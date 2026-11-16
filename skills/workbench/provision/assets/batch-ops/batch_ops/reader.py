"""Bounded, concurrent evidence gathering.

A read batch is a list of independent items.  Each item is isolated: a bad
regex, a missing file or a stale handle produces an error result while every
other item still completes.  All output is capped by the shared batch budget,
and truncation is always reported.
"""

from __future__ import annotations

import asyncio
import difflib
import fnmatch
import glob as globlib
import os
import re
import subprocess
import unicodedata
import time
from pathlib import Path

from .artifacts import ArtifactStore, make_read_handle, parse_read_handle
from .budget import BudgetTracker, body_budget, tier, water_fill
from .safety import (
    SafetyError,
    decode_bytes,
    estimate_tokens,
    format_bytes,
    literal_pattern,
    parse_range,
    relative_display,
    resolve_path,
    select_lines,
    sha256_bytes,
    truncate_text,
)
from .types import Coverage, ReadRequest, ReadResult, Report, Workspace
from .workspace import git_root_fast, path_is_within, workspace_info

MAX_FILE_BYTES = 32 * 1024 * 1024
DEFAULT_PARALLEL = 8
VCS_DIRS = {".git", ".hg", ".svn"}


def _skipped_dir(name: str) -> bool:
    """Folders never walked without git: version-control metadata and dot-folders."""
    return name in VCS_DIRS or name.startswith(".")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
async def read_batch(
    requests: list[ReadRequest],
    *,
    root: str | Path,
    tracker: BudgetTracker,
    artifacts: ArtifactStore,
    parallel: int = DEFAULT_PARALLEL,
    max_output: int = 64 * 1024,
) -> list[ReadResult]:
    """Read every request concurrently, then share the batch budget by what each produced.

    Pass 1 reads each item under its own per-item cap.  The batch budget is then shared
    with ``water_fill`` (small items keep everything, the rest split what is left), and only
    items that produced more than their share are read again under that share, which cuts
    them on a line boundary with a continuation.  Unused budget is never wasted.
    """
    root_p = Path(root).resolve()
    deadline = time.monotonic() + max(1.0, tracker.budget.time_s)
    semaphore = asyncio.Semaphore(max(1, int(parallel)))
    item_cap = min(max_output, tracker.budget.item_bytes)

    def early(req: ReadRequest, status: str, message: str) -> ReadResult:
        return ReadResult(id=req.label or "read", kind=req.kind, label=req.label,
                          status=status, message=message)

    async def run(req: ReadRequest, cap: int) -> ReadResult:
        if time.monotonic() >= deadline:
            return early(req, "error", "read skipped: batch deadline reached")
        async with semaphore:
            try:
                remaining = max(0.05, deadline - time.monotonic())
                return await asyncio.wait_for(
                    asyncio.to_thread(_read_one, req, root_p, cap, artifacts),
                    timeout=remaining,
                )
            except asyncio.TimeoutError:
                return early(req, "error", "read timed out at the batch deadline")
            except Exception as exc:  # one item never kills the batch
                return early(req, "error", f"{type(exc).__name__}: {exc}")

    async def first(index: int, req: ReadRequest) -> ReadResult:
        if req.error:
            return early(req, "error", req.error)
        if index >= tracker.budget.max_items:
            tracker.skip("item limit")
            return early(req, "skipped", f"skipped by item limit ({tracker.budget.max_items})")
        return await run(req, min(item_cap, req.max_bytes) if req.max_bytes else item_cap)

    results = list(await asyncio.gather(*(first(i, req) for i, req in enumerate(requests))))

    shares = water_fill([r.bytes_shown for r in results], [tier(r.priority) for r in requests],
                        body_budget(tracker.budget.bytes, len(requests)))
    redo = [i for i, r in enumerate(results) if r.bytes_shown > shares[i] + 256]
    if redo:
        again = await asyncio.gather(*(run(requests[i], shares[i]) for i in redo))
        for i, result in zip(redo, again):
            if result.status not in ("error", "skipped"):
                results[i] = result  # a failed re-read keeps the pass-1 result
    tracker.used_bytes = sum(r.bytes_shown for r in results)
    for index, result in enumerate(results, start=1):
        result.id = f"R{index}"
    return results


def _read_one(req: ReadRequest, root: Path, cap: int, artifacts: ArtifactStore) -> ReadResult:
    dispatch = {
        "file": _read_file_request,
        "glob": _glob_request,
        "grep": _grep_request,
        "git_diff": _git_diff_request,
        "git_changed": _git_changed_request,
        "compare": _compare_request,
        "handle": _handle_request,
        "artifact": _artifact_request,
    }
    handler = dispatch.get(req.kind)
    if handler is None:
        return ReadResult(id="read", kind=req.kind, label=req.label, status="error",
                          message=f"unknown read kind: {req.kind}")
    try:
        return handler(req, root, cap, artifacts)
    except SafetyError as exc:
        return ReadResult(id="read", kind=req.kind, label=req.label, path=req.path,
                          status="error", message=str(exc))
    except FileNotFoundError:
        return _missing_result(req, root)
    except Exception as exc:
        return ReadResult(id="read", kind=req.kind, label=req.label, path=req.path,
                          status="error", message=f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------
SUGGEST_SCAN_LIMIT = 5000


def _listed_names(root: Path) -> list[str]:
    """Forward-slash paths relative to *root*: git's listing, else a bounded walk."""
    code, out, _ = _git(root, ["ls-files", "--cached", "--others", "--exclude-standard", "-z"])
    if code == 0:
        return [name.replace("\\", "/") for name in out.split("\0") if name and not name.endswith("/")]
    names: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not _skipped_dir(d))
        for name in sorted(filenames):
            names.append((Path(dirpath) / name).relative_to(root).as_posix())
            if len(names) >= SUGGEST_SCAN_LIMIT:
                return names
    return names


def _respec(req: ReadRequest, path: str) -> str:
    """The string spec that repeats *req* on another path."""
    if req.mode == "lines" and req.range:
        return f"{path}:{req.range}"
    if req.mode in ("target", "raw") and req.range:
        return f"{path}@{req.mode}:{req.range}"
    if req.mode in ("outline", "list"):
        return f"{path}@{req.mode}"
    if req.mode in ("block", "grep") and req.pattern:
        return f"{path}@{req.mode}:{req.pattern}"
    if req.mode == "context" and req.pattern:
        return f"{path}@context:{req.pattern}:{req.context}"
    return path


def _missing_result(req: ReadRequest, root: Path) -> ReadResult:
    """A missing file names the real files it probably meant; a unique match becomes the continuation."""
    result = ReadResult(id="read", kind=req.kind, label=req.label, path=req.path,
                        status="missing", message="file or directory not found")
    wanted = (req.path or "").replace("\\", "/").strip()
    while wanted.startswith("./"):
        wanted = wanted[2:]
    if req.kind != "file" or not wanted or Path(wanted).is_absolute():
        return result
    try:
        names = _listed_names(root)
    except Exception:
        return result
    by_suffix = sorted((n for n in names if n.endswith("/" + wanted)), key=lambda n: (len(n), n))
    if by_suffix:
        hits = by_suffix
    else:
        base = wanted.rsplit("/", 1)[-1]
        hits = sorted((n for n in names if n.rsplit("/", 1)[-1] == base), key=lambda n: (len(n), n))
    if not hits:
        return result
    result.message += "; did you mean " + ", ".join(f'"{n}"' for n in hits[:3]) + (
        f" ({len(hits) - 3} more)" if len(hits) > 3 else "") + "?"
    if len(by_suffix) == 1:
        result.meta["continuation"] = _respec(req, by_suffix[0])
    return result


def _read_file_request(req: ReadRequest, root: Path, cap: int, artifacts: ArtifactStore) -> ReadResult:
    if not req.path:
        raise SafetyError("file read requires path")
    path = resolve_path(root, req.path, allow_outside=req.allow_outside, must_exist=True)
    display = relative_display(root, path)

    if path.is_dir():
        return _list_directory(path, display, cap, req)
    if req.mode == "list":
        stat = path.stat()
        body = f"f {format_bytes(stat.st_size):>9} {path.name}\nmodified: {_mtime(path)}"
        return ReadResult(
            id="read", kind="file", label=req.label, path=display, status="ok",
            body=body, bytes_total=stat.st_size,
            bytes_shown=len(body.encode("utf-8", errors="replace")),
            lines_total=1, lines_shown=1, meta={"kind": "file", "size_bytes": stat.st_size},
        )

    if not path.is_file():
        raise SafetyError(f"not a regular file: {display}")

    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        return ReadResult(
            id="read", kind="file", label=req.label, status="error", path=display,
            bytes_total=size, message=f"file is {format_bytes(size)}; limit is {format_bytes(MAX_FILE_BYTES)}",
        )

    data = path.read_bytes()
    info = decode_bytes(data, req.encoding)
    if info.binary:
        return ReadResult(
            id="read", kind="file", label=req.label, status="binary", path=display,
            bytes_total=info.bytes_total,
            message="binary data (NUL bytes); read it with batch_run and an explicit tool",
        )

    sha = sha256_bytes(data)
    if req.since:
        expected = _since_sha(req.since)
        if expected and sha.startswith(expected):
            return ReadResult(
                id="read", kind="file", label=req.label, path=display, status="unchanged",
                hash=sha, bytes_total=info.bytes_total, bytes_shown=0,
                handle=make_read_handle(display, sha, None, None),
                message="unchanged since the given hash; body omitted",
            )
    text = info.text
    lines = text.splitlines()
    lines_total = len(lines)
    mode = req.mode if req.mode != "auto" else ("lines" if req.range else "auto")

    handle_start: int | None = None
    handle_end: int | None = None
    line_rows: list[tuple[int, str]] | None = None
    meta: dict[str, object] = {
        "encoding": info.encoding,
        "eol": _eol_name(info.eol),
        "mixed_eol": info.mixed_eol,
        "lossy": info.lossy,
        "sha256": sha,
        "size_bytes": info.bytes_total,
    }

    if mode in ("context", "grep"):
        if not req.pattern:
            raise SafetyError(f"{mode} mode requires a pattern")
        body, match_count = _grep_text(
            text,
            req.pattern,
            context=req.context if mode == "context" else 0,
            fixed=False,
            ignore_case=False,
            number=True,
        )
        if match_count == 0:
            body = f"(no matches for {req.pattern})"
        meta["matches"] = match_count
        selected_count = body.count("\n") + 1 if body else 0

    elif mode == "block":
        if not req.pattern:
            raise SafetyError("block mode requires a pattern")
        spans = _block_spans(lines, req.pattern)
        if not spans:
            body = f"(no matches for {req.pattern})"
            selected_count = 0
        else:
            rows: list[str] = []
            selected_count = 0
            for index, (start, end) in enumerate(spans):
                if index:
                    rows.append("--")
                rows.extend(f"{n + 1:4d}: {lines[n]}" for n in range(start, end + 1))
                selected_count += end - start + 1
            body = "\n".join(rows)
            capped = [(s, e) for s, e in spans if e - s + 1 >= BLOCK_MAX_LINES - 1]
            if capped:
                s, e = capped[0]
                meta["block_capped"] = f"block cut at {BLOCK_MAX_LINES} lines; read \"{display}:{e + 2}-{lines_total}\" to continue"
            if len(spans) == 1:
                handle_start, handle_end = spans[0][0] + 1, spans[0][1] + 1
                line_rows = [(n + 1, f"{n + 1:4d}: {lines[n]}") for n in range(spans[0][0], spans[0][1] + 1)]
        meta["matches"] = len(spans)

    elif mode == "outline":
        picked = _outline_lines(lines, depth=req.depth)
        body = "\n".join(f"{n + 1:4d}: {lines[n]}" for n in picked) if picked else "(no outline: no indented blocks)"
        selected_count = len(picked)
        meta["outline_depth"] = req.depth

    elif mode == "target":
        if not req.range:
            raise SafetyError("target mode requires a range")
        ranges = parse_range(req.range)
        selected = select_lines(lines, ranges)
        if not selected:
            body = "(range is outside the file)"
        else:
            start_line = selected[0][0]
            end_line = selected[-1][0]
            numbered = [f"{n:4d}: {line}" for n, line in selected]
            verbatim = [line for _, line in selected]
            body = "\n".join(
                [f"=== [context {start_line}-{end_line} (numbered)] ===",
                 *numbered,
                 "",
                 "=== [target: copy verbatim to batch_edit] ===",
                 *verbatim,
                 "=== [end target] ==="]
            )
            handle_start, handle_end = start_line, end_line
        selected_count = len(selected)

    else:
        ranges = parse_range(req.range) if req.range else []
        selected = select_lines(lines, ranges)
        if req.max_lines is not None and len(selected) > req.max_lines:
            selected = selected[: req.max_lines]
            meta["line_cap"] = req.max_lines
        if not selected:
            body = "(no lines selected)"
        elif mode == "raw":
            line_rows = [(n, line) for n, line in selected]
            body = "\n".join(row for _, row in line_rows)
        else:
            line_rows = [(n, f"{n:4d}: {line}") for n, line in selected]
            body = "\n".join(row for _, row in line_rows)
        selected_count = len(selected)
        if ranges:
            handle_start = ranges[0][0]
            handle_end = ranges[-1][1] if ranges[-1][1] < 2**31 - 1 else lines_total

    effective_cap = min(cap, req.max_bytes) if req.max_bytes else cap
    full_body = body
    body, truncated, continuation, kept_count = _fit_body(
        full_body, line_rows, effective_cap, lines_total, lambda a, b: f"{display}:{a}-{b}"
    )
    if kept_count is not None:
        selected_count = kept_count
    artifact = artifacts.put(full_body, ".read.txt") if truncated else None

    if req.range is None and handle_start is None:
        handle_start, handle_end = None, None
    handle = make_read_handle(display, sha, handle_start, handle_end)

    status = "truncated" if truncated else ("lossy" if info.lossy else "ok")
    message = None
    if info.lossy:
        message = f"decoded as {info.encoding} with replacement characters"
    if truncated:
        message = f"body truncated to {format_bytes(effective_cap)}; full file is {format_bytes(info.bytes_total)}"
        if continuation:
            message += f"; continue with \"{continuation}\""
            meta["continuation"] = continuation
    if meta.get("block_capped"):
        message = f"{message}; {meta['block_capped']}" if message else str(meta["block_capped"])
    if info.mixed_eol:
        meta["mixed_eol_note"] = "mixed line endings preserved"

    shown = len(body.encode("utf-8", errors="replace"))
    meta["handle"] = handle
    if not path_is_within(root, path):
        meta["outside"] = True
    meta["match_count"] = meta.get("matches", 0)
    return ReadResult(
        id="read", kind="file", label=req.label, path=display,
        range=(handle_start, handle_end) if handle_start is not None else None,
        body=body, hash=sha, bytes_total=info.bytes_total, bytes_shown=shown,
        lines_total=lines_total, lines_shown=selected_count,
        truncated=truncated, status=status, message=message, handle=handle,
        artifact=artifact, meta=meta,
    )


def _fit_body(
    full_body: str,
    line_rows: list[tuple[int, str]] | None,
    cap: int,
    lines_total: int,
    next_ref,  # (first_line, last_line) -> the spec that reads the rest
) -> tuple[str, bool, str | None, int | None]:
    """Cut *full_body* to *cap* bytes: on a line boundary with a continuation when rows are known.

    Returns (body, truncated, continuation, rows_kept).
    """
    if line_rows and len(full_body.encode("utf-8", errors="replace")) > cap:
        kept: list[tuple[int, str]] = []
        used = 0
        for n, row in line_rows:
            size = len(row.encode("utf-8", errors="replace")) + 1
            if kept and used + size > max(64, cap - 160):
                break
            kept.append((n, row))
            used += size
        first, last, end = kept[0][0], kept[-1][0], line_rows[-1][0]
        continuation = next_ref(last + 1, end)
        body = "\n".join(row for _, row in kept) + (
            f"\n[... truncated: showed lines {first}-{last} of {lines_total}; "
            f"read \"{continuation}\" for the rest]"
        )
        return body, True, continuation, len(kept)
    body, truncated, _ = truncate_text(full_body, cap, style="head")
    return body, truncated, None, None


# ---------------------------------------------------------------------------
# Artifacts (full output that did not fit an earlier report)
# ---------------------------------------------------------------------------
def _artifact_request(req: ReadRequest, root: Path, cap: int, artifacts: ArtifactStore) -> ReadResult:
    try:
        name = artifacts.name(req.artifact or "")
    except ValueError as exc:
        raise SafetyError(str(exc)) from exc
    display = f"artifact:{name}"
    try:
        data = artifacts.get(name)
    except OSError:
        return ReadResult(id="read", kind="artifact", label=req.label, path=display, status="missing",
                          message="artifact expired or unknown (artifacts are kept about an hour)")
    text = decode_bytes(data).text
    lines = text.splitlines()
    line_rows: list[tuple[int, str]] | None = None
    if req.pattern:
        body, count = _grep_text(text, req.pattern, context=req.context, fixed=False,
                                 ignore_case=req.ignore_case, number=True)
        body = body or f"(no matches for {req.pattern})"
        shown_lines = body.count("\n") + 1 if count else 0
        meta: dict[str, object] = {"matches": count}
    else:
        selected = select_lines(lines, parse_range(req.range) if req.range else [])
        line_rows = [(n, f"{n:4d}: {line}") for n, line in selected]
        body = "\n".join(row for _, row in line_rows) or "(no lines selected)"
        shown_lines = len(selected)
        meta = {}
    body, truncated, continuation, kept = _fit_body(
        body, line_rows, cap, len(lines), lambda a, b: f"{display}:{a}-{b}"
    )
    if continuation:
        meta["continuation"] = continuation
    return ReadResult(
        id="read", kind="artifact", label=req.label, path=display,
        status="truncated" if truncated else "ok", body=body,
        bytes_total=len(data), bytes_shown=len(body.encode("utf-8", errors="replace")),
        lines_total=len(lines), lines_shown=kept if kept is not None else shown_lines,
        truncated=truncated, meta=meta,
        message=f"continue with \"{continuation}\"" if continuation else None,
    )


# ---------------------------------------------------------------------------
# Structure without language knowledge: indentation, blank lines and character
# classes only. No keywords, bracket characters, file extensions or names.
# ---------------------------------------------------------------------------
BLOCK_MAX_LINES = 400
BLOCK_MAX_MATCHES = 5
_QUOTES = "\"'`"


def _since_sha(value: str) -> str | None:
    value = value.strip()
    if value.startswith("read:"):
        try:
            value = str(parse_read_handle(value)["sha"])
        except ValueError:
            return None
    value = value.lower()
    return value if len(value) >= 8 and re.fullmatch(r"[0-9a-f]+", value) else None


def _width(line: str) -> int:
    stripped = line.lstrip(" \t")
    return len(line[: len(line) - len(stripped)].replace("\t", "    "))


def _lone(line: str) -> bool:
    """One token on the line (no inner whitespace)."""
    text = line.strip()
    return bool(text) and len(text.split()) == 1


def _punct_only(line: str) -> bool:
    text = line.strip()
    return bool(text) and not any(ch.isalnum() for ch in text)


def _starts_with_punct(line: str) -> bool:
    """Line opens with punctuation or a symbol (not a quote): it continues something above."""
    text = line.lstrip()
    if not text or text[0] in _QUOTES:
        return False
    category = unicodedata.category(text[0])
    return category[0] in "PS" and category != "Pc"  # connector punctuation ("_") is a word char, as in \w


def _block_end(lines: list[str], start: int) -> int:
    """End of the block opened at ``start`` (0-based, inclusive).

    Lines deeper than the match belong to it. Before any deeper line, a lone token at the
    match's indentation continues the header (an opener on its own line). After the body, a
    line at the match's indentation that starts with punctuation and is followed by deeper
    lines continues it (a multi-line header's closing part); a lone punctuation-only line
    closes it and is included; anything else ends the block before that line.
    """
    base = _width(lines[start])
    limit = min(len(lines), start + BLOCK_MAX_LINES)

    def next_nonblank(k: int) -> int | None:
        for m in range(k + 1, limit):
            if lines[m].strip():
                return m
        return None

    end = start
    seen_body = False
    j = start + 1
    while j < limit:
        line = lines[j]
        if not line.strip():
            j += 1
            continue
        width = _width(line)
        if width > base:
            end, seen_body = j, True
            j += 1
            continue
        if width != base:
            break
        if not seen_body:
            if _lone(line):
                end = j
                j += 1
                continue
            break
        nxt = next_nonblank(j)
        if _starts_with_punct(line) and nxt is not None and _width(lines[nxt]) > base:
            end = j
            j += 1
            continue
        if _lone(line) and _punct_only(line):
            end = j
        break
    return end


def _block_spans(lines: list[str], pattern: str) -> list[tuple[int, int]]:
    rx = _compile_pattern(pattern, fixed=False, ignore_case=False)
    spans: list[tuple[int, int]] = []
    for i, line in enumerate(lines):
        if not rx.search(line):
            continue
        if spans and i <= spans[-1][1]:
            continue  # already inside the previous block
        spans.append((i, _block_end(lines, i)))
        if len(spans) >= BLOCK_MAX_MATCHES:
            break
    return spans


def _outline_lines(lines: list[str], *, depth: int) -> list[int]:
    """Lines that open an indented block, nested at most ``depth`` levels deep.

    A lone token that opens a block (an opener on its own line) is shown by the line above it;
    a line starting with punctuation continues an earlier header and is not shown.
    """
    picked: list[int] = []
    stack: list[int] = []  # widths of enclosing block headers
    nonblank = [i for i, line in enumerate(lines) if line.strip()]
    for pos, i in enumerate(nonblank):
        width = _width(lines[i])
        while stack and width <= stack[-1]:
            stack.pop()
        nxt = nonblank[pos + 1] if pos + 1 < len(nonblank) else None
        if nxt is None or _width(lines[nxt]) <= width:
            continue
        if len(stack) < depth:
            shown = i
            # An opener on its own line ("{", "begin") belongs to the header line just above it
            # at the same indentation; a one-word header ("client:") stands for itself.
            if _lone(lines[i]) and pos > 0 and _width(lines[nonblank[pos - 1]]) == width:
                shown = nonblank[pos - 1]
            if not _starts_with_punct(lines[shown]) and (not picked or picked[-1] != shown):
                picked.append(shown)
        stack.append(width)
    return picked


def _mtime(path: Path) -> str:
    import datetime

    try:
        return datetime.datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        return "?"


def _list_directory(path: Path, display: str, cap: int, req: ReadRequest) -> ReadResult:
    entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    limit = max(1, min(req.max_files or 200, 500))
    shown = entries[:limit]
    rows: list[str] = []
    for entry in shown:
        try:
            if entry.is_dir():
                rows.append(f"d {entry.name}/")
            else:
                rows.append(f"f {format_bytes(entry.stat().st_size):>9} {entry.name}")
        except OSError:
            rows.append(f"? {entry.name}")
    if len(entries) > limit:
        rows.append(f"... {len(entries) - limit} more entries not listed")
    body, truncated, total_bytes = truncate_text("\n".join(rows) or "(empty directory)", cap, style="head")
    return ReadResult(
        id="read", kind="file", label=req.label, path=display, status="truncated" if truncated else "ok",
        body=body, bytes_total=total_bytes, bytes_shown=len(body.encode("utf-8", errors="replace")),
        lines_total=len(entries), lines_shown=len(shown), truncated=truncated,
        message=f"directory listing truncated to {format_bytes(cap)}" if truncated else None,
        meta={"entries": len(entries), "listed": len(shown), "kind": "directory"},
    )


def _eol_name(eol: str | None) -> str:
    return {"\r\n": "CRLF", "\n": "LF", "\r": "CR", None: "none"}.get(eol, eol or "none")


# ---------------------------------------------------------------------------
# Grep
# ---------------------------------------------------------------------------
def _compile_pattern(pattern: str, *, fixed: bool, ignore_case: bool) -> re.Pattern[str]:
    if not pattern:
        raise SafetyError("search pattern must not be empty")
    flags = re.IGNORECASE if ignore_case else 0
    if fixed:
        return re.compile(re.escape(pattern), flags)
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        raise SafetyError(f"invalid regular expression: {exc}") from exc


def _grep_text(
    text: str,
    pattern: str,
    *,
    context: int,
    fixed: bool,
    ignore_case: bool,
    number: bool,
) -> tuple[str, int]:
    rx = _compile_pattern(pattern, fixed=fixed, ignore_case=ignore_case)
    lines = text.splitlines()
    hits = [i for i, line in enumerate(lines) if rx.search(line)]
    if not hits:
        return "", 0
    if context <= 0:
        chosen = hits
    else:
        selected: set[int] = set()
        for i in hits:
            selected.update(range(max(0, i - context), min(len(lines), i + context + 1)))
        chosen = sorted(selected)

    out: list[str] = []
    previous = None
    hit_set = set(hits)
    for idx in chosen:
        if previous is not None and idx > previous + 1:
            out.append("--")
        marker = ":" if idx in hit_set else "-"
        out.append(f"{idx + 1:4d}{marker} {lines[idx]}" if number else lines[idx])
        previous = idx
    return "\n".join(out), len(hits)


def _grep_request(req: ReadRequest, root: Path, cap: int, artifacts: ArtifactStore) -> ReadResult:
    if not req.pattern:
        raise SafetyError("grep requires a pattern")
    rx = _compile_pattern(req.pattern, fixed=req.fixed, ignore_case=req.ignore_case)
    path_specs = req.paths or ["."]
    files: list[Path] = []
    seen: set[str] = set()
    truncated_listing = False

    for spec in path_specs:
        for candidate in _expand_paths(root, spec):
            resolved = resolve_path(root, candidate, allow_outside=req.allow_outside, must_exist=False)
            key = os.path.normcase(str(resolved))
            if key in seen:
                continue
            seen.add(key)
            if resolved.is_file():
                files.append(resolved)
            elif resolved.is_dir():
                listed = _git_listed(resolved)
                if listed is not None:
                    files.extend(listed)
                    continue
                for dirpath, dirnames, filenames in os.walk(resolved):
                    dirnames[:] = sorted(d for d in dirnames if not _skipped_dir(d))
                    for name in sorted(filenames):
                        files.append(Path(dirpath) / name)
                        if len(files) >= req.max_files * 10:
                            truncated_listing = True
                            break
                    if truncated_listing:
                        break
            if truncated_listing:
                break
        if truncated_listing:
            break

    excluded = 0
    if req.exclude:
        def _excluded(path: Path) -> bool:
            rel = relative_display(root, path)
            name = rel.rsplit("/", 1)[-1]
            return any(fnmatch.fnmatch(rel, pat) or ("/" not in pat and fnmatch.fnmatch(name, pat))
                       for pat in req.exclude)
        kept_files = [p for p in files if not _excluded(p)]
        excluded = len(files) - len(kept_files)
        files = kept_files

    if len(files) > req.max_files:
        truncated_listing = True
    files = files[: req.max_files]
    out: list[str] = []
    match_count = 0
    files_with_hits = 0
    scanned = 0
    skipped_binary = 0
    for path in files:
        if match_count >= req.max_matches:
            truncated_listing = True
            break
        try:
            if not req.allow_outside and path.is_symlink() and not path_is_within(root, path.resolve()):
                continue  # a link inside the tree that points outside cwd
            if path.stat().st_size > 4 * 1024 * 1024:
                continue
            data = path.read_bytes()
        except OSError:
            continue
        info = decode_bytes(data)
        if info.binary:
            skipped_binary += 1
            continue
        scanned += 1
        rel = relative_display(root, path)
        lines = info.text.splitlines()
        hits = [i for i, line in enumerate(lines) if rx.search(line)]
        if not hits:
            continue
        files_with_hits += 1
        out.append(f"=== {rel} ===")
        selected: set[int] = set()
        for i in hits:
            selected.update(range(max(0, i - req.context), min(len(lines), i + req.context + 1)))
        previous = None
        hit_set = set(hits)
        for idx in sorted(selected):
            if previous is not None and idx > previous + 1:
                out.append("--")
            marker = ":" if idx in hit_set else "-"
            out.append(f"{idx + 1:4d}{marker} {lines[idx]}")  # path is in the === header ===
            previous = idx
            if idx in hit_set:
                match_count += 1
                if match_count >= req.max_matches:
                    break
        if match_count >= req.max_matches:
            break

    full = "\n".join(out) if out else f"(no matches for {req.pattern})"
    full_bytes = len(full.encode("utf-8", errors="replace"))
    clip = max(20, req.max_line)
    rows = [(i + 1, row if len(row) <= clip else f"{row[:clip]} …[+{len(row) - clip} chars]")
            for i, row in enumerate(out)]
    shown = "\n".join(row for _, row in rows) if out else full
    body, truncated, artifact, continuation = shown, False, None, None
    if out and len(shown.encode("utf-8", errors="replace")) > cap:
        # Cut on a report line, keeping the full rows as an artifact the continuation reads by line.
        artifact = artifacts.put(full, ".grep.txt")
        body, truncated, continuation, _ = _fit_body(shown, rows, cap, len(out), lambda a, b: f"{artifact}:{a}-{b}")
    return ReadResult(
        id="read", kind="grep", label=req.label or f"grep:{req.pattern}", status="truncated" if truncated else "ok",
        body=body, bytes_total=full_bytes, bytes_shown=len(body.encode("utf-8", errors="replace")),
        lines_total=len(out), lines_shown=match_count, truncated=truncated,
        message="; ".join(m for m in (
            f"{len(files)} file(s) capped at max_files={req.max_files}" if truncated_listing else "",
            f"{excluded} file(s) excluded" if excluded else "",
        ) if m) or None,
        artifact=artifact,
        meta={
            "matches": match_count, "files_with_hits": files_with_hits, "files_scanned": scanned,
            "files_candidates": len(files), "skipped_binary": skipped_binary,
            "truncated_listing": truncated_listing, "excluded": excluded,
            **({"continuation": continuation} if continuation else {}),
        },
    )


def _git_listed(base: Path) -> list[Path] | None:
    """Tracked plus untracked, non-ignored files under *base*, or None outside a git repository."""
    code, out, _ = _git(base, ["ls-files", "--cached", "--others", "--exclude-standard", "-z"])
    if code != 0:
        return None
    return [base / name for name in out.split("\0") if name and not name.endswith("/")]


def _expand_paths(root: Path, spec: str) -> list[Path]:
    if any(ch in spec for ch in "*?["):
        if Path(spec).is_absolute():
            return [Path(p) for p in globlib.iglob(spec, recursive=True)]
        return [root / p for p in globlib.iglob(spec, root_dir=str(root), recursive=True)]
    return [root / spec]


# ---------------------------------------------------------------------------
# Globs
# ---------------------------------------------------------------------------
def _glob_request(req: ReadRequest, root: Path, cap: int, artifacts: ArtifactStore) -> ReadResult:
    if not req.glob:
        raise SafetyError("glob requires a pattern")
    pattern = req.glob
    limit = max(1, min(req.max_files, 1000))
    entries: list[Path] = []
    total_matches = 0
    outside = 0
    ignored = 0
    if Path(pattern).is_absolute():
        iterator = globlib.iglob(pattern, recursive=True)
    else:
        iterator = globlib.iglob(pattern, root_dir=str(root), recursive=True)

    # Inside git, list only files git does not ignore (tracked plus untracked), as grep does;
    # git's own ignore rules decide, so no folder names are hard-coded here.
    keep: set[str] | None = None
    if not req.include_ignored:
        code, out, _ = _git(root, ["ls-files", "--cached", "--others", "--exclude-standard", "-z"])
        if code == 0:
            keep = {os.path.normcase(name.replace("\\", "/")) for name in out.split("\0") if name}

    # No folder filter otherwise: glob never matches a dot-name with * or **, so a hidden
    # folder only appears when the pattern names it (".github/**/*").
    for raw in iterator:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            candidate = candidate.resolve()
        except OSError:
            continue
        inside = path_is_within(root, candidate)
        if not inside and not req.allow_outside:
            outside += 1  # "../*" or an absolute pattern reaching outside cwd
            continue
        if not candidate.is_file():
            continue
        if keep is not None and inside and os.path.normcase(relative_display(root, candidate)) not in keep:
            ignored += 1
            continue
        total_matches += 1
        if len(entries) < limit:
            entries.append(candidate)

    entries.sort(key=lambda p: relative_display(root, p).lower())
    rows = [f"{format_bytes(p.stat().st_size):>9} {relative_display(root, p)}" for p in entries]
    more = total_matches - len(entries)
    body_parts = list(rows)  # the pattern is in the item header (label)
    if more > 0:
        body_parts.append(f"... {more} more matches not listed (max_files={limit})")
    if not entries:
        body_parts.append("(no files matched)")

    expanded = 0
    expanded_meta: list[dict[str, object]] = []
    if req.expand and entries:
        remaining_cap = max(1024, cap // max(2, len(entries)))
        for path in entries[: min(len(entries), 25)]:
            try:
                if path.stat().st_size > 256 * 1024:
                    continue
                data = path.read_bytes()
                info = decode_bytes(data)
                if info.binary:
                    continue
                rel = relative_display(root, path)
                text, _, _ = truncate_text(info.text, remaining_cap, style="head")
                body_parts.extend(["", f"=== {rel} ===", text])
                expanded += 1
                sha = sha256_bytes(data)
                expanded_meta.append({
                    "path": rel,
                    "hash": sha,
                    "handle": make_read_handle(rel, sha, None, None),
                })
            except OSError:
                continue

    body, truncated, full_bytes = truncate_text("\n".join(body_parts), cap, style="head")
    artifact = artifacts.put("\n".join(body_parts), ".glob.txt") if truncated else None
    notes = []
    if more > 0:
        notes.append(f"{total_matches} match(es); listing capped at {limit}")
    if outside:
        notes.append(f"{outside} match(es) outside cwd skipped")
    if ignored:
        notes.append(f"{ignored} gitignored match(es) skipped; add \"ignored\": true to include them")
    return ReadResult(
        id="read", kind="glob", label=req.label or f"glob:{pattern}", status="truncated" if truncated else "ok",
        body=body, bytes_total=full_bytes, bytes_shown=len(body.encode("utf-8", errors="replace")),
        lines_total=len(entries), lines_shown=len(entries), truncated=truncated,
        message="; ".join(notes) or None,
        artifact=artifact,
        meta={"matches": total_matches, "listed": len(entries), "expanded": expanded,
              "handles": expanded_meta, "ignored_skipped": ignored},
    )


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------
def _git(root: Path, args: list[str], timeout: float = 20.0) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return 127, "", "git is not installed"
    except subprocess.TimeoutExpired:
        return 124, "", f"git timed out after {timeout:.0f}s"
    except OSError as exc:
        return 1, "", str(exc)


def _status_rows(out: str, root: Path, top: Path | None) -> list[str]:
    """Rows of ``git status --porcelain=v1 -z`` with paths made relative to cwd.

    Porcelain paths are relative to the repository root; with -z a rename or copy
    carries its source path in the next field, which is skipped here.
    """
    fields = out.split("\0")
    rows: list[str] = []
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        if "R" in status or "C" in status:
            i += 1
        if top is not None:
            try:
                path = Path(os.path.relpath(top / path, root)).as_posix()
            except ValueError:  # another drive
                pass
        rows.append(f"{status} {path}")
    return rows


def _git_diff_request(req: ReadRequest, root: Path, cap: int, artifacts: ArtifactStore) -> ReadResult:
    args = ["--no-pager", "diff", "--no-color", "--no-ext-diff"]
    if req.staged:
        args.append("--cached")
    if req.base and req.base != "HEAD":
        args.append(req.base)
    elif not req.staged:
        args.append("HEAD")
    if req.paths:
        args.extend(["--", *req.paths])
    code, out, err = _git(root, args)
    if code != 0:
        return ReadResult(id="read", kind="git_diff", label=req.label, status="error",
                          message=err.strip() or f"git diff failed ({code})")
    if not out.strip():
        return ReadResult(id="read", kind="git_diff", label=req.label, status="unchanged",
                          body="(no changes)", message="working tree matches the requested base")
    body, truncated, full_bytes = truncate_text(out, cap, style="head_tail")
    artifact = artifacts.put(out, ".diff") if truncated else None
    files = sorted({line[6:].strip() for line in out.splitlines()
                    if line.startswith("+++ ") and line[6:].strip() not in ("/dev/null",)})
    return ReadResult(
        id="read", kind="git_diff", label=req.label, status="truncated" if truncated else "ok",
        body=body, bytes_total=full_bytes, bytes_shown=len(body.encode("utf-8", errors="replace")),
        truncated=truncated, artifact=artifact,
        message=f"diff truncated at {format_bytes(cap)}; artifact kept" if truncated else None,
        meta={"files": files, "file_count": len(files), "staged": req.staged, "base": req.base},
    )


def _git_changed_request(req: ReadRequest, root: Path, cap: int, artifacts: ArtifactStore) -> ReadResult:
    code, out, err = _git(root, ["--no-pager", "status", "--porcelain=v1", "-z", "--untracked-files=normal"])
    if code != 0:
        return ReadResult(id="read", kind="git_changed", label=req.label, status="error",
                          message=err.strip() or f"git status failed ({code})")
    rows = _status_rows(out, root, git_root_fast(root))
    body_text = "\n".join(rows) if rows else "(no local changes)"
    body, truncated, full_bytes = truncate_text(body_text, cap, style="head")
    artifact = artifacts.put(body_text, ".status.txt") if truncated else None
    return ReadResult(
        id="read", kind="git_changed", label=req.label,
        status="unchanged" if not rows else ("truncated" if truncated else "ok"),
        body=body, bytes_total=full_bytes, bytes_shown=len(body.encode("utf-8", errors="replace")),
        lines_total=len(rows), lines_shown=len(rows), truncated=truncated, artifact=artifact,
        meta={"changed": len(rows)},
    )


# ---------------------------------------------------------------------------
# Handles
# ---------------------------------------------------------------------------
def _handle_request(req: ReadRequest, root: Path, cap: int, artifacts: ArtifactStore) -> ReadResult:
    if not req.handle:
        raise SafetyError("handle read requires a handle")
    parsed = parse_read_handle(req.handle)
    path = resolve_path(root, str(parsed["path"]), allow_outside=req.allow_outside, must_exist=True)
    display = relative_display(root, path)
    data = path.read_bytes()
    current = sha256_bytes(data)
    expected = str(parsed["sha"])
    if not current.startswith(expected):
        return ReadResult(
            id="read", kind="handle", label=req.label, path=display, status="stale",
            hash=current, bytes_total=len(data),
            message="file changed since the handle was issued; re-read the file",
            meta={"expected_hash": expected, "handle": req.handle},
        )
    mode = "lines"
    range_value = None
    start, end = parsed["start"], parsed["end"]
    if start is not None and end is not None:
        range_value = f"{start}-{end}"
    child = ReadRequest(
        kind="file", path=display, mode=mode, range=range_value,
        encoding=req.encoding, max_bytes=req.max_bytes, priority=req.priority,
        allow_outside=req.allow_outside,
    )
    result = _read_file_request(child, root, cap, artifacts)
    result.kind = "handle"
    result.label = req.label
    result.message = "handle verified; file unchanged"
    result.meta["handle"] = req.handle
    return result


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------
def _load_for_compare(req: ReadRequest, root: Path) -> tuple[str, str, str | None]:
    """Return (display, text, error).  Reads the full text, ignoring inline output caps."""
    if req.kind == "handle":
        parsed = parse_read_handle(req.handle or "")
        path = resolve_path(root, str(parsed["path"]), allow_outside=req.allow_outside, must_exist=True)
        data = path.read_bytes()
        if not sha256_bytes(data).startswith(str(parsed["sha"])):
            return relative_display(root, path), "", "stale handle"
        info = decode_bytes(data, req.encoding)
        if info.binary:
            return relative_display(root, path), "", "binary file"
        text = info.text
        start, end = parsed["start"], parsed["end"]
        if start is not None and end is not None:
            text = "\n".join(text.splitlines()[int(start) - 1:int(end)])
        return relative_display(root, path), text, None

    if req.kind == "file" and req.path:
        path = resolve_path(root, req.path, allow_outside=req.allow_outside, must_exist=True)
        data = path.read_bytes()
        info = decode_bytes(data, req.encoding)
        if info.binary:
            return relative_display(root, path), "", "binary file"
        text = info.text
        if req.range:
            lines = text.splitlines()
            selected = select_lines(lines, parse_range(req.range))
            text = "\n".join(line for _, line in selected)
        return relative_display(root, path), text, None
    return req.path or req.handle or "?", "", "compare children must be file or handle reads"


def _compare_request(req: ReadRequest, root: Path, cap: int, artifacts: ArtifactStore) -> ReadResult:
    if len(req.children) < 2:
        raise SafetyError("compare needs at least two children")
    loaded: list[tuple[str, str]] = []
    errors: list[str] = []
    for child in req.children:
        display, text, error = _load_for_compare(child, root)
        if error:
            errors.append(f"{display}: {error}")
        else:
            loaded.append((display, text))
    if errors:
        return ReadResult(id="read", kind="compare", label=req.label, status="error",
                          message="; ".join(errors), meta={"children": len(req.children)})

    if len(loaded) == 2:
        (left_name, left), (right_name, right) = loaded
        if left == right:
            body = f"(identical: {left_name} and {right_name})"
            diff_text = body
        else:
            diff_text = "\n".join(difflib.unified_diff(
                left.splitlines(), right.splitlines(),
                fromfile=f"a/{left_name}", tofile=f"b/{right_name}", lineterm="",
            ))
            body = diff_text
    else:
        parts: list[str] = []
        for name, text in loaded:
            parts.extend([f"=== {name} ===", text, ""])
        diff_text = "\n".join(parts).rstrip()
        body = diff_text

    body, truncated, full_bytes = truncate_text(body, cap, style="head_tail")
    artifact = artifacts.put(diff_text, ".compare.diff") if truncated else None
    return ReadResult(
        id="read", kind="compare", label=req.label, status="truncated" if truncated else "ok",
        body=body, bytes_total=full_bytes, bytes_shown=len(body.encode("utf-8", errors="replace")),
        truncated=truncated, artifact=artifact,
        message=f"comparison truncated at {format_bytes(cap)}; artifact kept" if truncated else None,
        meta={"children": [n for n, _ in loaded], "identical": len(loaded) == 2 and loaded[0][1] == loaded[1][1]},
    )


# ---------------------------------------------------------------------------
# Survey
# ---------------------------------------------------------------------------
def survey(
    root: str | Path,
    *,
    focus: list[str] | None = None,
    max_files: int = 2000,
    artifacts: ArtifactStore | None = None,
    max_bytes: int = 32 * 1024,
) -> Report:
    root_p = Path(root).resolve()
    report = Report(tool="batch_read", mode="survey", cwd=str(root_p))
    info = workspace_info(root_p)
    report.workspace = info

    files: list[Path] = []
    truncated_walk = False
    used_git_ls = False
    git_top_dirs: set[str] = set()
    git_top_files: set[str] = set()
    if info.git_root:
        code, out, _ = _git(root_p, ["ls-files", "--cached", "--others", "--exclude-standard", "-z"])
        if code == 0:
            used_git_ls = True
            for raw_rel in out.split("\0"):
                if not raw_rel:
                    continue
                # Collect every top-level entry before the max_files cap so the listing stays
                # complete even when the walk is truncated.
                first, sep, _ = raw_rel.partition("/")
                if sep:
                    git_top_dirs.add(first + "/")
                else:
                    git_top_files.add(first)
                if len(files) >= max_files:
                    truncated_walk = True
                    continue
                p = root_p / raw_rel
                files.append(p)

    if not used_git_ls:
        for dirpath, dirnames, filenames in os.walk(root_p):
            dirnames[:] = sorted(d for d in dirnames if not _skipped_dir(d))
            for name in sorted(filenames):
                files.append(Path(dirpath) / name)
                if len(files) >= max_files:
                    truncated_walk = True
                    break
            if truncated_walk:
                break

    by_ext: dict[str, list[Path]] = {}
    total_size = 0
    largest: list[tuple[int, Path]] = []
    tree_summary: dict[str, dict[str, int]] = {}
    for path in files:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        total_size += size
        largest.append((size, path))
        ext = path.suffix.lower() or "(none)"
        by_ext.setdefault(ext, []).append(path)
        rel = relative_display(root_p, path)
        top_part = rel.split("/")[0] if "/" in rel else "."
        if top_part not in tree_summary:
            tree_summary[top_part] = {"files": 0, "bytes": 0}
        tree_summary[top_part]["files"] += 1
        tree_summary[top_part]["bytes"] += size

    largest.sort(key=lambda pair: pair[0], reverse=True)
    largest = largest[:8]

    # Top-level entries come from the same file list as every other section, so gitignored
    # folders (build output, scratch, caches) cannot crowd real ones out of the capped list.
    if used_git_ls:
        top_dirs = sorted(git_top_dirs, key=str.lower)[:12]
        top_files = sorted(git_top_files, key=str.lower)[:15]
    else:
        top_level = sorted(root_p.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        top_dirs = [p.name + "/" for p in top_level
                    if p.is_dir() and not _skipped_dir(p.name)][:12]
        top_files = [p.name for p in top_level if p.is_file()][:15]

    focus_matches: list[Path] = []
    if focus:
        for path in files:
            rel = relative_display(root_p, path).lower()
            if any(fnmatch.fnmatch(rel, f.lower()) or f.lower() in rel for f in focus):
                focus_matches.append(path)

    changed: list[str] = []
    code, out, _ = _git(root_p, ["--no-pager", "status", "--porcelain=v1", "-z", "--untracked-files=normal"])
    if code == 0:
        changed = _status_rows(out, root_p, Path(info.git_root) if info.git_root else None)

    diff_stat: str | None = None
    if info.git_root:
        code, out, _ = _git(root_p, ["--no-pager", "diff", "--stat", "HEAD"])
        if code == 0 and out.strip():
            diff_stat = out.strip()

    recent: list[str] = []
    code, out, _ = _git(root_p, ["--no-pager", "log", "--oneline", "-5"])
    if code == 0:
        recent = [line for line in out.splitlines() if line.strip()]

    hot: list[tuple[str, int]] = []
    code, out, _ = _git(root_p, ["--no-pager", "log", "--pretty=format:", "--name-only", "--relative", "-n", "200"])
    if code == 0:
        counts: dict[str, int] = {}
        for line in out.splitlines():
            line = line.strip()
            if line and not line.startswith("("):
                counts[line] = counts.get(line, 0) + 1
        hot = sorted(counts.items(), key=lambda pair: pair[1], reverse=True)[:10]

    # Candidate matches with factual reasons
    candidates_dict: dict[str, list[str]] = {}
    for c in changed:
        parts_c = c.split(None, 1)
        if len(parts_c) == 2:
            candidates_dict.setdefault(parts_c[1], []).append(f"git status: {parts_c[0]}")
    for p in focus_matches:
        rel = relative_display(root_p, p)
        candidates_dict.setdefault(rel, []).append("matched focus")

    ext_rows = sorted(by_ext.items(), key=lambda pair: len(pair[1]), reverse=True)
    parts = [f"# Survey: {root_p}"]
    ws = "no git repository"
    if info.git_root:
        flags = "dirty" if info.dirty else "clean"
        ws = f"{info.branch or '?'} @ {info.head or '?'} ({flags}, {info.changed_count or 0} changed)"
    parts.append(f"Workspace: {ws}")
    parts.append(f"Files walked: {len(files)}" + (" (capped)" if truncated_walk else "")
                 + f", total size {format_bytes(total_size)}")
    if top_dirs:
        parts.append("Top-level directories: " + ", ".join(top_dirs))
    if tree_summary:
        sorted_tree = sorted(tree_summary.items(), key=lambda x: x[1]["bytes"], reverse=True)[:10]
        tree_desc = ", ".join(f"{d} ({v['files']} files, {format_bytes(v['bytes'])})" for d, v in sorted_tree)
        parts.append("Layout tree: " + tree_desc)
    if top_files:
        parts.append("Top-level files: " + ", ".join(top_files))
    if ext_rows:
        parts.append("By extension: " + ", ".join(f"{ext} {len(group)}" for ext, group in ext_rows[:12]))
    if largest:
        parts.append("Largest files:")
        parts.extend(f"  {format_bytes(size):>9} {relative_display(root_p, path)}" for size, path in largest)
    if changed:
        parts.append(f"Changed files: {len(changed)}")
        parts.extend(f"  {row}" for row in changed[:15])
        if len(changed) > 15:
            parts.append(f"  ... {len(changed) - 15} more")
    if diff_stat:
        parts.append(f"Diff stat (HEAD):\n  " + "\n  ".join(diff_stat.splitlines()[:10]))
    if recent:
        parts.append("Recent commits:")
        parts.extend(f"  {row}" for row in recent)
    if hot:
        parts.append("Hot spots (last 200 commits):")
        parts.extend(f"  {count:3d}x {path}" for path, count in hot)
    if candidates_dict:
        parts.append("Candidate files (factual reasons):")
        for cpath, reasons in list(candidates_dict.items())[:20]:
            parts.append(f"  {cpath} ({', '.join(reasons)})")
    if focus:
        parts.append(f"Focus {focus}: {len(focus_matches)} match(es)")
        parts.extend(f"  {relative_display(root_p, p)}" for p in focus_matches[:25])
        if len(focus_matches) > 25:
            parts.append(f"  ... {len(focus_matches) - 25} more")
    if not info.git_root:
        report.unknowns.append("no git repository: commit history, diff stat, and ls-files unavailable")
    if truncated_walk:
        report.unknowns.append(f"repository walk capped at max_files={max_files}")
    if report.unknowns:
        parts.append("Unknowns: " + "; ".join(report.unknowns))
    parts.append("")
    parts.append("Suggested next evidence: batch_read on focus files, then grep for the central symbol or error string.")

    text = "\n".join(parts)
    body, truncated, full_bytes = truncate_text(text, max_bytes, style="head")
    if truncated:
        body += f"\n[... survey truncated at {format_bytes(max_bytes)}]"
        if artifacts is not None:
            report.artifacts.append(artifacts.put(text, ".survey.md"))
    report.body = body
    report.budget_bytes = max_bytes
    report.used_bytes = len(body.encode("utf-8", errors="replace"))
    report.budget_tokens = estimate_tokens(body)
    report.coverage = Coverage(
        requested=1, read=1, ok=1, bytes_total=full_bytes, bytes_shown=report.used_bytes,
        truncated=1 if truncated else 0,
    )
    report.summary = {
        "files": len(files), "size": total_size,
        "changed": len(changed),
        "focus_matches": len(focus_matches), "truncated": truncated,
        "git_root": info.git_root,
    }
    if truncated_walk:
        report.unknowns.append(f"repository walk capped at {max_files} files")
    return report


def collect_coverage(requested: int, results: list[ReadResult]) -> Coverage:
    coverage = Coverage(requested=requested, read=len(results))
    for result in results:
        if result.status == "ok":
            coverage.ok += 1
        elif result.status in ("truncated", "lossy"):
            coverage.ok += 1
            coverage.truncated += 1 if result.truncated else 0
            coverage.lossy += 1 if result.status == "lossy" else 0
        elif result.status == "missing":
            coverage.missing += 1
        elif result.status == "skipped":
            coverage.skipped += 1
        elif result.status == "binary":
            coverage.binary += 1
        elif result.status == "stale":
            coverage.stale += 1
        elif result.status == "unchanged":
            coverage.unchanged += 1
        else:
            coverage.failed += 1
        coverage.bytes_total += result.bytes_total or 0
        coverage.bytes_shown += result.bytes_shown
    return coverage

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
import json
import os
import re
import subprocess
import threading
import unicodedata
import time
from pathlib import Path

from .artifacts import ArtifactStore, make_read_handle, parse_read_handle, since_sha as _since_sha
from .budget import BudgetTracker, body_budget, tier
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
    """Read every request concurrently, then fit the batch budget item by item.

    Pass 1 reads each item under its own per-item cap.  Items are then admitted greedily in
    (priority tier, request order): one that fits is kept whole, one larger than the whole body
    budget is cut while at least half of it remains, and any other is deferred whole, its
    original spec carried in ``next:``.  The first item in order is always shown or cut.
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

    total = body_budget(tracker.budget.bytes, len(requests))
    remaining = total
    for i in sorted(range(len(requests)), key=lambda k: (tier(requests[k].priority), k)):
        size = results[i].bytes_shown
        if size <= remaining:
            remaining -= size
        elif size > total and remaining * 2 >= total:
            again = await run(requests[i], remaining)
            if again.status not in ("error", "skipped"):
                results[i] = again  # a failed re-read keeps the pass-1 result
            remaining -= min(remaining, results[i].bytes_shown)
        else:
            request = requests[i]
            source = request.source
            if source is None:
                source = request.path or request.glob or request.pattern or request.label
            meta: dict[str, object] = {"continuation": source}
            if request.allow_outside:
                meta["outside"] = True
            results[i] = ReadResult(
                id="read", kind=request.kind, label=request.label or str(source), path=request.path,
                status="deferred",
                message="not shown: the report budget ran out; listed whole in next:",
                meta=meta,
            )
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
        "git_log": _git_log_request,
        "git_cochange": _git_cochange_request,
        "compare": _compare_request,
        "handle": _handle_request,
        "artifact": _artifact_request,
    }
    if req.kind == "invalid":
        return ReadResult(id="read", kind="invalid", label=req.label, status="error",
                          message=req.error or "invalid spec")
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
        return f"{path}@{req.mode}" + (f":{req.pattern}" if req.mode == "outline" and req.pattern else "")
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
    result.message = (result.message or "") + "; did you mean " + ", ".join(f'"{n}"' for n in hits[:3]) + (
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
            message="binary data (NUL bytes); inspect it with a command through the run tool",
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

    pattern_note: str | None = None
    no_match = False  # a pattern that matched nothing is reported, not counted as ok
    if mode in ("context", "grep"):
        if not req.pattern:
            raise SafetyError(f"{mode} mode requires a pattern")
        body, match_count, pattern_note = _grep_text(
            text,
            req.pattern,
            context=req.context if mode == "context" else 0,
            ignore_case=False,
            number=True,
        )
        if match_count == 0:
            body = f"(no matches for {req.pattern})"
            no_match = True
        meta["matches"] = match_count
        selected_count = body.count("\n") + 1 if body else 0

    elif mode == "block":
        if not req.pattern:
            raise SafetyError("block mode requires a pattern")
        spans, pattern_note = _block_spans(lines, req.pattern)
        if not spans:
            body = f"(no matches for {req.pattern})"
            selected_count = 0
            no_match = True
        else:
            rows: list[str] = []
            selected_count = 0
            for index, (start, end, _) in enumerate(spans):
                if index:
                    rows.append("--")
                rows.extend(f"{n + 1}: {lines[n]}" for n in range(start, end + 1))
                selected_count += end - start + 1
            body = "\n".join(rows)
            capped = [(s, e) for s, e, cut in spans if cut]
            if capped:
                s, e = capped[0]
                meta["block_capped"] = f"block cut at {BLOCK_MAX_LINES} lines; read \"{display}:{e + 2}-{lines_total}\" to continue"
            if len(spans) == 1:
                handle_start, handle_end = spans[0][0] + 1, spans[0][1] + 1
                line_rows = [(n + 1, f"{n + 1}: {lines[n]}") for n in range(spans[0][0], spans[0][1] + 1)]
        meta["matches"] = len(spans)

    elif mode == "outline":
        if req.pattern:  # the agent names the heading lines
            rx, pattern_note = _match_rx(req.pattern, lines=lines)
            picked = [i for i, line in enumerate(lines) if rx.search(line)]
        else:
            picked = _outline_lines(lines, depth=req.depth)
            meta["outline_depth"] = req.depth
        empty = f"(no lines match {req.pattern})" if req.pattern else (
            "(no outline: no indented blocks or headings; name heading lines with @outline:PATTERN)")
        body = "\n".join(_outline_row(n, lines[n]) for n in picked) if picked else empty
        selected_count = len(picked)
        no_match = bool(req.pattern) and not picked

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
            verbatim = [line for _, line in selected]
            body = "\n".join(
                [f"=== [target lines {start_line}-{end_line}: copy verbatim as search, "
                 f"or edit by range with since] ===",
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
            line_rows = [(n, f"{n}: {line}") for n, line in selected]
            body = "\n".join(row for _, row in line_rows)
        selected_count = len(selected)
        if ranges:
            handle_start = ranges[0][0]
            handle_end = ranges[-1][1] if ranges[-1][1] < 2**31 - 1 else lines_total

    effective_cap = min(cap, req.max_bytes) if req.max_bytes else cap
    full_body = body
    full_size = len(full_body.encode("utf-8", errors="replace"))
    summary = None
    kept_count: int | None
    continuation: str | None
    if mode == "auto" and not req.range and line_rows and full_size > effective_cap:
        summary = _outline_summary(lines, effective_cap)
    if summary is not None:
        # A large file read whole is mostly skimmed: show its map and let blocks be read from it.
        body, kept_count, all_rows = summary
        truncated, continuation = True, None
        meta["outline_first"] = True
        if all_rows is not None:
            ref = artifacts.put("\n".join(all_rows), ".outline.txt")
            continuation = f"{ref}:{kept_count + 1}-{len(all_rows)}"
            body += f"\n[... {len(all_rows) - kept_count} more outline line(s): \"{continuation}\"]"
            meta["continuation"] = continuation
    else:
        outlines = None
        if mode in ("auto", "lines") and line_rows and full_size > effective_cap:
            outlines = [
                [(i + 1, _outline_row(i, lines[i])) for i in _outline_lines(lines, depth=d)] for d in (2, 1)
            ]
        body, truncated, continuation, kept_count = _fit_body(
            full_body, line_rows, effective_cap, lines_total, lambda a, b: f"{display}:{a}-{b}",
            outlines=outlines,
        )
    if kept_count is not None:
        selected_count = kept_count
    artifact = (artifacts.put(full_body, ".read.txt")
                if truncated and continuation is None and summary is None else None)

    if req.range is None and handle_start is None:
        handle_start, handle_end = None, None
    handle = make_read_handle(display, sha, handle_start, handle_end)

    status = "truncated" if truncated else ("lossy" if info.lossy else "ok")
    if no_match:
        status = "no_match"
    message = pattern_note
    if info.lossy:
        message = f"decoded as {info.encoding} with replacement characters"
    if summary is not None:
        message = (f"outline only: {lines_total} lines, {format_bytes(info.bytes_total)}, too big for this "
                   f"report; read blocks or ranges from it, or \"{display}:1-{lines_total}\" in parts")
    elif truncated:
        # The continuation is named by the body's cut marker and the report's next: line.
        message = f"body truncated to {format_bytes(effective_cap)}; full file is {format_bytes(info.bytes_total)}"
        if continuation:
            meta["continuation"] = continuation
    if pattern_note and message != pattern_note:
        message = f"{pattern_note}; {message}"
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
        range=(handle_start, handle_end) if handle_start is not None and handle_end is not None else None,
        body=body, hash=sha, bytes_total=info.bytes_total, bytes_shown=shown,
        lines_total=lines_total, lines_shown=selected_count,
        truncated=truncated, status=status, message=message, handle=handle,
        artifact=artifact, meta=meta,
    )


OUTLINE_SUMMARY_BYTES = 6 * 1024  # an outline-first read shows depth 2 only when it fits this
OUTLINE_ROW_CHARS = 160


def _outline_row(index: int, line: str) -> str:
    """A numbered outline row, clipped: an outline names places, it does not quote them."""
    row = f"{index + 1}: {line}"
    return row if len(row) <= OUTLINE_ROW_CHARS else row[:OUTLINE_ROW_CHARS] + " …"


def _outline_summary(lines: list[str], cap: int) -> tuple[str, int, list[str] | None] | None:
    """The richest outline of *lines* that fits, cut with a count when even depth 1 does not;
    None when the file has no outline."""
    rows: list[str] = []
    for depth in (2, 1):
        rows = [_outline_row(i, lines[i]) for i in _outline_lines(lines, depth=depth)]
        if not rows:
            return None
        if len("\n".join(rows).encode("utf-8", errors="replace")) <= min(cap - 64, OUTLINE_SUMMARY_BYTES):
            return "\n".join(rows), len(rows), None
    if len("\n".join(rows).encode("utf-8", errors="replace")) <= cap - 64:
        return "\n".join(rows), len(rows), None
    kept: list[str] = []
    used = 0
    for row in rows:
        size = len(row.encode("utf-8", errors="replace")) + 1
        if used + size > cap - 128:
            break
        kept.append(row)
        used += size
    return "\n".join(kept), len(kept), rows


def _fit_body(
    full_body: str,
    line_rows: list[tuple[int, str]] | None,
    cap: int,
    lines_total: int,
    next_ref,  # (first_line, last_line) -> the spec that reads the rest
    *,
    outlines: list[list[tuple[int, str]]] | None = None,  # candidate outlines, richest first
) -> tuple[str, bool, str | None, int | None]:
    """Cut *full_body* to *cap* bytes: on a line boundary with a continuation when rows are known.

    With *outlines*, the cut spends its leftover room on an outline of the lines it did not show.
    Returns (body, truncated, continuation, rows_kept).
    """
    if line_rows and len(full_body.encode("utf-8", errors="replace")) > cap:
        def _size(text: str) -> int:
            return len(text.encode("utf-8", errors="replace"))

        def _outline_marker(first: int, last: int, continuation: str, end: int) -> str:
            return (
                f"[... truncated: showed lines {first}-{last} of {lines_total}; "
                f"read \"{continuation}\" for the rest; outline of lines {last + 1}-{end}:]"
            )

        first_n, end = line_rows[0][0], line_rows[-1][0]
        limit = max(64, cap - 160)
        if outlines:
            reserve = min(sum(_size(row) + 1 for n, row in outlines[-1] if n > first_n), cap // 3)
            longest = _size(_outline_marker(first_n, end, next_ref(end, end), end)) + 48
            limit = max(64, cap - longest - reserve)
        kept: list[tuple[int, str]] = []
        used = 0
        for n, row in line_rows:
            size = _size(row) + 1
            if kept and used + size > limit:
                break
            kept.append((n, row))
            used += size
        first, last = kept[0][0], kept[-1][0]
        continuation = next_ref(last + 1, end)
        body = "\n".join(row for _, row in kept) + (
            f"\n[... truncated: showed lines {first}-{last} of {lines_total}; "
            f"read \"{continuation}\" for the rest]"
        )
        if outlines:
            marker = _outline_marker(first, last, continuation, end)
            room = cap - used - _size(marker)
            candidates = [[row for n, row in rows if last < n <= end] for rows in outlines]
            picked: list[str] = []
            omitted = 0
            for candidate in candidates:
                if sum(_size(row) + 1 for row in candidate) <= room:
                    picked = candidate
                    break
            else:
                budget_left = room - 40
                taken = 0
                for row in candidates[-1]:
                    if _size(row) + 1 > budget_left:
                        break
                    budget_left -= _size(row) + 1
                    taken += 1
                picked = candidates[-1][:taken]
                omitted = len(candidates[-1]) - taken
            if picked:
                body = "\n".join([*(row for _, row in kept), marker, *picked])
                if omitted:
                    body += f"\n[... {omitted} more outline line(s)]"
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
    note: str | None = None
    if req.pattern:
        body, count, note = _grep_text(text, req.pattern, context=req.context,
                                       ignore_case=req.ignore_case, number=True)
        body = body or f"(no matches for {req.pattern})"
        shown_lines = body.count("\n") + 1 if count else 0
        meta: dict[str, object] = {"matches": count}
    else:
        selected = select_lines(lines, parse_range(req.range) if req.range else [])
        line_rows = [(n, f"{n}: {line}") for n, line in selected]
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
        status="truncated" if truncated else ("no_match" if req.pattern and not shown_lines else "ok"),
        body=body, bytes_total=len(data), bytes_shown=len(body.encode("utf-8", errors="replace")),
        lines_total=len(lines), lines_shown=kept if kept is not None else shown_lines,
        truncated=truncated, meta=meta,
        message=note,  # a continuation is named by the body's cut marker and the next: line
    )


# ---------------------------------------------------------------------------
# Structure without language knowledge: indentation, blank lines and character
# classes only. No keywords, bracket characters, file extensions or names.
# ---------------------------------------------------------------------------
BLOCK_MAX_LINES = 400
BLOCK_MAX_MATCHES = 5
_QUOTES = "\"'`"


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


def _block_end(lines: list[str], start: int, limit: int | None = None) -> int:
    """End of the block opened at ``start`` (0-based, inclusive).

    Lines deeper than the match belong to it. Before any deeper line, a lone token at the
    match's indentation continues the header (an opener on its own line). After the body, a
    line at the match's indentation that starts with punctuation and is followed by deeper
    lines continues it (a multi-line header's closing part); a lone punctuation-only line
    closes it and is included; anything else ends the block before that line. A flat heading
    with no deeper lines opens a section that runs to the next heading of its level or above.
    """
    base = _width(lines[start])
    if limit is None:
        limit = min(len(lines), start + BLOCK_MAX_LINES)
    stop = limit

    def next_nonblank(k: int) -> int | None:
        for m in range(k + 1, stop):
            if lines[m].strip():
                return m
        return None

    end = start
    seen_body = False
    j = start + 1
    while j < stop:
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
    if not seen_body and _flat_header(lines, start):
        return _section_end(lines, start, stop)
    return end


def _lead_run(line: str) -> tuple[str, int] | None:
    """(character, count) for a line that starts, unindented, with a run of one repeated
    punctuation or symbol character and then a space ("## Title"), else None."""
    if not line or not _starts_with_punct(line) or line[0] in " \t":
        return None
    char = line[0]
    count = len(line) - len(line.lstrip(char))
    if count >= len(line) or line[count] != " ":
        return None
    return char, count


def _underline(line: str) -> str | None:
    """The character of a line made only of one punctuation or symbol character, 3 or more."""
    text = line.rstrip()
    if len(text) >= 3 and len(set(text)) == 1 and _starts_with_punct(text):
        return text[0]
    return None


def _nearest_text(lines: list[str], i: int, step: int) -> str | None:
    j = i + step
    while 0 <= j < len(lines) and not lines[j].strip():
        j += step
    return lines[j] if 0 <= j < len(lines) else None


def _flat_headings(lines: list[str]) -> dict[int, tuple[str, int]]:
    """Every flat heading: line -> (family, level).

    A lead-run heading ("## Title") stands alone between blank lines; its family is the
    character, its level the run length.  A line preceded by a blank line and underlined by a
    line of one repeated punctuation or symbol character is a heading too; underline
    characters rank in the order they first appear (family "u").  Lines whose nearest
    non-blank neighbour starts with the same lead run are list items, not headings.
    """
    heads: dict[int, tuple[str, int]] = {}
    ranks: dict[str, int] = {}
    for i, line in enumerate(lines):
        if i > 0 and lines[i - 1].strip():
            continue
        if line.strip() and line[0] not in " \t" and i + 1 < len(lines):
            char = _underline(lines[i + 1])
            if char and lines[i + 1][0] == char and not line.startswith(char):
                heads[i] = ("u", ranks.setdefault(char, len(ranks) + 1))
                continue
        run = _lead_run(line)
        if run is None or (i + 1 < len(lines) and lines[i + 1].strip()):
            continue
        neighbours = (_nearest_text(lines, i, -1), _nearest_text(lines, i, 1))
        if any(other is not None and _lead_run(other) == run for other in neighbours):
            continue  # bullets come in runs
        heads[i] = run
    return heads


_FLAT = threading.local()


def _flat_map(lines: list[str]) -> dict[int, tuple[str, int]]:
    """``_flat_headings`` of *lines*, computed once per list (reads run in threads)."""
    if getattr(_FLAT, "lines", None) is not lines:
        _FLAT.lines, _FLAT.heads = lines, _flat_headings(lines)
    return _FLAT.heads


def _flat_header(lines: list[str], i: int) -> tuple[str, int] | None:
    """(family, level) when line *i* is a flat heading: the structure of a file whose
    structure is not indented."""
    return _flat_map(lines).get(i)


def _section_end(lines: list[str], start: int, limit: int) -> int:
    """End of a flat section: the line before the next heading of its family at the same
    or a higher level, trailing blank lines dropped."""
    family, level = _flat_header(lines, start) or ("", 0)
    end = start
    for j in range(start + 1, limit):
        other = _flat_header(lines, j)
        if other and other[0] == family and other[1] <= level:
            break
        end = j
    while end > start and not lines[end].strip():
        end -= 1
    return end


def _flat_outline(lines: list[str]) -> list[int]:
    return sorted(_flat_map(lines))


def _block_cap(lines: list[str], start: int, end: int) -> bool:
    """True when the same scan without the line limit ends after *end*."""
    if start + BLOCK_MAX_LINES >= len(lines):
        return False
    return _block_end(lines, start, len(lines)) > end


BLOCK_WINDOW_LINES = 100


def _hit_window(lines: list[str], hit: int) -> set[int]:
    """Line indexes shown for one grep hit in blocks mode: the largest enclosing block or
    section of at most BLOCK_WINDOW_LINES lines, else the hit's neighbourhood plus the
    opening line of the smallest enclosing block."""
    openers: list[int] = []
    if _block_end(lines, hit) > hit:
        openers.append(hit)
    narrowest = _width(lines[hit])
    for k in range(hit - 1, max(-1, hit - BLOCK_MAX_LINES - 1), -1):
        if not lines[k].strip():
            continue
        width = _width(lines[k])
        if width < narrowest:
            narrowest = width
            openers.append(k)
        elif _flat_header(lines, k):
            openers.append(k)
    kept = [(k, _block_end(lines, k)) for k in openers]
    kept = [(k, end) for k, end in kept if end >= hit]
    fits = [(k, end) for k, end in kept if end - k + 1 <= BLOCK_WINDOW_LINES]
    if fits:
        start, end = max(fits, key=lambda span: span[1] - span[0])
        return set(range(start, end + 1))
    window = set(range(max(0, hit - 5), min(len(lines), hit + 6)))
    if kept:
        window.add(min(kept, key=lambda span: span[1] - span[0])[0])
    return window


def _block_spans(lines: list[str], pattern: str) -> tuple[list[tuple[int, int, bool]], str | None]:
    """Blocks opened by lines matching *pattern*, or by line N when the pattern is a number."""
    if re.fullmatch(r"\d+", pattern.strip()):
        n = int(pattern)
        if not 1 <= n <= len(lines):
            raise SafetyError(f"block line {n} is outside the file ({len(lines)} lines)")
        end = _block_end(lines, n - 1)
        return [(n - 1, end, _block_cap(lines, n - 1, end))], None
    rx, note = _match_rx(pattern, lines=lines)
    spans: list[tuple[int, int, bool]] = []
    for i, line in enumerate(lines):
        if not rx.search(line):
            continue
        if spans and i <= spans[-1][1]:
            continue  # already inside the previous block
        end = _block_end(lines, i)
        spans.append((i, end, _block_cap(lines, i, end)))
        if len(spans) >= BLOCK_MAX_MATCHES:
            break
    return spans, note


def _outline_lines(lines: list[str], *, depth: int) -> list[int]:
    """Lines that open an indented block, nested at most ``depth`` levels deep, plus flat
    headings (see ``_flat_header``), so unindented prose has an outline too.

    A lone token that opens a block (an opener on its own line) is shown by the line above it;
    a line starting with punctuation continues an earlier header and is not shown.
    """
    return sorted(set(_indent_outline(lines, depth=depth)) | set(_flat_outline(lines)))


def _indent_outline(lines: list[str], *, depth: int) -> list[int]:
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


LITERAL_NOTE = "pattern matched as literal text"


def _match_rx(
    pattern: str, *, ignore_case: bool = False, lines: list[str] | None = None,
) -> tuple[re.Pattern[str], str | None]:
    """A regex for *pattern*, or its literal text when it is not a valid regex.

    With *lines* (a file-local search), a valid regex that matches no line while the
    literal text does is also matched literally: pasted code such as ``name(arg)`` is a
    valid regex that never matches itself.  Returns (regex, note when literal).
    """
    if not pattern:
        raise SafetyError("search pattern must not be empty")
    flags = re.IGNORECASE if ignore_case else 0
    literal = re.compile(re.escape(pattern), flags)
    try:
        rx = re.compile(pattern, flags)
    except re.error as exc:
        return literal, f"{LITERAL_NOTE} (not a valid regex: {exc})"
    if (lines is not None and literal.pattern != rx.pattern
            and not any(rx.search(line) for line in lines)
            and any(literal.search(line) for line in lines)):
        return literal, f"{LITERAL_NOTE} (the regex matched nothing)"
    return rx, None


def _grep_text(
    text: str,
    pattern: str,
    *,
    context: int,
    ignore_case: bool,
    number: bool,
) -> tuple[str, int, str | None]:
    lines = text.splitlines()
    rx, note = _match_rx(pattern, ignore_case=ignore_case, lines=lines)
    hits = [i for i, line in enumerate(lines) if rx.search(line)]
    if not hits:
        return "", 0, note
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
        if previous is not None and idx > previous + 1 and context > 0:
            out.append("--")
        marker = ":" if idx in hit_set else "-"
        out.append(f"{idx + 1}{marker} {lines[idx]}" if number else lines[idx])
        previous = idx
    return "\n".join(out), len(hits), note


def _split_scope(pattern: str, root: Path, allow_outside: bool) -> tuple[str, list[str]]:
    """Read "RE in PATH [PATH..]" as a scoped grep when every word after the last " in " exists."""
    head, sep, tail = pattern.rpartition(" in ")
    words = tail.split()
    if not sep or not head or not words:
        return pattern, []
    for word in words:
        try:
            if not _expand_paths(root, word) or not all(
                resolve_path(root, p, allow_outside=allow_outside).exists() for p in _expand_paths(root, word)
            ):
                return pattern, []
        except (OSError, SafetyError):
            return pattern, []
    return head, words


def _grep_request(req: ReadRequest, root: Path, cap: int, artifacts: ArtifactStore) -> ReadResult:
    if not req.pattern:
        raise SafetyError("grep requires a pattern")
    pattern, scope = req.pattern, req.paths
    if not scope:
        pattern, scope = _split_scope(pattern, root, req.allow_outside)
    if req.fixed:
        rx, literal_note = _compile_pattern(pattern, fixed=True, ignore_case=req.ignore_case), None
    else:
        rx, literal_note = _match_rx(pattern, ignore_case=req.ignore_case)  # no second repo scan
    path_specs = scope or ["."]
    files: list[Path] = []
    seen: set[str] = set()
    truncated_listing = False
    ignored_paths = 0

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
                listed = _git_listed(resolved, ignored=req.include_ignored)
                if listed is not None:
                    files.extend(listed)
                    if not req.include_ignored:
                        code, skipped_out, _ = _git(resolved, ["ls-files", "--others", "--ignored",
                                                              "--exclude-standard", "--directory", "-z"])
                        if code == 0:
                            ignored_paths += sum(1 for name in skipped_out.split("\0") if name)
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
    file_hits: list[tuple[str, int]] = []
    hit_paths: list[Path] = []
    match_count = 0
    shown_matches = 0
    scanned = 0
    skipped = 0
    skipped_binary = 0
    want_rows = req.mode != "files"
    for path in files:
        try:
            if not req.allow_outside and path.is_symlink() and not path_is_within(root, path.resolve()):
                skipped += 1
                continue  # a link inside the tree that points outside cwd
            if path.stat().st_size > 4 * 1024 * 1024:
                skipped += 1
                continue
            data = path.read_bytes()
        except OSError:
            skipped += 1
            continue
        info = decode_bytes(data)
        if info.binary:
            skipped_binary += 1
            skipped += 1
            continue
        scanned += 1
        rel = relative_display(root, path)
        lines = info.text.splitlines()
        hits = [i for i, line in enumerate(lines) if rx.search(line)]
        if not hits:
            continue
        file_hits.append((rel, len(hits)))
        hit_paths.append(path)
        match_count += len(hits)

    quotas = _fair_quota([n for _, n in file_hits], req.max_matches) if want_rows else [0] * len(file_hits)
    for path, (rel, total_hits), quota in zip(hit_paths, file_hits, quotas):
        if not quota:
            continue
        try:
            lines = decode_bytes(path.read_bytes()).text.splitlines()
        except OSError:
            continue
        hits = [i for i, line in enumerate(lines) if rx.search(line)][:quota]
        if not hits:
            continue
        shown_matches += len(hits)
        count = f"{len(hits)} of {total_hits}" if len(hits) < total_hits else str(total_hits)
        out.append(f"=== {rel} ({count}) ===")
        selected: set[int] = set()
        windowed = req.blocks and want_rows and match_count <= 20
        for i in hits:
            if windowed:
                selected.update(_hit_window(lines, i))
            else:
                selected.update(range(max(0, i - req.context), min(len(lines), i + req.context + 1)))
        previous = None
        hit_set = set(hits)
        for idx in sorted(selected):
            if previous is not None and idx > previous + 1 and (req.context > 0 or windowed):
                out.append("--")
            marker = ":" if idx in hit_set else "-"
            out.append(f"{idx + 1}{marker} {lines[idx]}")  # path is in the === header ===
            previous = idx

    def _size(text: str) -> int:
        return len(text.encode("utf-8", errors="replace"))

    census_rows = [f"{rel} ({n})" for rel, n in file_hits]
    # The === headers name every file with rows; the list is needed only when some are cut or left out.
    rows_cut = not want_rows or any(q < n for q, (_, n) in zip(quotas, file_hits))
    census = "\n".join(census_rows) if rows_cut else ""
    full_rows = "\n".join(out)
    truncated, artifact, continuation = False, None, None
    if not file_hits:
        body = f"(no matches for {req.pattern})"
        full_bytes = _size(body)
    elif census and _size(census) + 1 > cap - 64:
        census_artifact = artifacts.put(census, ".grep-files.txt")
        artifact = census_artifact
        used = 0
        shown_census = 0
        for row in census_rows:
            if used + _size(row) + 1 > cap - 128:
                break
            used += _size(row) + 1
            shown_census += 1
        body_lines = census_rows[:shown_census]
        body_lines.append(f"[... {len(census_rows) - shown_census} more file(s); full list: {census_artifact}]")
        if out:
            rows_artifact = artifacts.put(full_rows, ".grep.txt")
            body_lines.append(f"[... match lines: {rows_artifact}]")
        body = "\n".join(body_lines)
        continuation = f"{census_artifact}:{shown_census + 1}-{len(file_hits)}"
        truncated = True
        full_bytes = _size(census) + (_size(full_rows) + 1 if out else 0)
    else:
        body = census
        full_bytes = _size(census) + (_size(full_rows) + 1 if out else 0)
        if out:
            clip = max(20, req.max_line)
            rows = [(i + 1, row if len(row) <= clip else f"{row[:clip]} …[+{len(row) - clip} chars]")
                    for i, row in enumerate(out)]
            shown = "\n".join(row for _, row in rows)
            room = cap - (_size(census) + 1 if census else 0)
            if _size(shown) > room:
                # Cut on a report line, keeping the full rows as an artifact the continuation reads by line.
                artifact = artifacts.put(full_rows, ".grep.txt")
                shown, truncated, continuation, _ = _fit_body(
                    shown, rows, room, len(out), lambda a, b: f"{artifact}:{a}-{b}"
                )
            body = f"{census}\n{shown}" if census else shown
    return ReadResult(
        id="read", kind="grep", label=req.label or f"grep:{req.pattern}",
        status="truncated" if truncated else ("ok" if file_hits else "no_match"),
        body=body, bytes_total=full_bytes, bytes_shown=len(body.encode("utf-8", errors="replace")),
        lines_total=len(out), lines_shown=shown_matches, truncated=truncated,
        message="; ".join(m for m in (
            literal_note or "",
            f"blocks skipped: {match_count} matches over 20; narrow the pattern or paths"
            if req.blocks and want_rows and match_count > 20 else "",
            f"showing {shown_matches} of {match_count} matches (max_matches={req.max_matches})"
            if want_rows and shown_matches < match_count else "",
            f"{len(files)} file(s) capped at max_files={req.max_files}" if truncated_listing else "",
            f"{excluded} file(s) excluded" if excluded else "",
            f"{skipped} file(s) skipped (binary, over 4MB, unreadable or outside cwd)" if skipped else "",
            f"{ignored_paths} gitignored path(s) not searched; add \"ignored\": true to a grep object to include them"
            if ignored_paths else "",
        ) if m) or None,
        artifact=artifact,
        meta={
            "matches": match_count, "matches_shown": shown_matches, "files_with_hits": len(file_hits),
            "files_scanned": scanned,
            "files_candidates": len(files), "skipped_binary": skipped_binary, "files_skipped": skipped,
            "truncated_listing": truncated_listing, "excluded": excluded,
            **({"ignored_skipped": ignored_paths} if ignored_paths else {}),
            **({"continuation": continuation} if continuation else {}),
        },
    )


def _fair_quota(counts: list[int], total: int) -> list[int]:
    """Rows per file so no file starves the rest: an even share, small files' leftovers
    passed on; with more files than rows, one row each in file order."""
    quotas = [0] * len(counts)
    if total <= 0 or not counts:
        return quotas
    if len(counts) >= total:
        for i in range(total):
            quotas[i] = 1
        return quotas
    left = total
    order = sorted(range(len(counts)), key=lambda i: counts[i])
    for k, i in enumerate(order):
        quotas[i] = min(counts[i], left // (len(order) - k))
        left -= quotas[i]
    for i, n in enumerate(counts):  # integer-division remainder, in file order
        if left <= 0:
            break
        if quotas[i] < n:
            quotas[i] += 1
            left -= 1
    return quotas


def _git_listed(base: Path, ignored: bool = False) -> list[Path] | None:
    """Tracked plus untracked files under *base* (ignored ones only when *ignored*), or None outside git."""
    args = ["ls-files", "--cached", "--others", "-z"] if ignored else [
        "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    code, out, _ = _git(base, args)
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
    seen_files: set[str] = set()
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
        key = os.path.normcase(str(candidate))
        if key in seen_files:
            continue
        seen_files.add(key)
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


def _git_history_spec(req: ReadRequest, root: Path) -> str:
    """The one pathspec a history read names: cwd-relative inside cwd, absolute outside it."""
    path = resolve_path(root, req.paths[0], allow_outside=req.allow_outside, must_exist=False)
    return relative_display(root, path)


def _git_history_result(
    req: ReadRequest, kind: str, label: str, out: str, cap: int, artifacts: ArtifactStore,
    suffix: str, meta: dict[str, object] | None = None, note: str = "log",
) -> ReadResult:
    """A history body cut on a line boundary; the full text is kept as an artifact the continuation reads."""
    _, truncated, full_bytes = truncate_text(out, cap, style="head")
    lines = out.split("\n")
    meta = dict(meta or {})
    if not truncated:
        return ReadResult(
            id="read", kind=kind, label=label, status="ok", body=out,
            bytes_total=full_bytes, bytes_shown=len(out.encode("utf-8", errors="replace")),
            lines_total=len(lines), lines_shown=len(lines), meta=meta,
        )
    kept = 0
    used = 0
    for line in lines:
        size = len(line.encode("utf-8", errors="replace")) + 1
        if used + size > max(64, cap - 64):
            break
        used += size
        kept += 1
    body = "\n".join(lines[:kept])
    artifact = artifacts.put(out, suffix)
    continuation = f"{artifact}:{kept + 1}-{len(lines)}"
    meta["continuation"] = continuation
    return ReadResult(
        id="read", kind=kind, label=label, status="truncated", body=body,
        bytes_total=full_bytes, bytes_shown=len(body.encode("utf-8", errors="replace")),
        lines_total=len(lines), lines_shown=kept, truncated=True, artifact=artifact,
        message=f"{note} truncated at {format_bytes(cap)}; continue with \"{continuation}\"",
        meta=meta,
    )


def _git_log_request(req: ReadRequest, root: Path, cap: int, artifacts: ArtifactStore) -> ReadResult:
    spec = _git_history_spec(req, root)
    label = req.label or f"git:log:{spec}" + (f":{req.range}" if req.range else "")
    if req.range:
        first, _, last = req.range.partition("-")
        args = ["--literal-pathspecs", "--no-pager", "log", "-L", f"{first},{last}:{spec}",
                "--format=%h %ad %s", "--date=short", "-n", "5"]
    else:
        args = ["--literal-pathspecs", "--no-pager", "log", "--follow", "--format=%h %ad %s",
                "--date=short", "-n", "15", "--", spec]
    code, out, err = _git(root, args)
    if code != 0:
        return ReadResult(id="read", kind="git_log", label=label, status="error",
                          message=err.strip() or f"git log failed ({code})")
    out = out.rstrip("\n")
    if not out.strip():
        return ReadResult(id="read", kind="git_log", label=label, status="ok",
                          body=f"(no commits touch {spec})")
    return _git_history_result(req, "git_log", label, out, cap, artifacts, ".log.txt")


def _git_cochange_request(req: ReadRequest, root: Path, cap: int, artifacts: ArtifactStore) -> ReadResult:
    spec = _git_history_spec(req, root)
    label = req.label or f"git:cochange:{spec}"
    args = ["--literal-pathspecs", "--no-pager", "log", "--full-diff", "--format=%x00%h", "--name-only",
            "--relative", "-n", "200", "--", spec]
    code, out, err = _git(root, args)
    if code != 0:
        return ReadResult(id="read", kind="git_cochange", label=label, status="error",
                          message=err.strip() or f"git log failed ({code})")
    chunks = [chunk for chunk in out.split("\0") if chunk.strip()]
    if not chunks:
        return ReadResult(id="read", kind="git_cochange", label=label, status="ok",
                          body=f"(no commits touch {spec})", meta={"commits": 0, "files": 0})
    counts: dict[str, int] = {}
    for chunk in chunks:
        names = [line.strip() for line in chunk.splitlines()[1:] if line.strip()]
        for name in dict.fromkeys(names):
            if name != spec:
                counts[name] = counts.get(name, 0) + 1
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    rows = [f"{len(chunks)} commit(s) touch {spec} (newest 200 searched; files under cwd)"]
    rows.extend(f"  {count}x {name}" for name, count in ranked[:20])
    if len(ranked) > 20:
        rows.append(f"  ... {len(ranked) - 20} more file(s)")
    return _git_history_result(
        req, "git_cochange", label, "\n".join(rows), cap, artifacts, ".cochange.txt",
        meta={"commits": len(chunks), "files": len(counts)}, note="cochange",
    )


def _git_diff_request(req: ReadRequest, root: Path, cap: int, artifacts: ArtifactStore) -> ReadResult:
    args = ["--no-pager", "diff", "--no-color", "--no-ext-diff",
            "--stat" if req.stat else f"-U{max(0, req.context)}"]
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
    files = [] if req.stat else sorted({line[6:].strip() for line in out.splitlines()
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
        if isinstance(start, int) and isinstance(end, int):
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
_RUN_STEP = re.compile(r"^(\s*)(?:-\s+)?run:\s*(.*)$")
_MAKE_TARGET = re.compile(
    r"^([A-Za-z0-9_][A-Za-z0-9_.-]*(?:[ \t]+[A-Za-z0-9_][A-Za-z0-9_.-]*)*)[ \t]*::?(?![=:])"
)


def _cut_command(text: str) -> str:
    return text if len(text) <= 160 else text[:157] + "..."


class _SourceNotRead(Exception):
    """A command source exists but was not read; the message says why."""


def _read_source(path: Path) -> str | None:
    """Return the text of `path`, or None when absent; raise _SourceNotRead when present but unread or its presence cannot be checked."""
    try:
        if not path.is_file():
            return None
        if path.stat().st_size > 1024 * 1024:
            raise _SourceNotRead("over 1 MB")
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise _SourceNotRead("unreadable") from exc


def _workflow_steps(text: str) -> list[str]:
    lines = text.splitlines()
    steps: list[str] = []
    i = 0
    while i < len(lines):
        m = _RUN_STEP.match(lines[i])
        i += 1
        if not m:
            continue
        column = lines[i - 1].index("run:")
        value = m.group(2).strip()
        if value[:1] in ("|", ">"):
            block: list[str] = []
            while i < len(lines):
                line = lines[i]
                if line.strip() and len(line) - len(line.lstrip()) <= column:
                    break
                if line.strip():
                    block.append(line.strip())
                i += 1
            if not block:
                continue
            if value[0] == "|":
                command = block[0] + (f" (+{len(block) - 1} more lines)" if len(block) > 1 else "")
            else:
                command = " ".join(block)
        else:
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if not value:
                continue
            command = value
        steps.append(_cut_command(command))
    return list(dict.fromkeys(steps))


def _survey_commands(root_p: Path) -> list[str]:
    rows: list[str] = []
    workflows = root_p / ".github" / "workflows"
    try:
        names = sorted(
            (p.name for p in workflows.iterdir() if p.suffix in (".yml", ".yaml")),
        ) if workflows.is_dir() else []
    except OSError:
        names = []
        rows.append("  .github/workflows: not read (unreadable)")
    for name in names[:5]:
        try:
            text = _read_source(workflows / name)
        except _SourceNotRead as exc:
            rows.append(f"  .github/workflows/{name}: steps not read ({exc})")
            continue
        steps = _workflow_steps(text) if text is not None else []
        if not steps:
            continue
        rows.append(f"  .github/workflows/{name}:")
        rows.extend(f"    {s}" for s in steps[:8])
        if len(steps) > 8:
            rows.append(f"    +{len(steps) - 8} more")
    if len(names) > 5:
        rows.append(f"  +{len(names) - 5} more workflow file(s)")

    for make_name in ("Makefile", "makefile", "GNUmakefile"):
        try:
            text = _read_source(root_p / make_name)
        except _SourceNotRead as exc:
            rows.append(f"  {make_name}: targets not read ({exc})")
            break
        if text is None:
            continue
        targets: list[str] = []
        for line in text.splitlines():
            if not line or line[0] in " \t":
                continue
            m = _MAKE_TARGET.match(line)
            if m:
                targets.extend(m.group(1).split())
        targets = list(dict.fromkeys(targets))
        if targets:
            shown = ", ".join(f"make {t}" for t in targets[:15])
            more = f", +{len(targets) - 15} more" if len(targets) > 15 else ""
            rows.append(f"  {make_name}: {shown}{more}")
        break

    try:
        text = _read_source(root_p / "package.json")
    except _SourceNotRead as exc:
        text = None
        rows.append(f"  package.json: scripts not read ({exc})")
    if text is not None:
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if not isinstance(data, dict):
            rows.append("  package.json: scripts not read (invalid JSON)")
        else:
            scripts = data.get("scripts")
            items = [(k, v) for k, v in scripts.items() if isinstance(v, str)] if isinstance(scripts, dict) else []
            if items:
                rows.append("  package.json scripts:")
                rows.extend(f"    {k}: {_cut_command(v)}" for k, v in items[:15])
                if len(items) > 15:
                    rows.append(f"    +{len(items) - 15} more")
    if rows:
        rows.insert(0, "Commands (CI workflow steps, Makefile targets, package.json scripts):")
    return rows


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
    dir_counts: dict[str, int] = {}  # folder -> files anywhere under it
    dir_files: dict[str, int] = {}  # folder -> files directly in it
    dir_kids: dict[str, set[str]] = {}  # folder -> its folders

    def count_folders(rel_path: str) -> None:
        parts_f = rel_path.split("/")
        for depth in range(1, len(parts_f)):
            folder = "/".join(parts_f[:depth])
            dir_counts[folder] = dir_counts.get(folder, 0) + 1
            if depth > 1:
                dir_kids.setdefault("/".join(parts_f[:depth - 1]), set()).add(folder)
        if len(parts_f) > 1:
            parent = "/".join(parts_f[:-1])
            dir_files[parent] = dir_files.get(parent, 0) + 1

    def chain(folder: str) -> str:
        """A folder holding only one folder is shown with it: src/main/java as one row."""
        while not dir_files.get(folder) and len(dir_kids.get(folder, ())) == 1:
            folder = next(iter(dir_kids[folder]))
        return folder

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
                count_folders(raw_rel.replace("\\", "/"))
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
        for walked in files:
            count_folders(relative_display(root_p, walked))

    total_size = 0
    for path in files:
        try:
            total_size += path.stat().st_size
        except OSError:
            continue

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
    code, out, _ = _git(root_p, ["--no-pager", "status", "--porcelain=v1", "-z", "--untracked-files=normal",
                                 "--", "."])
    if code == 0:
        changed = _status_rows(out, root_p, Path(info.git_root) if info.git_root else None)

    line_counts: dict[str, str] = {}  # changed path -> "+added -deleted" against HEAD
    added_total = deleted_total = 0
    if info.git_root and changed:
        code, out, _ = _git(root_p, ["--no-pager", "diff", "--numstat", "--relative", "HEAD", "--", "."])
        if code == 0:
            for row in out.splitlines():
                cells = row.split("\t")
                if len(cells) != 3:
                    continue
                if cells[0].isdigit() and cells[1].isdigit():
                    added_total += int(cells[0])
                    deleted_total += int(cells[1])
                    line_counts[cells[2]] = f"+{cells[0]} -{cells[1]}"
                else:
                    line_counts[cells[2]] = "binary"

    recent: list[str] = []
    code, out, _ = _git(root_p, ["--no-pager", "log", "--oneline", "-5"])
    if code == 0:
        recent = [line for line in out.splitlines() if line.strip()]

    hot: list[tuple[str, int]] = []
    counts: dict[str, int] = {}
    hubs: set[str] = set()
    groups: list[tuple[int, list[str]]] = []
    commit_log: list[tuple[str, list[str]]] = []  # ("<hash> <date> <subject>", files), newest first
    log_ran = False
    code, out, _ = _git(root_p, ["--no-pager", "log", "--format=%x00%h %ad %s", "--date=short", "--name-only",
                                 "--relative", "-n", "200"])
    if code == 0:
        log_ran = True
        commits: list[list[str]] = []
        for chunk in out.split("\0"):
            if not chunk.strip():
                continue
            head, _, listing = chunk.partition("\n")
            names = list(dict.fromkeys(
                line.strip() for line in listing.splitlines()
                if line.strip() and not line.strip().startswith("(")
            ))
            if names:
                commits.append(names)
                commit_log.append((head.strip(), names))
        pair_counts: dict[tuple[str, str], int] = {}
        for names in commits:
            for name in names:
                counts[name] = counts.get(name, 0) + 1
            if len(names) > 30:
                continue
            ordered = sorted(names)
            for i, left in enumerate(ordered):
                for right in ordered[i + 1:]:
                    pair_counts[(left, right)] = pair_counts.get((left, right), 0) + 1
        hot = sorted(counts.items(), key=lambda pair: pair[1], reverse=True)[:10]
        hubs, groups = _cochange_groups(commits, counts, pair_counts)

    if not info.git_root:
        report.unknowns.append("no git repository: commit history, diff stat, and ls-files unavailable")
    if truncated_walk:
        report.unknowns.append(f"repository walk capped at max_files={max_files}")

    parts = [f"# Survey: {root_p}"]
    ws = "no git repository"
    if info.git_root:
        flags = "dirty" if info.dirty else "clean"
        ws = f"{info.branch or '?'} @ {info.head or '?'} ({flags}, {info.changed_count or 0} changed)"
    parts.append(f"Workspace: {ws}")
    parts.append(f"Files walked: {len(files)}" + (" (capped)" if truncated_walk else "")
                 + f", total size {format_bytes(total_size)}")
    if report.unknowns:  # first, so a cut survey still says what it could not see
        parts.append("Unknowns: " + "; ".join(report.unknowns))
    top_folders = sorted((f for f in dir_counts if "/" not in f), key=lambda f: (-dir_counts[f], f))
    if top_folders:
        churn: dict[str, int] = {}
        for name, count in counts.items():
            for folder in top_folders:
                if name.startswith(folder + "/"):
                    churn[folder] = churn.get(folder, 0) + count
                    break
        parts.append("Tree (files per folder, depth 2; churn = file changes in the last 200 commits):")
        shown_top: list[str] = []
        for folder in top_folders[:20]:
            label = chain(folder)
            shown_top.append(label)
            parts.append(f"  {label}/ {dir_counts[folder]}" + (f", churn {churn[folder]}" if churn.get(folder) else ""))
            kids = sorted(dir_kids.get(label, ()), key=lambda f: (-dir_counts[f], f))
            for kid in kids[:6]:
                parts.append(f"    {chain(kid)[len(label) + 1:]}/ {dir_counts[kid]}")
            if len(kids) > 6:
                parts.append(f"    +{len(kids) - 6} more folder(s)")
        if len(top_folders) > 20:
            parts.append(f"  +{len(top_folders) - 20} more folder(s)")
        parts.append('Zoom (read tool): mode="survey" with cwd one of '
                     + json.dumps([str(root_p / label) for label in shown_top[:3]]))
    if top_files:
        parts.append("Top-level files: " + ", ".join(top_files))
    if files:
        by_ext: dict[str, int] = {}
        for path in files:
            ext = path.suffix.lower() or "(none)"
            by_ext[ext] = by_ext.get(ext, 0) + 1
        ranked_ext = sorted(by_ext.items(), key=lambda pair: (-pair[1], pair[0]))
        parts.append(("By extension (walked files only): " if truncated_walk else "By extension: ") + ", ".join(f"{ext} {n}" for ext, n in ranked_ext[:10])
                     + (f", +{len(ranked_ext) - 10} more" if len(ranked_ext) > 10 else ""))
    parts.extend(_survey_commands(root_p))
    if changed:
        totals = f" (+{added_total} -{deleted_total} vs HEAD)" if line_counts else ""
        parts.append(f"Changed files: {len(changed)}{totals}")
        for row in changed[:15]:
            counted = line_counts.get(row.split(None, 1)[-1])
            parts.append(f"  {row} {counted}" if counted else f"  {row}")
        if len(changed) > 15:
            parts.append(f"  ... {len(changed) - 15} more")
    if recent:
        parts.append("Recent commits:")
        parts.extend(f"  {row}" for row in recent)
    if hot:
        parts.append("Hot spots (last 200 commits; hub = in a quarter or more of them):")
        parts.extend(f"  {count:3d}x {path}" + (" (hub)" if path in hubs else "") for path, count in hot)
    if groups:
        parts.append("Co-change groups (files usually committed together; hubs left out):")
        for together, members in groups:
            shown = members[:5] + ([f"+{len(members) - 5} more"] if len(members) > 5 else [])
            parts.append(f"  {together} commits together: " + ", ".join(shown))
    if focus:
        changed_paths = {row.split(None, 1)[-1] for row in changed}
        parts.append(f"Focus {focus}: {len(focus_matches)} match(es)")
        for p in focus_matches[:25]:
            rel = relative_display(root_p, p)
            parts.append(f"  {rel} (changed)" if rel in changed_paths else f"  {rel}")
        if len(focus_matches) > 25:
            parts.append(f"  ... {len(focus_matches) - 25} more")
        if focus_matches and log_ran:
            matched = {relative_display(root_p, p) for p in focus_matches}
            parts.extend(_focus_history(matched, commit_log, hubs, [relative_display(root_p, p) for p in files]))

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
    return report


_TEST_FOLDERS = {"test", "tests", "spec", "specs", "__tests__"}


def _test_like(path: str) -> bool:
    *folders, name = path.split("/")
    if any(folder in _TEST_FOLDERS for folder in folders):
        return True
    stem = Path(name).stem
    return name.startswith("test_") or stem.endswith(("_test", ".test", ".spec"))


def _base_stem(path: str) -> str:
    stem = Path(path.rsplit("/", 1)[-1]).stem
    if stem.startswith("test_"):
        stem = stem[len("test_"):]
    for suffix in ("_test", ".test", ".spec"):
        if stem.endswith(suffix):
            stem = stem[:-len(suffix)]
            break
    return stem.lower()


def _focus_history(
    matched: set[str], commit_log: list[tuple[str, list[str]]], hubs: set[str], walked: list[str],
) -> list[str]:
    """Recent commits, co-changed files and related tests for the focus matches, from the survey's
    own newest-200 log (the same window and ranking as ``git:cochange``)."""
    touching = [(head, names) for head, names in commit_log if matched.intersection(names)]
    if not touching:
        return ["Focus history: no commit in the newest 200 touches a match"]
    rows = ["Focus recent commits (newest 5 touching a match):"]
    rows.extend(f"  {head}" for head, _ in touching[:5])
    together: dict[str, int] = {}
    for _, names in touching:
        for name in names:
            if name not in matched:
                together[name] = together.get(name, 0) + 1
    ranked = sorted(together.items(), key=lambda pair: (-pair[1], pair[0]))
    if ranked:
        rows.append("Focus co-change (files committed with a match; newest 200 commits):")
        rows.extend(f"  {count}x {name}" + (" (hub)" if name in hubs else "") for name, count in ranked[:10])
        if len(ranked) > 10:
            rows.append(f"  +{len(ranked) - 10} more")
    stems = {_base_stem(path) for path in matched if not _test_like(path)} - {""}
    tests = {name for name, _ in ranked if _test_like(name)}
    tests.update(path for path in walked if _test_like(path) and _base_stem(path) in stems)
    tests = sorted(tests - matched)
    if tests:
        rows.append("Focus related tests:")
        rows.extend(f"  {path}" for path in tests[:10])
        if len(tests) > 10:
            rows.append(f"  +{len(tests) - 10} more")
    return rows


HUB_SHARE = 0.25  # a file in this share of commits (or more) is a hub, not a co-change signal
GROUP_MIN_TOGETHER = 3
GROUP_MIN_JACCARD = 0.4


def _cochange_groups(
    commits: list[list[str]], counts: dict[str, int], pair_counts: dict[tuple[str, str], int],
) -> tuple[set[str], list[tuple[int, list[str]]]]:
    """Hubs, and groups of files that are mostly committed together.

    A pair joins a group when it was committed together at least GROUP_MIN_TOGETHER times and
    in at least GROUP_MIN_JACCARD of the commits touching either file; hubs (files in
    HUB_SHARE of all commits) pair with everything and are left out.  Groups are ranked by
    their strongest pair, members by how often each changed.
    """
    floor = max(5, int(len(commits) * HUB_SHARE + 0.999))
    hubs = {name for name, count in counts.items() if count >= floor}
    parent: dict[str, str] = {}

    def find(name: str) -> str:
        while parent.setdefault(name, name) != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    edges = [
        (left, right, together) for (left, right), together in pair_counts.items()
        if together >= GROUP_MIN_TOGETHER and left not in hubs and right not in hubs
        and together / (counts[left] + counts[right] - together) >= GROUP_MIN_JACCARD
    ]
    for left, right, _ in edges:
        a, b = find(left), find(right)
        if a != b:
            parent[a] = b
    strongest: dict[str, int] = {}
    for left, _, together in edges:
        root = find(left)
        strongest[root] = max(strongest.get(root, 0), together)
    members: dict[str, list[str]] = {}
    for name in parent:
        members.setdefault(find(name), []).append(name)
    ranked = [
        (strongest.get(root, 0), sorted(names, key=lambda n: (-counts.get(n, 0), n)))
        for root, names in members.items() if len(names) > 1
    ]
    ranked.sort(key=lambda pair: (-pair[0], pair[1][0]))
    return hubs, ranked[:4]


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
        elif result.status == "no_match":
            coverage.no_match += 1
        elif result.status == "deferred":
            coverage.deferred += 1
        else:
            coverage.failed += 1
        coverage.bytes_total += result.bytes_total or 0
        coverage.bytes_shown += result.bytes_shown
    return coverage

"""Transactional multi-file edits.

The editor validates every item before touching disk.  Writes are atomic, the
original bytes and modes are kept in memory for rollback, and an optional verify
command runs after the write.  A failed verify rolls the whole batch back by
default.
"""

from __future__ import annotations

import difflib
import os
import stat
import subprocess
from dataclasses import dataclass, field, replace as _with
from pathlib import Path

from .artifacts import ArtifactStore, since_sha
from .budget import Budget, BudgetTracker, body_budget, water_fill
from .runner import run_commands
from .safety import (
    SafetyError,
    apply_replacement,
    atomic_write_bytes,
    decode_bytes,
    encode_text,
    file_mode,
    find_matches,
    relative_display,
    resolve_path,
    sha256_bytes,
    to_eol,
)
from .workspace import git_root, path_is_within
from .types import (
    EditReport,
    EditRequest,
    EditRequestBundle,
    FileChange,
    NewFileRequest,
    RunResult,
    TextPart,
    VerifyRequest,
)

MAX_DIFF_BYTES = 8 * 1024


@dataclass
class _Snapshot:
    path: Path
    rel: str
    data: bytes | None
    mode: int | None


@dataclass
class _Planned:
    change: FileChange
    path: Path
    action: str
    before: bytes | None = None
    after: bytes | None = None
    mode: int | None = None
    destination: Path | None = None
    full_diff: str = ""


@dataclass
class _Plan:
    items: list[_Planned] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (path, message)
    snapshots: dict[str, _Snapshot] = field(default_factory=dict)
    creates: list[Path] = field(default_factory=list)
    renames: list[tuple[Path, Path]] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    made_dirs: list[Path] = field(default_factory=list)


async def apply_edits(
    bundle: EditRequestBundle,
    *,
    root: str | Path,
    artifacts: ArtifactStore,
    tracker: BudgetTracker | None = None,
    spec_errors: list[str] | None = None,
) -> EditReport:
    root_p = Path(root).resolve()
    report = EditReport(dry_run=bundle.dry_run)
    report.errors.extend(spec_errors or [])

    if bundle.manifest:
        return await _apply_manifest(bundle, root_p, artifacts, tracker, report)

    plan = _plan_edits(bundle, root_p, artifacts)
    report.errors.extend(f"{path}: {message}" for path, message in plan.errors)
    report.changes = [item.change for item in plan.items]
    report.artifacts.extend(plan.artifacts)

    if len(bundle.edits) + len(bundle.new_files) + len(bundle.deletes) + len(bundle.renames) > bundle.max_files:
        report.errors.append(f"too many items: limit is {bundle.max_files}")
    if report.errors:
        report.ok = False
        for item in plan.items:
            if item.change.status == "ok":
                item.change.status = "skipped"
                item.change.message = "not applied because another item failed validation"
        return report

    if bundle.dry_run:
        report.message = "dry run: no files were written"
        return report

    failed, rollback_errors = _apply_plan(plan)
    report.artifacts.extend(rollback_errors)
    if failed:
        report.ok = False
        report.rolled_back = True
        report.rollback_status = "complete" if not rollback_errors else "partial"
        report.message = "write failed; all changes were rolled back"
        return report

    if bundle.verify is not None:
        verify = await _run_verify(bundle.verify, root_p, tracker, artifacts)
        report.verify = verify
        failed_runs = [r for r in verify if r.status != "ok" or r.exit_code not in (0, None)]
        if failed_runs:
            report.ok = False
            report.message = f"verification failed: {failed_runs[0].cmd_display or failed_runs[0].id}"
            if bundle.rollback_on_failure:
                status, errors = _rollback(plan)
                report.rolled_back = True
                report.rollback_status = status
                report.errors.extend(errors)
                for item in plan.items:
                    if item.change.status == "ok":
                        item.change.status = "rolled_back"
                        item.change.message = "rolled back after verification failure"
                report.message = (
                    "verification failed; all changes rolled back"
                    if status == "complete"
                    else f"verification failed; rollback was {status}"
                )
            else:
                report.message = "verification failed; changes kept (rollback_on_failure=false)"
    elif bundle.verify is None:
        report.message = report.message or "changes applied"

    for result in report.verify:
        if result.stdout_artifact:
            report.artifacts.append(result.stdout_artifact)
        if result.stderr_artifact:
            report.artifacts.append(result.stderr_artifact)
    report.ok = report.ok and not report.errors
    return report


# ---------------------------------------------------------------------------
# Text parts
# ---------------------------------------------------------------------------
def _resolve_text_parts(
    bundle: EditRequestBundle, root: Path, artifacts: ArtifactStore, plan: _Plan,
) -> tuple[list[tuple[EditRequest, list[str]]], list[tuple[NewFileRequest, list[str]]]]:
    """Turn every edit's and new file's list of parts into one string, from the files and kept results on disk.

    Each source is read once, before any target is planned, so line numbers name the text as it was read.
    A part that fails adds its own error and drops its edit or new file; the others carry on to be checked.
    """
    sources: dict[str, tuple[str, bytes]] = {}
    shut: set[str] | None = None  # sources this batch creates, deletes or renames

    def key_of(path: Path) -> str:
        return os.path.normcase(str(path))

    def shut_keys() -> set[str]:
        keys: set[str] = set()
        wanted = [new.path for new in bundle.new_files] + list(bundle.deletes)
        wanted += [name for rename in bundle.renames for name in (rename.source, rename.destination)]
        for name in wanted:
            try:
                keys.add(key_of(resolve_path(root, name, allow_outside=bundle.allow_outside)))
            except Exception:
                pass
        return keys

    def file_source(part: TextPart) -> tuple[str, bytes]:
        nonlocal shut
        try:
            path = resolve_path(root, part.path or "", allow_outside=bundle.allow_outside, must_exist=True)
        except FileNotFoundError:
            raise SafetyError(f"source {part.path} not found") from None
        if not path.is_file():
            raise SafetyError(f"source {part.path} is not a regular file")
        rel = relative_display(root, path)
        if shut is None:
            shut = shut_keys()
        if key_of(path) in shut:
            raise SafetyError(f"source {rel} is created, deleted or renamed by this batch")
        if key_of(path) not in sources:
            sources[key_of(path)] = (rel, path.read_bytes())
        rel, data = sources[key_of(path)]
        expected = since_sha(part.since or "")
        if expected is None:
            raise SafetyError("since must be the sha (8+ hex characters) or read handle a read printed")
        sha = sha256_bytes(data)
        if not sha.startswith(expected):
            raise SafetyError(f"file changed since it was read (sha now {sha[:12]}); re-read it")
        return rel, data

    def artifact_source(part: TextPart) -> tuple[str, bytes]:
        name = part.artifact or ""
        target = name
        if artifacts.is_alias(name):
            record = artifacts.resolve(root, name)
            if record is None:
                raise SafetyError(f"no artifact or alias {name} for this cwd")
            target = str(record["target"])
        try:
            return f"artifact:{name}", artifacts.get(target)
        except (OSError, ValueError):
            raise SafetyError("artifact expired or unknown") from None

    def copy_part(part: TextPart) -> tuple[str, str, str | None]:
        display, data = file_source(part) if part.path is not None else artifact_source(part)
        info = decode_bytes(data)
        if info.binary:
            raise SafetyError("binary source; refusing to copy")
        if info.lossy:
            raise SafetyError("source is not valid UTF-8; refusing to copy")
        lines = info.text.splitlines(keepends=True)
        if part.range is None:
            chosen, label = lines, display
        else:
            start, end = part.range
            if start < 1 or end < start or end > len(lines):
                raise SafetyError(f"range {start}-{end} is outside {display} ({len(lines)} lines)")
            chosen, label = lines[start - 1:end], f"{display}:{start}-{end}"
        return "".join(chosen), f"copied {len(chosen)} line(s) from {label}", info.eol

    def resolve_text(value: str | list[TextPart]) -> tuple[str, list[str], str | None, bool]:
        if isinstance(value, str):
            return value, [], None, False
        pieces: list[str] = []
        notes: list[str] = []
        eol: str | None = None
        has_file = False
        for number, part in enumerate(value, start=1):
            if part.text is not None:
                pieces.append(part.text)
                continue
            try:
                text, note, part_eol = copy_part(part)
            except Exception as exc:
                raise SafetyError(f"part {number}: {exc}") from None
            pieces.append(text)
            notes.append(note)
            if part.path is not None and not has_file:
                has_file, eol = True, part_eol
        return "".join(pieces), notes, eol, has_file

    edits: list[tuple[EditRequest, list[str]]] = []
    for edit in bundle.edits:
        try:
            text, notes, _, _ = resolve_text(edit.replace)
        except Exception as exc:
            plan.errors.append((edit.path, str(exc)))
            continue
        edits.append((_with(edit, replace=text) if isinstance(edit.replace, list) else edit, notes))
    new_files: list[tuple[NewFileRequest, list[str]]] = []
    for new in bundle.new_files:
        try:
            text, notes, eol, has_file = resolve_text(new.content)
        except Exception as exc:
            plan.errors.append((new.path, str(exc)))
            continue
        if has_file:  # a new file has no ending of its own, and must not mix endings
            text = to_eol(text, eol)
        new_files.append((_with(new, content=text) if isinstance(new.content, list) else new, notes))
    return edits, new_files


def _with_notes(message: str | None, notes: list[str]) -> str | None:
    return "; ".join(part for part in (message, *notes) if part) or None


def _resolved_text(value: str | list[TextPart]) -> str:
    if isinstance(value, list):
        raise TypeError("text parts reached planning unresolved")
    return value


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------
def _plan_edits(bundle: EditRequestBundle, root: Path, artifacts: ArtifactStore) -> _Plan:
    plan = _Plan()
    claimed: dict[str, str] = {}
    resolved_edits, resolved_new = _resolve_text_parts(bundle, root, artifacts, plan)

    def claim(path: Path, what: str) -> str | None:
        key = os.path.normcase(str(path))
        if key in claimed:
            return f"{relative_display(root, path)} is already used by {claimed[key]}"
        claimed[key] = what
        return None

    grouped: dict[str, list[EditRequest]] = {}
    group_notes: dict[str, list[str]] = {}
    order: list[str] = []
    for edit, edit_notes in resolved_edits:
        try:
            path = resolve_path(root, edit.path, allow_outside=bundle.allow_outside, must_exist=True)
            if not path.is_file():
                raise SafetyError("not a regular file")
            key = str(path)
            if key not in grouped:
                grouped[key] = []
                group_notes[key] = []
                order.append(str(path))
            grouped[key].append(edit)
            group_notes[key].extend(edit_notes)
        except FileNotFoundError:
            plan.errors.append((edit.path, "file not found"))
        except Exception as exc:
            plan.errors.append((edit.path, str(exc)))

    for path_key in order:
        path = Path(path_key)
        rel = relative_display(root, path)
        clash = claim(path, "edits")
        if clash:
            plan.errors.append((rel, clash))
            continue
        try:
            before = path.read_bytes()
            encoding_hint = next((e.encoding for e in grouped[path_key] if e.encoding), None)
            info = decode_bytes(before, encoding_hint)
            if info.binary:
                raise SafetyError("binary file; refusing to edit")
            if info.lossy:
                raise SafetyError("file is not valid UTF-8; pass an explicit encoding or convert it first")
            if info.mixed_eol and not bundle.normalize_eol:
                counts_str = ", ".join(f"{k}:{v}" for k, v in sorted(info.eol_counts.items()) if v > 0)
                raise SafetyError(f"file has mixed line endings ({counts_str}); refuse to edit without normalize_eol=true")
            text = to_eol(info.text, info.eol) if (info.mixed_eol and bundle.normalize_eol) else info.text
            total = 0
            ranged = [e for e in grouped[path_key] if e.range is not None]
            if ranged:  # line numbers name the file as read, so ranges go first
                text = _apply_ranges(text, before, ranged, info.eol)
                total += len(ranged)
            for edit in grouped[path_key]:
                if edit.range is None:
                    text, count = _apply_one(text, edit, info.eol)
                    total += count
            after = encode_text(text, info.encoding)
            original_text = decode_bytes(before, encoding_hint).text
            diff = _unified_diff(original_text, text, rel, "modify")
            full_diff = diff
            diff_ref = None  # fit_diffs cuts the diff to the report budget and keeps the full text
            change = FileChange(
                path=rel, action="modify", replacements=total,
                before_hash=sha256_bytes(before), after_hash=sha256_bytes(after),
                diff=diff, diff_artifact=diff_ref, diff_truncated=diff_ref is not None,
                message=_with_notes(None, group_notes[path_key]),
            )
            plan.items.append(_Planned(
                change=change, path=path, action="modify", before=before, after=after,
                mode=file_mode(path), full_diff=full_diff,
            ))
            _snapshot(plan, path, rel, before, file_mode(path))
        except Exception as exc:
            plan.errors.append((rel, f"{type(exc).__name__}: {exc}"))

    for new, new_notes in resolved_new:
        try:
            path = resolve_path(root, new.path, allow_outside=bundle.allow_outside, must_exist=False)
            rel = relative_display(root, path)
            clash = claim(path, "new_files")
            if clash:
                raise SafetyError(clash)
            if path.exists():
                if path.is_dir():
                    raise SafetyError("path is a directory")
                if not new.overwrite and not bundle.overwrite:
                    raise SafetyError("file exists; pass overwrite=true to replace it")
                existing = path.read_bytes()
                prior: bytes | None = existing
                before_text = decode_bytes(existing).text
                mode = file_mode(path)
                action = "create"
                message = "overwritten (existing file)"
            else:
                prior = None
                before_text = ""
                mode = new.mode
                action = "create"
                message = None
            content = _resolved_text(new.content)
            after = encode_text(content, new.encoding)
            diff = _unified_diff(before_text, content, rel, "create")
            full_diff = diff
            diff_ref = None  # fit_diffs cuts the diff to the report budget and keeps the full text
            change = FileChange(
                path=rel, action=action, status="ok",
                before_hash=sha256_bytes(prior) if prior is not None else None,
                after_hash=sha256_bytes(after), diff=diff, diff_artifact=diff_ref, diff_truncated=diff_ref is not None,
                message=_with_notes(message, new_notes),
            )
            plan.items.append(_Planned(
                change=change, path=path, action="create", before=prior, after=after,
                mode=mode, full_diff=full_diff,
            ))
            if prior is not None:
                _snapshot(plan, path, rel, prior, file_mode(path))
            else:
                plan.creates.append(path)
        except Exception as exc:
            plan.errors.append((new.path, str(exc)))

    for raw in bundle.deletes:
        try:
            if (root / raw).is_symlink():
                raise SafetyError("refusing to delete a symlink")
            path = resolve_path(root, raw, allow_outside=bundle.allow_outside, must_exist=True)
            rel = relative_display(root, path)
            if path.is_dir():
                raise SafetyError("refusing to delete a directory")
            if not path.is_file():
                raise SafetyError("not a regular file")
            clash = claim(path, "deletes")
            if clash:
                raise SafetyError(clash)
            before = path.read_bytes()
            info = decode_bytes(before)
            diff = _unified_diff(info.text if not info.binary else "", "", rel, "delete")
            full_diff = diff
            diff_ref = None  # fit_diffs cuts the diff to the report budget and keeps the full text
            change = FileChange(
                path=rel, action="delete", before_hash=sha256_bytes(before), diff=diff, diff_artifact=diff_ref, diff_truncated=diff_ref is not None,
            )
            plan.items.append(_Planned(
                change=change, path=path, action="delete", before=before, after=None,
                mode=file_mode(path), full_diff=full_diff,
            ))
            _snapshot(plan, path, rel, before, file_mode(path))
        except FileNotFoundError:
            plan.errors.append((raw, "file not found"))
        except Exception as exc:
            plan.errors.append((raw, str(exc)))

    for rename in bundle.renames:
        try:
            if (root / rename.source).is_symlink():
                raise SafetyError("refusing to rename a symlink")
            source = resolve_path(root, rename.source, allow_outside=bundle.allow_outside, must_exist=True)
            destination = resolve_path(root, rename.destination, allow_outside=bundle.allow_outside, must_exist=False)
            rel = relative_display(root, source)
            dest_rel = relative_display(root, destination)
            if source.is_dir():
                raise SafetyError("refusing to rename a directory")
            if not source.is_file():
                raise SafetyError("not a regular file")
            clash = claim(source, "renames")
            if clash:
                raise SafetyError(clash)
            clash = claim(destination, "a rename destination")
            if clash:
                raise SafetyError(clash)
            if destination.exists() and not (rename.overwrite or bundle.overwrite):
                raise SafetyError("destination exists; pass overwrite=true to replace it")
            if destination.exists() and destination.is_dir():
                raise SafetyError("destination is a directory")
            before = source.read_bytes()
            destination_existed = destination.exists()
            destination_before = destination.read_bytes() if destination_existed and destination.is_file() else None
            change = FileChange(
                path=rel, destination=dest_rel, action="rename",
                before_hash=sha256_bytes(before),
                after_hash=sha256_bytes(before), diff="",
            )
            plan.items.append(_Planned(
                change=change, path=source, action="rename", before=before,
                after=before, mode=file_mode(source), destination=destination,
            ))
            _snapshot(plan, source, rel, before, file_mode(source))
            if destination_before is not None:
                _snapshot(plan, destination, dest_rel, destination_before, file_mode(destination))
            plan.renames.append((source, destination))
        except FileNotFoundError:
            plan.errors.append((rename.source, "file not found"))
        except Exception as exc:
            plan.errors.append((rename.source, str(exc)))

    return plan


def _note_new_dirs(plan: _Plan, target: Path) -> None:
    """Record each missing ancestor directory of *target*, so rollback can remove them."""
    directory = target.parent
    while not directory.exists():
        if directory not in plan.made_dirs:
            plan.made_dirs.append(directory)
        if directory.parent == directory:
            break
        directory = directory.parent


def _snapshot(plan: _Plan, path: Path, rel: str, data: bytes | None, mode: int | None) -> None:
    key = os.path.normcase(str(path))
    if key not in plan.snapshots:
        plan.snapshots[key] = _Snapshot(path=path, rel=rel, data=data, mode=mode)


def _ends_in_break(s: str) -> bool:
    """True when *s* ends in any line boundary ``str.splitlines`` splits on."""
    return bool(s) and s.splitlines(keepends=True)[-1] != s.splitlines()[-1]


def _apply_ranges(text: str, before: bytes, edits: list[EditRequest], eol: str | None) -> str:
    """Replace whole lines N-M, only while the file still has the sha its read printed."""
    sha = sha256_bytes(before)
    lines = text.splitlines(keepends=True)
    ordered = sorted(edits, key=lambda e: e.range or (0, 0))
    previous_end = 0
    for edit in ordered:
        expected = since_sha(edit.since or "")
        if expected is None:
            raise SafetyError("since must be the sha (8+ hex characters) or read handle a read printed")
        if not sha.startswith(expected):
            raise SafetyError(f"file changed since it was read (sha now {sha[:12]}); re-read it")
        start, end = edit.range or (0, 0)
        if start < 1 or end < start or end > len(lines):
            raise SafetyError(f"range {start}-{end} is outside the file ({len(lines)} lines)")
        if start <= previous_end:
            raise SafetyError(f"range {start}-{end} overlaps another range edit")
        previous_end = end
    for edit in reversed(ordered):
        start, end = edit.range or (0, 0)
        line_eol = eol or "\n"
        new = to_eol(_resolved_text(edit.replace), line_eol)
        if new and not _ends_in_break(new) and _ends_in_break(lines[end - 1]):
            new += line_eol
        lines[start - 1:end] = [new] if new else []
    return "".join(lines)


def _apply_one(text: str, edit: EditRequest, eol: str | None) -> tuple[str, int]:
    if not edit.search or not edit.search.strip():
        raise SafetyError("search text must not be empty or whitespace-only")
    matches = find_matches(text, edit.search)
    if not matches:
        raise SafetyError(f"search text not found: {edit.search.splitlines()[0][:80]!r}")
    if edit.replace_all:
        selected = matches
    elif edit.occurrence is not None:
        if edit.occurrence > len(matches):
            raise SafetyError(
                f"occurrence {edit.occurrence} requested but only {len(matches)} match(es) found"
            )
        selected = [matches[edit.occurrence - 1]]
    else:
        if len(matches) > 1:
            lines = ", ".join(str(m.line) for m in matches[:10])
            raise SafetyError(
                f"search is ambiguous ({len(matches)} matches at lines {lines}); "
                "add context, set occurrence, or use replace_all"
            )
        selected = matches

    updated = text
    for match in reversed(selected):
        replacement = apply_replacement(updated, match, _resolved_text(edit.replace), eol)
        updated = updated[: match.start] + replacement + updated[match.end:]
    return updated, len(selected)


def _unified_diff(before: str, after: str, rel: str, action: str) -> str:
    if before == after and action != "create":
        return ""
    fromfile = "/dev/null" if action == "create" and not before else f"a/{rel}"
    tofile = "/dev/null" if action == "delete" else f"b/{rel}"
    return "\n".join(
        difflib.unified_diff(
            before.splitlines(), after.splitlines(),
            fromfile=fromfile, tofile=tofile, lineterm="",
        )
    )


def fit_diffs(
    report: EditReport, budget_bytes: int, artifacts: ArtifactStore, *, condense: bool = False
) -> None:
    """Share the report budget across diffs so every file's status line stays visible.

    Small diffs keep everything; larger ones split what is left (max-min fair) and are cut
    on a line boundary, with the full diff kept as an artifact the report names.
    """
    changes = report.changes
    if not changes:
        return
    fulls = [c.diff for c in changes]
    if condense:
        for change in changes:
            if change.diff:
                change.diff = _condense(change.diff)
    sizes = [len(c.diff.encode("utf-8", errors="replace")) for c in changes]
    verify_bytes = sum(r.bytes_shown for r in report.verify)
    total = max(0, body_budget(budget_bytes, len(changes) + len(report.verify)) - verify_bytes)
    if sum(sizes) <= total:
        shares = sizes
    else:
        shares = water_fill(sizes, [0] * len(changes), total, floor=160)
    for change, size, share, full in zip(changes, sizes, shares, fulls):
        share = min(share, MAX_DIFF_BYTES)  # no single diff dominates a report
        if size <= share:
            continue
        if not change.diff_artifact:
            change.diff_artifact = artifacts.put(full, ".edit.diff")
            report.artifacts.append(change.diff_artifact)
        if condense:
            change.diff = _head_paired(change.diff, max(0, share - 64)) + "\n[... changed lines cut to fit the report]"
            change.diff_truncated = True
            continue
        # Spend the share on what changed: drop context lines first, then cut if still too big.
        condensed = _condense(change.diff)
        room = max(0, share - 64)
        if len(condensed.encode("utf-8", errors="replace")) <= room:
            change.diff = condensed + "\n[... context lines dropped to fit the report]"
        else:
            change.diff = _head_paired(condensed, room) + "\n[... context lines dropped to fit the report]"
        change.diff_truncated = True


_DIFF_HEADERS = ("diff --git", "rename ", "new file", "deleted file", "@@", "\\")


def _bsize(line: str) -> int:
    return len(line.encode("utf-8", errors="replace")) + 1


def _clip_at(line: str, limit: int, start: int) -> str:
    """One diff line cut to about *limit* bytes, keeping its sign and the window of its body
    that begins at *start*; cut ends are marked with [...]."""
    if _bsize(line) <= limit:
        return line
    sign, body = line[:1], line[1:]
    width = max(16, limit - 16)
    start = max(0, min(start, len(body) - width))
    piece = body[start:start + width]
    while piece and len(piece.encode("utf-8", errors="replace")) > width:
        piece = piece[:-1]
    head = "[...] " if start > 0 else ""
    tail = " [...]" if start + len(piece) < len(body) else ""
    return sign + head + piece + tail


def _is_changed(line: str) -> bool:
    return line[:1] in ("+", "-")


def _head_paired(condensed: str, cap: int) -> str:
    """Cut a condensed diff to *cap* bytes, keeping removed and added lines in pairs.

    A unified diff lists a run's removed lines before its added lines, so a plain cut from
    the top can show only removals.  Each run keeps its first k removed and first k added
    lines; when not even one pair fits, that pair is shown with each line clipped.  The
    last line counts every changed line left out.
    """
    lines = condensed.splitlines()
    total_changed = sum(1 for line in lines if _is_changed(line))
    room = max(0, cap - 48)  # the closing count line
    out: list[str] = []
    used = shown = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        if not _is_changed(line):
            if used + _bsize(line) > room:
                break
            out.append(line)
            used += _bsize(line)
            i += 1
            continue
        minus: list[str] = []
        plus: list[str] = []
        while i < len(lines) and lines[i][:1] == "-" and _is_changed(lines[i]):
            minus.append(lines[i])
            i += 1
        while i < len(lines) and lines[i][:1] == "+" and _is_changed(lines[i]):
            plus.append(lines[i])
            i += 1
        k = 0
        while k < max(len(minus), len(plus)):
            step = (_bsize(minus[k]) if k < len(minus) else 0) + (_bsize(plus[k]) if k < len(plus) else 0)
            if used + step > room:
                break
            used += step
            k += 1
        if k == 0 and shown == 0:
            pair = minus[:1] + plus[:1]
            each = max(24, (room - used) // len(pair))
            # Cut both lines around where they first differ, from the same start, so the
            # change is visible even when it sits far into a long line.
            focus = len(os.path.commonprefix([minus[0][1:], plus[0][1:]])) if minus and plus else 0
            start = max(0, focus - max(16, each - 16) // 3)
            out.extend(_clip_at(line, each, start) for line in pair)
            shown += len(pair)
            break
        out.extend(minus[:k] + plus[:k])
        shown += min(k, len(minus)) + min(k, len(plus))
        if k < max(len(minus), len(plus)):
            break
    left = total_changed - shown
    if left:
        out.append(f"[... {left} more changed line(s) not shown]")
    return "\n".join(out)


def _condense(diff: str) -> str:
    """A unified diff without its context lines or file header: hunk headers and changed lines."""
    kept: list[str] = []
    in_hunk = False
    for line in diff.splitlines():
        if line.startswith("@@"):
            in_hunk = True
        if in_hunk:
            if line.startswith(("@@", "\\")) or _is_changed(line):
                kept.append(line)
        elif line.startswith(_DIFF_HEADERS):
            kept.append(line)
    return "\n".join(kept)


# ---------------------------------------------------------------------------
# Apply and rollback
# ---------------------------------------------------------------------------
def _apply_plan(plan: _Plan) -> tuple[bool, list[str]]:
    failed = False
    artifacts: list[str] = []
    try:
        for item in plan.items:
            if item.action in ("modify", "create"):
                if item.after is None:
                    raise SafetyError(f"missing content for {item.change.path}")
                if item.action == "create":
                    _note_new_dirs(plan, item.path)
                atomic_write_bytes(item.path, item.after, mode=item.mode)
            elif item.action == "delete":
                item.path.unlink()
            elif item.action == "rename":
                if item.destination is None:
                    raise SafetyError(f"missing destination for {item.change.path}")
                _note_new_dirs(plan, item.destination)
                item.destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(item.path, item.destination)
            item.change.status = "ok"
    except Exception as exc:
        failed = True
        status, errors = _rollback(plan)
        for item in plan.items:
            if item.change.status == "ok":
                item.change.status = "rolled_back" if status in ("complete", "partial") else "error"
                item.change.message = "rolled back after a write failure"
            elif item.change.status != "error":
                item.change.status = "error"
                item.change.message = f"{type(exc).__name__}: {exc}"
        artifacts.extend(errors)
    return failed, artifacts


def _rollback(plan: _Plan) -> tuple[str, list[str]]:
    errors: list[str] = []
    for path in plan.creates:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            errors.append(f"rollback could not remove {path}: {exc}")
    for source, destination in plan.renames:
        try:
            if destination.exists():
                destination.unlink()
        except OSError as exc:
            errors.append(f"rollback could not remove {destination}: {exc}")
    for snapshot in plan.snapshots.values():
        try:
            if snapshot.data is None:
                snapshot.path.unlink(missing_ok=True)
            else:
                snapshot.path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_bytes(snapshot.path, snapshot.data, mode=snapshot.mode)
        except Exception as exc:
            errors.append(f"rollback could not restore {snapshot.rel}: {exc}")
    for directory in sorted(plan.made_dirs, key=lambda d: len(d.parts), reverse=True):
        if not directory.exists():
            continue
        try:
            directory.rmdir()
        except OSError as exc:
            errors.append(f"rollback could not remove directory {directory}: {exc}")
    if errors:
        return "partial", errors
    return "complete", errors


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
async def _run_verify(
    verify: VerifyRequest,
    root: Path,
    tracker: BudgetTracker | None,
    artifacts: ArtifactStore,
) -> list[RunResult]:
    from .runner import make_verify_run

    req = make_verify_run(verify, 0)
    verify_tracker = tracker or BudgetTracker(Budget(tokens=4000, item_tokens=4000, time_s=max(30.0, verify.timeout + 5)))
    return await run_commands(
        [req], root=root, tracker=verify_tracker, artifacts=artifacts,
        parallel=1, max_output=32 * 1024,
    )


# ---------------------------------------------------------------------------
# Git-apply manifests
# ---------------------------------------------------------------------------
async def _apply_manifest(
    bundle: EditRequestBundle,
    root: Path,
    artifacts: ArtifactStore,
    tracker: BudgetTracker | None,
    report: EditReport,
) -> EditReport:
    patch = bundle.manifest or ""
    if patch.strip() == "":
        report.ok = False
        report.errors.append("manifest is empty")
        return report
    if report.errors:
        report.ok = False
        return report

    top = git_root(root) or root
    listing = _git_apply(top, patch, "--numstat", "-z")
    if listing.returncode != 0:
        report.ok = False
        report.errors.append(
            f"git apply could not read the diff: {listing.stderr.strip() or listing.stdout.strip()}"
        )
        return report
    paths: list[str] = []
    for record in listing.stdout.split("\0"):
        parts = record.split("\t", 2)
        if len(parts) == 3 and parts[2] not in paths:
            paths.append(parts[2])
    for value in _patch_sources(patch):
        if value.startswith('"'):
            report.ok = False
            report.errors.append(f"{value}: quoted rename or copy paths are not supported")
            return report
        if value not in paths:
            paths.append(value)
    if not paths:
        report.ok = False
        report.errors.append("diff does not mention any files")
        return report
    # Diff paths are relative to the repository root, as git reads them, so a `git diff`
    # pasted from any subfolder applies. Paths that land outside cwd are refused.
    try:
        resolved = []
        for p in paths:
            target = resolve_path(top, p, allow_outside=True, must_exist=False)
            if not bundle.allow_outside and not path_is_within(root, target):
                raise SafetyError(
                    f"{p}: outside cwd (diff paths are relative to the repository root {top.as_posix()})"
                )
            resolved.append(target)
    except Exception as exc:
        report.ok = False
        report.errors.append(str(exc))
        return report

    plan = _Plan()
    actions = _patch_actions(patch)
    expect_change: list[tuple[_Planned, str]] = []  # (item, action) git apply must visibly carry out
    for original, path in zip(paths, resolved):
        if actions.get(original) == "copy-source":
            continue  # git reads a copy source without writing it
        rel = relative_display(root, path)
        existed = path.exists()
        before = path.read_bytes() if existed and path.is_file() else None
        if existed and path.is_dir():
            report.ok = False
            report.errors.append(f"{rel}: is a directory")
            return report
        action = actions.get(original, "modify" if before is not None else "create")
        diff = _patch_section(patch, original)
        full_diff = diff
        diff_ref = None  # fit_diffs cuts the diff to the report budget and keeps the full text
        change = FileChange(
            path=rel, action=action,
            before_hash=sha256_bytes(before) if before is not None else None,
            diff=diff, diff_artifact=diff_ref, diff_truncated=diff_ref is not None,
        )
        planned = _Planned(change=change, path=path, action=action, before=before, mode=file_mode(path))
        plan.items.append(planned)
        if action in ("create", "delete") or "\n@@" in f"\n{diff}":
            expect_change.append((planned, action))  # mode-only sections change no bytes
        if before is not None:
            _snapshot(plan, path, rel, before, file_mode(path))
        else:
            plan.creates.append(path)

    check = _git_apply(top, patch, "--check")
    if check.returncode != 0:
        report.ok = False
        report.errors.append(f"git apply --check failed: {check.stderr.strip() or check.stdout.strip()}")
        report.changes = [item.change for item in plan.items]
        for change in report.changes:
            change.status = "error"
        return report

    report.changes = [item.change for item in plan.items]
    if bundle.dry_run:
        report.message = "dry run: git apply --check passed; no files were written"
        return report

    for created in plan.creates:
        _note_new_dirs(plan, created)
    result = _git_apply(top, patch)
    if result.returncode != 0:
        status, rollback_errors = _rollback(plan)
        report.ok = False
        report.rolled_back = True
        report.rollback_status = status
        report.errors.append(f"git apply failed: {result.stderr.strip() or result.stdout.strip()}")
        report.errors.extend(rollback_errors)
        for change in report.changes:
            change.status = "rolled_back" if status != "failed" else "error"
        return report

    # git apply exits 0 even when it skips a path (for example one outside the directory it
    # runs in); check that every file it was asked to change really changed.
    untouched: list[str] = []
    for item, action in expect_change:
        exists = item.path.exists()
        if action == "delete":
            done = not exists
        elif action == "create":
            done = exists
        else:
            done = exists and item.before is not None and item.path.read_bytes() != item.before
        if not done:
            untouched.append(item.change.path)
    if untouched:
        status, rollback_errors = _rollback(plan)
        report.ok = False
        report.rolled_back = True
        report.rollback_status = status
        report.errors.append("git apply reported success but did not change: " + ", ".join(untouched))
        report.errors.extend(rollback_errors)
        for change in report.changes:
            change.status = "rolled_back"
        report.message = "patch not applied; all changes were rolled back"
        return report

    for item in plan.items:
        try:
            if item.path.exists():
                item.change.after_hash = sha256_bytes(item.path.read_bytes())
                item.change.status = "ok"
            else:
                item.change.status = "ok"
        except OSError as exc:
            item.change.status = "error"
            item.change.message = str(exc)
    report.message = "patch applied with git apply"

    if bundle.verify is not None:
        verify = await _run_verify(bundle.verify, root, tracker, artifacts)
        report.verify = verify
        for run_result in verify:
            if run_result.stdout_artifact:
                report.artifacts.append(run_result.stdout_artifact)
            if run_result.stderr_artifact:
                report.artifacts.append(run_result.stderr_artifact)
        failed = [r for r in verify if r.status != "ok" or r.exit_code not in (0, None)]
        if failed:
            report.ok = False
            if bundle.rollback_on_failure:
                status, errors = _rollback(plan)
                report.rolled_back = True
                report.rollback_status = status
                report.errors.extend(errors)
                for change in report.changes:
                    change.status = "rolled_back"
                report.message = f"verification failed; rollback {status}"
            else:
                report.message = "verification failed; changes kept"
    return report


def _git_apply(root: Path, patch: str, *options: str) -> subprocess.CompletedProcess[str]:
    argv = ["git", "apply", "--whitespace=nowarn", *options]
    # The patch goes in as bytes: text-mode stdin would turn its LF into CRLF on Windows.
    proc = subprocess.run(
        argv, cwd=str(root), input=patch.encode("utf-8", errors="replace"),
        capture_output=True, timeout=60, check=False,
    )
    return subprocess.CompletedProcess(
        argv, proc.returncode,
        proc.stdout.decode("utf-8", errors="replace"), proc.stderr.decode("utf-8", errors="replace"),
    )


def _patch_sources(patch: str) -> list[str]:
    sources: list[str] = []
    for line in patch.splitlines():
        for prefix in ("rename from ", "copy from "):
            if line.startswith(prefix):
                value = line[len(prefix):].strip()
                if value not in sources:
                    sources.append(value)
    return sources


def _patch_section(patch: str, path: str) -> str:
    sections = patch.split("diff --git ")
    for section in sections[1:]:
        header = section.splitlines()[0] if section.splitlines() else ""
        padded = f" {header} "
        if f" a/{path} " in padded or f" b/{path} " in padded:
            return "diff --git " + section.strip()
    return patch.strip() if patch.strip().startswith("--- ") else ""


def _patch_actions(patch: str) -> dict[str, str]:
    actions: dict[str, str] = {}
    current_path: str | None = None
    pending_new = False
    for line in patch.splitlines():
        if line.startswith("--- /dev/null"):
            current_path = None
            pending_new = True
        elif line.startswith("--- a/"):
            current_path = line[6:].strip()
            actions.setdefault(current_path, "modify")
            pending_new = False
        elif line.startswith("+++ b/"):
            path = line[6:].strip()
            if actions.get(path) != "create":  # a rename target stays a create
                actions[path] = "create" if pending_new else "modify"
            current_path = path
            pending_new = False
        elif line.startswith("+++ /dev/null"):
            if current_path:
                actions[current_path] = "delete"
        elif line.startswith("rename from "):
            actions[line[len("rename from "):].strip()] = "delete"
        elif line.startswith("rename to "):
            actions[line[len("rename to "):].strip()] = "create"
        elif line.startswith("copy from "):
            actions.setdefault(line[len("copy from "):].strip(), "copy-source")
        elif line.startswith("copy to "):
            actions[line[len("copy to "):].strip()] = "create"
    return actions

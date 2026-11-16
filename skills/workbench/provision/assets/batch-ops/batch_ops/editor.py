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
from dataclasses import dataclass, field
from pathlib import Path

from .artifacts import ArtifactStore
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
# Planning
# ---------------------------------------------------------------------------
def _plan_edits(bundle: EditRequestBundle, root: Path, artifacts: ArtifactStore) -> _Plan:
    plan = _Plan()
    claimed: dict[str, str] = {}

    def claim(path: Path, what: str) -> str | None:
        key = os.path.normcase(str(path))
        if key in claimed:
            return f"{relative_display(root, path)} is already used by {claimed[key]}"
        claimed[key] = what
        return None

    grouped: dict[str, list[EditRequest]] = {}
    order: list[str] = []
    for edit in bundle.edits:
        try:
            path = resolve_path(root, edit.path, allow_outside=bundle.allow_outside, must_exist=True)
            if not path.is_file():
                raise SafetyError("not a regular file")
            key = str(path)
            if key not in grouped:
                grouped[key] = []
                order.append(str(path))
            grouped[key].append(edit)
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
            for edit in grouped[path_key]:
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
            )
            plan.items.append(_Planned(
                change=change, path=path, action="modify", before=before, after=after,
                mode=file_mode(path), full_diff=full_diff,
            ))
            _snapshot(plan, path, rel, before, file_mode(path))
        except Exception as exc:
            plan.errors.append((rel, f"{type(exc).__name__}: {exc}"))

    for new in bundle.new_files:
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
            after = encode_text(new.content, new.encoding)
            diff = _unified_diff(before_text, new.content, rel, "create")
            full_diff = diff
            diff_ref = None  # fit_diffs cuts the diff to the report budget and keeps the full text
            change = FileChange(
                path=rel, action=action, status="ok",
                before_hash=sha256_bytes(prior) if prior is not None else None,
                after_hash=sha256_bytes(after), diff=diff, diff_artifact=diff_ref, diff_truncated=diff_ref is not None, message=message,
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
        except Exception as exc:
            plan.errors.append((rename.source, str(exc)))

    return plan


def _snapshot(plan: _Plan, path: Path, rel: str, data: bytes | None, mode: int | None) -> None:
    key = os.path.normcase(str(path))
    if key not in plan.snapshots:
        plan.snapshots[key] = _Snapshot(path=path, rel=rel, data=data, mode=mode)


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
        replacement = apply_replacement(updated, match, edit.replace, eol)
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


def fit_diffs(report: EditReport, budget_bytes: int, artifacts: ArtifactStore) -> None:
    """Share the report budget across diffs so every file's status line stays visible.

    Small diffs keep everything; larger ones split what is left (max-min fair) and are cut
    on a line boundary, with the full diff kept as an artifact the report names.
    """
    changes = report.changes
    if not changes:
        return
    sizes = [len(c.diff.encode("utf-8", errors="replace")) for c in changes]
    verify_bytes = sum(r.bytes_shown for r in report.verify)
    total = max(0, body_budget(budget_bytes, len(changes) + len(report.verify)) - verify_bytes)
    if sum(sizes) <= total:
        shares = sizes
    else:
        shares = water_fill(sizes, [0] * len(changes), total, floor=160)
    for change, size, share in zip(changes, sizes, shares):
        share = min(share, MAX_DIFF_BYTES)  # no single diff dominates a report
        if size <= share:
            continue
        if not change.diff_artifact:
            change.diff_artifact = artifacts.put(change.diff, ".edit.diff")
            report.artifacts.append(change.diff_artifact)
        # Spend the share on what changed: drop context lines first, then cut if still too big.
        condensed = _condense(change.diff)
        room = max(0, share - 64)
        if len(condensed.encode("utf-8", errors="replace")) <= room:
            change.diff = condensed + "\n[... context lines dropped to fit the report]"
        else:
            change.diff = _head_paired(condensed, room) + "\n[... context lines dropped to fit the report]"
        change.diff_truncated = True


_FILE_HEADERS = ("--- ", "+++ ")  # the path is already in the report's item header
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
    return line[:1] in ("+", "-") and not line.startswith(_FILE_HEADERS)


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
    return "\n".join(
        line for line in diff.splitlines()
        if line.startswith(_DIFF_HEADERS) or _is_changed(line)
    )


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
                atomic_write_bytes(item.path, item.after, mode=item.mode)
            elif item.action == "delete":
                item.path.unlink()
            elif item.action == "rename":
                if item.destination is None:
                    raise SafetyError(f"missing destination for {item.change.path}")
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

    paths = _patch_paths(patch)
    if not paths:
        report.ok = False
        report.errors.append("diff does not mention any files")
        return report
    # Diff paths are relative to the repository root, as git reads them, so a `git diff`
    # pasted from any subfolder applies. Paths that land outside cwd are refused.
    top = git_root(root) or root
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

    check = _git_apply(top, patch, check=True, dry_run=False)
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

    result = _git_apply(top, patch, check=False, dry_run=False)
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


def _git_apply(root: Path, patch: str, *, check: bool, dry_run: bool) -> subprocess.CompletedProcess[str]:
    args = ["git", "apply", "--whitespace=nowarn"]
    if check:
        args.append("--check")
    return subprocess.run(
        args, cwd=str(root), input=patch, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60, check=False,
    )


def _patch_paths(patch: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for line in patch.splitlines():
        value = None
        if line.startswith("+++ b/"):
            value = line[6:]
        elif line.startswith("--- a/"):
            value = line[6:]
        elif line.startswith("+++ ") and line[4:] not in ("/dev/null",):
            value = line[4:]
        elif line.startswith("--- ") and line[4:] not in ("/dev/null",):
            value = line[4:]
        elif line.startswith("rename to "):
            value = line[len("rename to "):]
        elif line.startswith("rename from "):
            value = line[len("rename from "):]
        if not value:
            continue
        value = value.strip()
        if value.startswith(("a/", "b/")):
            value = value[2:]
        if value in seen or value.startswith("/dev/null"):
            continue
        if value.startswith("/") or ".." in Path(value).parts:
            continue
        seen.add(value)
        paths.append(value)
    return paths


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
    return actions

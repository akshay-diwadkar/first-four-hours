#!/usr/bin/env python3
"""Install or remove Atlas project-folder guidance."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from _diagnostic_contract import normalize_diagnostic
from structure_state import Page, analyze

MANAGED_BEGIN = b"<!-- ATLAS"
MANAGED_END = b"<!-- /ATLAS -->"
LEGACY_BEGIN = b"<!-- BEGIN ATLAS"
LEGACY_END = b"<!-- END ATLAS -->"
RETIRED_MANAGED_BEGIN = b"<!-- BEGIN MAP-CODEBASE"
RETIRED_MANAGED_END = b"<!-- END MAP-CODEBASE"
RETIRED_OPT_OUT = b"<!-- OPT-OUT MAP-CODEBASE -->"
OBSOLETE_BEGIN = b"<!-- BEGIN BUILD-CODEBASE-KNOWLEDGE -->"
OBSOLETE_END = b"<!-- END BUILD-CODEBASE-KNOWLEDGE -->"
OPT_OUT = b"<!-- OPT-OUT ATLAS -->"
TARGETS = ("AGENTS.md", "CLAUDE.md")
# The stamp `<!-- ATLAS [prefix [suffix]] -->` records how many line breaks the block owns
# before and after it; the bytes follow the block's actual line endings, so Git line-ending
# normalization never breaks ownership.
BEGIN_RE = re.compile(rb"<!-- ATLAS(?: ([0-2])(?: ([01]))?)? -->")
# Anything shaped like a stamp counts toward duplicate/malformed detection; other comments
# that merely start with `<!-- ATLAS`, such as `<!-- ATLASSIAN -->` or
# `<!-- ATLAS 2026 roadmap -->`, belong to the user.
BEGIN_TOKEN_RE = re.compile(rb"<!-- ATLAS(?: \d+)* -->")
# Earlier verbose stamps stay recognized so setup upgrades them and remove restores bytes.
LEGACY_BREAKS = {b"none": 0, b"lf": 1, b"crlf": 1, b"lf2": 2, b"crlf2": 2}
LEGACY_BEGIN_RE = re.compile(rb"<!-- BEGIN ATLAS(?: prefix=(none|lf|crlf|lf2|crlf2))?(?: suffix=(none|lf|crlf))? -->")
MARKERLESS_LEGACY_HEADING = b"## Repository Knowledge"

MAP_LEAD = (
    "Atlas `setup-guidance` writes this section from each top-level Landmark's title and opening "
    "paragraph; never edit it by hand, and rerun `setup-guidance` after changing them. Follow only "
    "links whose cue fits the task, and search project files directly when none fits. Update "
    "affected `.map/` pointers when files move or change meaning; run Atlas `check`/`baseline` only "
    "for drift audits."
)
MAP_AUTHORITY = (
    "Project files are authoritative. This map offers selective orientation, not exhaustive "
    "coverage; inspect current sources before deciding or changing anything."
)


class GuidanceError(ValueError):
    """A supported instruction file cannot be changed safely."""


class GuidanceTransactionError(OSError):
    """A publication failed after writes began."""

    def __init__(self, message: str, rollback_failures: list[str]) -> None:
        super().__init__(message)
        self.rollback_failures = rollback_failures


@dataclass(frozen=True)
class OwnedBlock:
    start: int
    end: int
    prefix_breaks: int
    suffix_breaks: int
    newline: bytes
    body_start: int
    body_end: int


@dataclass(frozen=True)
class PlannedWrite:
    path: Path
    original: bytes | None
    desired: bytes | None
    action: str
    mode: int | None


def map_lines(pages: Mapping[PurePosixPath, Page]) -> tuple[str, ...]:
    """Derive the Map block's lines from the top-level Landmarks of a diagnostic-free wiki."""
    entries: list[str] = []
    for path, page in sorted(pages.items()):
        if page.role != "landmark" or page.parent is not None:
            continue
        if page.map_entry is None:
            raise ValueError(f"top-level Landmark has no Map entry: {path.as_posix()}")
        title, cue = page.map_entry
        entries.append(f"- [{title}]({path.as_posix()}): {cue}")
    return ("## Atlas", "", MAP_LEAD, "", MAP_AUTHORITY, "", *entries)


def managed_block(
    newline: bytes,
    prefix_breaks: int,
    suffix_breaks: int,
    lines: tuple[str, ...],
) -> bytes:
    if prefix_breaks not in (0, 1, 2) or suffix_breaks not in (0, 1):
        raise ValueError(f"unsupported managed spacing: {prefix_breaks} {suffix_breaks}")
    body = newline.join(line.encode("utf-8") for line in lines)
    counts = (prefix_breaks, suffix_breaks) if suffix_breaks else (prefix_breaks,) if prefix_breaks else ()
    begin = b" ".join((MANAGED_BEGIN, *(str(count).encode("ascii") for count in counts), b"-->"))
    return newline.join((begin, body, MANAGED_END, b"")) + newline * suffix_breaks


def _spacing(before: bytes, after: bytes) -> tuple[int, int]:
    if not before or before.endswith((b"\n\n", b"\r\n\r\n", b"\r")):
        prefix_breaks = 0
    elif before.endswith(b"\n"):
        prefix_breaks = 1
    else:
        prefix_breaks = 2
    suffix_breaks = 1 if after and not after.startswith((b"\n", b"\r")) else 0
    return prefix_breaks, suffix_breaks


def _positions(payload: bytes, marker: bytes) -> list[int]:
    result: list[int] = []
    start = 0
    while (position := payload.find(marker, start)) >= 0:
        result.append(position)
        start = position + len(marker)
    return result


def _owned_block(payload: bytes, filename: str) -> OwnedBlock | None:
    begin_tokens = [match.start() for match in BEGIN_TOKEN_RE.finditer(payload)]
    begin_tokens += _positions(payload, LEGACY_BEGIN)
    current = list(BEGIN_RE.finditer(payload))
    legacy = list(LEGACY_BEGIN_RE.finditer(payload))
    ends = _positions(payload, MANAGED_END) + _positions(payload, LEGACY_END)
    if not begin_tokens and not ends:
        return None
    if len(begin_tokens) != 1 or len(current) + len(legacy) != 1 or len(ends) != 1:
        raise GuidanceError(f"malformed or duplicate ATLAS block in {filename}")
    if current:
        match, end_marker = current[0], MANAGED_END
        prefix_breaks, suffix_breaks = int(match.group(1) or b"0"), int(match.group(2) or b"0")
    else:
        match, end_marker = legacy[0], LEGACY_END
        prefix_breaks = LEGACY_BREAKS[match.group(1) or b"none"]
        suffix_breaks = LEGACY_BREAKS[match.group(2) or b"none"]
    marker_start = match.start()
    marker_end = ends[0] + len(end_marker)
    if marker_start >= ends[0] or not payload.startswith(end_marker, ends[0]):
        raise GuidanceError(f"malformed ATLAS block in {filename}")
    newline = b"\r\n" if b"\r\n" in payload[marker_start:marker_end] else b"\n"
    prefix = newline * prefix_breaks
    start = marker_start - len(prefix)
    if start < 0 or payload[start:marker_start] != prefix:
        raise GuidanceError(f"ATLAS prefix ownership does not match in {filename}")
    end = marker_end
    if payload[end : end + len(newline)] == newline:
        end += len(newline)
    suffix = newline * suffix_breaks
    if suffix and payload[end : end + len(suffix)] == suffix:
        end += len(suffix)
    return OwnedBlock(start, end, prefix_breaks, suffix_breaks, newline, match.end(), ends[0])


def _newline(payload: bytes) -> bytes:
    return b"\r\n" if b"\r\n" in payload else b"\n"


def _created_heading(filename: str, newline: bytes) -> bytes:
    return f"# {filename}".encode("utf-8") + newline * 2


def _without_block(payload: bytes, located: OwnedBlock) -> bytes:
    prefix = payload[: located.start]
    suffix = payload[located.end :]
    if (
        located.prefix_breaks
        and suffix
        and not prefix.endswith((b"\n", b"\r"))
        and not suffix.startswith((b"\n", b"\r"))
    ):
        return prefix + located.newline + suffix
    return prefix + suffix


def _reject_markerless_legacy(payload: bytes, filename: str) -> None:
    if MARKERLESS_LEGACY_HEADING in payload:
        raise GuidanceError(
            f"noncanonical Repository Knowledge section requires manual review in {filename}"
        )


def _reject_retired_managed_block(payload: bytes, filename: str) -> None:
    if RETIRED_MANAGED_BEGIN in payload or RETIRED_MANAGED_END in payload:
        raise GuidanceError(
            f"retired MAP-CODEBASE guidance block requires manual review in {filename}"
        )


def _reject_retired_opt_out(payload: bytes, filename: str) -> None:
    if RETIRED_OPT_OUT in payload:
        raise GuidanceError(
            f"retired MAP-CODEBASE opt-out marker requires manual review in {filename}"
        )


def _reject_obsolete_markers(payload: bytes, filename: str) -> None:
    if OBSOLETE_BEGIN in payload or OBSOLETE_END in payload:
        raise GuidanceError(
            f"obsolete BUILD-CODEBASE-KNOWLEDGE block requires manual review in {filename}"
        )


def _read_target(path: Path) -> tuple[bytes | None, int | None]:
    if path.is_symlink():
        raise GuidanceError(f"instruction path is a symbolic link: {path.name}")
    if not path.exists():
        return None, None
    if not path.is_file():
        raise GuidanceError(f"instruction path is not a regular file: {path.name}")
    payload = path.read_bytes()
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GuidanceError(f"instruction file is not UTF-8: {path.name}") from exc
    return payload, stat.S_IMODE(path.stat().st_mode)


def _inspect(payload: bytes, filename: str) -> tuple[OwnedBlock | None, bool]:
    _reject_obsolete_markers(payload, filename)
    _reject_markerless_legacy(payload, filename)
    _reject_retired_managed_block(payload, filename)
    _reject_retired_opt_out(payload, filename)
    located = _owned_block(payload, filename)
    opt_outs = _positions(payload, OPT_OUT)
    if len(opt_outs) > 1:
        raise GuidanceError(f"duplicate ATLAS opt-out markers in {filename}")
    if (
        opt_outs
        and located is not None
        and located.start <= opt_outs[0] < located.end
    ):
        raise GuidanceError(f"ATLAS opt-out marker is inside the managed block in {filename}")
    return located, bool(opt_outs)


def _plan_setup(path: Path, lines: tuple[str, ...]) -> PlannedWrite:
    payload, mode = _read_target(path)
    if payload is None:
        return PlannedWrite(
            path, None, _created_heading(path.name, b"\n") + managed_block(b"\n", 0, 0, lines), "created", None
        )

    located, opted_out = _inspect(payload, path.name)
    if opted_out:
        desired = (
            _without_block(payload, located)
            if located is not None
            else payload
        )
        action = "opted_out_removed" if desired != payload else "opted_out"
        return PlannedWrite(path, payload, desired, action, mode)

    newline = _newline(payload)
    before = payload[: located.start] if located is not None else payload
    after = payload[located.end :] if located is not None else b""
    prefix_breaks, suffix_breaks = _spacing(before, after)
    desired = (
        before
        + newline * prefix_breaks
        + managed_block(newline, prefix_breaks, suffix_breaks, lines)
        + after
    )
    action = "unchanged" if desired == payload else "updated"
    return PlannedWrite(path, payload, desired, action, mode)


def map_diagnostics(root: Path, pages: Mapping[PurePosixPath, Page]) -> list[dict[str, Any]]:
    """Validate each root file's managed block as the Map derived from the top-level Landmarks."""
    lines = ["", *map_lines(pages)]
    diagnostics: list[dict[str, Any]] = []
    for name in TARGETS:
        try:
            payload, _mode = _read_target(root / name)
            if payload is None:
                diagnostics.append(_map_missing(name, "does not exist"))
                continue
            located, opted_out = _inspect(payload, name)
            if opted_out:
                continue
            if located is None:
                diagnostics.append(_map_missing(name, "has no Atlas Map block"))
                continue
            body = payload[located.body_start : located.body_end].decode("utf-8")
        except (GuidanceError, OSError) as exc:
            diagnostics.append(
                _diagnostic(
                    "map.map_unreadable",
                    f"The Atlas Map block in {name} cannot be read: {exc}",
                    name,
                    "Report this diagnostic without editing the named instruction file; the user repairs the "
                    "reported marker, encoding, or path before `setup-guidance` and `run` are rerun.",
                    phase="run",
                )
            )
            continue
        # Only the lines between the markers count: spacing around the block and newline style never do.
        if body.splitlines() != lines:
            diagnostics.append(
                _diagnostic(
                    "map.map_stale",
                    f"The Atlas Map block in {name} differs from what setup-guidance writes from the top-level Landmarks.",
                    name,
                    "Rerun Atlas `setup-guidance` to rewrite the block from the Landmarks; never hand-edit the block.",
                    phase="run",
                )
            )
    return diagnostics


def _map_missing(name: str, reason: str) -> dict[str, Any]:
    return _diagnostic(
        "map.map_missing",
        f"{name} {reason}, so agents reading it never see the Atlas Map.",
        name,
        "Run Atlas `setup-guidance` to write the Map block, unless the user removed or declined root guidance; "
        "then report this diagnostic and ask the user to add `<!-- OPT-OUT ATLAS -->` to that file, which only "
        "the user adds.",
        phase="run",
    )


def _plan_remove(path: Path) -> PlannedWrite:
    payload, mode = _read_target(path)
    if payload is None:
        return PlannedWrite(path, None, None, "absent", None)
    _reject_obsolete_markers(payload, path.name)
    _reject_markerless_legacy(payload, path.name)
    _reject_retired_managed_block(payload, path.name)
    _reject_retired_opt_out(payload, path.name)
    located = _owned_block(payload, path.name)
    if located is None:
        return PlannedWrite(
            path,
            payload,
            payload,
            "unchanged",
            mode,
        )
    remaining = _without_block(payload, located)
    if remaining in (_created_heading(path.name, b"\n"), _created_heading(path.name, b"\r\n")):
        return PlannedWrite(path, payload, None, "deleted", mode)
    return PlannedWrite(path, payload, remaining, "removed", mode)


def _write_temporary(path: Path, payload: bytes, mode: int | None, label: str) -> Path:
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.atlas-{label}-",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        if temporary.read_bytes() != payload:
            raise OSError(f"temporary bytes did not verify for {path.name}")
        return temporary
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _stage(plan: Iterable[PlannedWrite]) -> dict[Path, Path]:
    staged: dict[Path, Path] = {}
    try:
        for item in plan:
            if item.desired is None or item.desired == item.original:
                continue
            staged[item.path] = _write_temporary(
                item.path,
                item.desired,
                item.mode,
                "stage",
            )
        return staged
    except Exception:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
        raise


def _snapshot_matches(item: PlannedWrite) -> bool:
    if item.path.is_symlink():
        return False
    if item.original is None:
        return not item.path.exists()
    if not item.path.is_file():
        return False
    try:
        return (
            item.path.read_bytes() == item.original
            and stat.S_IMODE(item.path.stat().st_mode) == item.mode
        )
    except OSError:
        return False


def _restore(plan: Iterable[PlannedWrite]) -> list[str]:
    failures: list[str] = []
    for item in plan:
        try:
            if item.original is None:
                item.path.unlink(missing_ok=True)
                continue
            temporary = _write_temporary(
                item.path,
                item.original,
                item.mode,
                "rollback",
            )
            try:
                os.replace(temporary, item.path)
            finally:
                temporary.unlink(missing_ok=True)
        except OSError as exc:
            failures.append(f"{item.path.name}: {exc}")
    return failures


def _apply(plan: list[PlannedWrite]) -> None:
    staged = _stage(plan)
    try:
        stale = [item.path.name for item in plan if not _snapshot_matches(item)]
        if stale:
            raise GuidanceError(
                "instruction files changed after preflight: " + ", ".join(stale)
            )
    except Exception:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
        raise
    touched: list[PlannedWrite] = []
    try:
        for item in plan:
            if item.desired == item.original:
                continue
            touched.append(item)
            if item.desired is None:
                item.path.unlink(missing_ok=True)
            else:
                temporary = staged[item.path]
                os.replace(temporary, item.path)
                staged.pop(item.path)
            actual = item.path.read_bytes() if item.path.exists() else None
            if actual != item.desired:
                raise OSError(f"published bytes did not verify for {item.path.name}")
    except Exception as exc:
        rollback_failures = _restore(touched)
        if rollback_failures:
            message = (
                f"repository guidance transaction failed and rollback is incomplete: {exc}; "
                f"rollback failures: {', '.join(rollback_failures)}"
            )
        else:
            message = (
                "repository guidance transaction failed and prior contents were restored: "
                f"{exc}"
            )
        raise GuidanceTransactionError(message, rollback_failures) from exc
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def _diagnostic(
    code: str,
    message: str,
    path: str,
    repair: str,
    *,
    phase: str = "setup-guidance",
) -> dict[str, Any]:
    return normalize_diagnostic(
        {
            "code": code,
            "message": message,
            "required_action": repair,
            "valid_repairs": [repair],
            "supporting_evidence": [message],
        },
        skill="atlas",
        phase=phase,
        artifact="repository instructions",
        path=path,
    )


def apply_guidance(root: Path, operation: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = root.resolve()
    if operation == "setup":
        try:
            _report, pages, topology_diagnostics = analyze(root)
        except (OSError, UnicodeError) as exc:
            filename = getattr(exc, "filename", None)
            path = Path(filename).name if filename else ".map"
            message = (
                "Repository guidance requires a readable UTF-8 `.map/` hierarchy; direct project-file "
                f"exploration remains allowed while Atlas is repaired: {exc}"
            )
            return {}, [
                _diagnostic(
                    "map.guidance_map_unreadable",
                    message,
                    path,
                    "Repair or rebuild the unreadable Landmark/Satellite Markdown, run Atlas `run`, then retry setup-guidance.",
                )
            ]
        if topology_diagnostics:
            message = (
                "Repository guidance requires a valid `.map/` hierarchy; direct project-file exploration "
                "remains allowed while Atlas is repaired."
            )
            return {}, [
                _diagnostic(
                    "map.guidance_setup_requires_valid_map",
                    message,
                    ".map",
                    "Build or repair the `.map/` Landmark and Satellite pages, run Atlas `run` to review exact diagnostics, then retry setup-guidance.",
                )
            ]
    try:
        if operation == "setup":
            lines = map_lines(pages)
            plan = [_plan_setup(root / name, lines) for name in TARGETS]
        else:
            plan = [_plan_remove(root / name) for name in TARGETS]
        _apply(plan)
    except (GuidanceError, OSError) as exc:
        message = str(exc)
        error_path = next((name for name in TARGETS if name in message), "AGENTS.md")
        code = (
            "map.guidance_rollback_incomplete"
            if isinstance(exc, GuidanceTransactionError) and exc.rollback_failures
            else "map.guidance_write_blocked"
        )
        repair = (
            "Report this diagnostic without editing the named instruction files; the user inspects and restores them from version control or backup before the guidance command is rerun."
            if code == "map.guidance_rollback_incomplete"
            else "Report this diagnostic without editing the named instruction files; the user repairs the reported marker, encoding, path, or write failure before the guidance command is rerun."
        )
        return {}, [
            _diagnostic(
                code,
                message,
                error_path,
                repair,
                phase=f"{operation}-guidance",
            )
        ]
    actions: dict[str, list[str]] = {name: [] for name in sorted({item.action for item in plan})}
    for item in plan:
        actions[item.action].append(item.path.name)
    return {"status": "complete", "operation": operation, "actions": actions}, []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--operation", choices=("setup", "remove"), required=True)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    if not root.is_dir():
        parser.error(f"repository root is not a directory: {root}")
    report, diagnostics = apply_guidance(root, args.operation)
    payload: object = {"diagnostics": diagnostics} if diagnostics else report
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 3 if diagnostics else 0


if __name__ == "__main__":
    raise SystemExit(main())

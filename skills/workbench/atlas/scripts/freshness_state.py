#!/usr/bin/env python3
"""Check and atomically baseline filesystem-native Atlas freshness."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, cast

from _diagnostic_contract import normalize_diagnostic, sorted_diagnostics
from _skill_protocol_runtime import compatible_version
from structure_state import Page, analyze

STATE_VERSION = "1.0.0"
STATE_PATH = PurePosixPath(".map/.state/freshness.json")
IGNORE_PATH = PurePosixPath(".mapignore")
DEFAULT_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "target",
        "vendor",
        "venv",
    }
)
CHUNK_SIZE = 1024 * 1024
EXAMPLE_LIMIT = 10


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _digest(value: object) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _examples(values: Iterable[str]) -> str:
    ordered = sorted(values)
    shown = ", ".join(repr(value) for value in ordered[:EXAMPLE_LIMIT])
    hidden = len(ordered) - EXAMPLE_LIMIT
    return f"{shown}, and {hidden} more" if hidden > 0 else shown


def _malformed(value: str) -> bool:
    return value != value.strip() or any(unicodedata.category(character) == "Cc" for character in value)


def _file_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _diagnostic(code: str, message: str, path: str, action: str, *, category: str) -> dict[str, Any]:
    return normalize_diagnostic(
        {
            "code": code,
            "category": category,
            "severity": "error",
            "message": message,
            "required_action": action,
            "valid_repairs": [action],
            "supporting_evidence": [path],
            "path": path,
        },
        skill="atlas",
        phase="freshness",
        artifact="freshness-state",
        path=path,
    )


def _read_ignore(root: Path) -> tuple[list[str], list[dict[str, Any]]]:
    path = root / IGNORE_PATH.as_posix()
    if not path.exists():
        return [], []
    diagnostics: list[dict[str, Any]] = []
    patterns: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return [], [
            _diagnostic(
                "map.ignore_unreadable",
                f"Map ignore policy cannot be read: {exc}.",
                IGNORE_PATH.as_posix(),
                "Write .mapignore as UTF-8 text or remove it.",
                category="malformed_input",
            )
        ]
    for number, raw in enumerate(lines, start=1):
        value = raw.strip().replace("\\", "/")
        if not value or value.startswith("#"):
            continue
        pure = PurePosixPath(value.rstrip("/"))
        if value.startswith(("/", "!")) or ".." in pure.parts:
            diagnostics.append(
                _diagnostic(
                    "map.ignore_pattern_unsafe",
                    f".mapignore line {number} is not a safe repository-relative glob: {raw}.",
                    IGNORE_PATH.as_posix(),
                    "Use a relative glob without negation, a leading slash, or parent traversal.",
                    category="unsafe_state",
                )
            )
            continue
        patterns.append(value)
    return sorted(set(patterns)), diagnostics


def _matches_ignore(path: PurePosixPath, patterns: Iterable[str]) -> bool:
    value = path.as_posix()
    for pattern in patterns:
        if pattern.endswith("/") and (value == pattern[:-1] or value.startswith(pattern)):
            return True
        if fnmatch.fnmatchcase(value, pattern) or path.match(pattern):
            return True
    return False


def _excluded(path: PurePosixPath, patterns: Iterable[str], *, directory: bool) -> str | None:
    if path == IGNORE_PATH:
        return "map-ignore-policy"
    if path == PurePosixPath("MAP.md") or (path.parts and path.parts[0] == ".map"):
        return "map-wiki-or-state"
    if any(part in DEFAULT_EXCLUDED_DIRS for part in path.parts[:-1]) or (
        directory and path.name in DEFAULT_EXCLUDED_DIRS
    ):
        return "dependency-cache-build-or-vcs"
    if _matches_ignore(path, patterns):
        return "mapignore"
    return None


def _contained(root: Path, path: Path) -> bool:
    try:
        return path.resolve(strict=True).is_relative_to(root.resolve(strict=True))
    except (OSError, RuntimeError):
        return False


def _directory_alias(resolved_root: Path, path: Path, relative: PurePosixPath) -> bool:
    def normalized(value: Path) -> str:
        text = str(value)
        if text.startswith("\\\\?\\UNC\\"):
            text = "\\\\" + text[len("\\\\?\\UNC\\") :]
        elif text.startswith("\\\\?\\"):
            text = text[len("\\\\?\\") :]
        return os.path.normcase(text)

    try:
        actual = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return True
    return normalized(actual) != normalized(resolved_root.joinpath(*relative.parts))


def scan_repository(
    root: Path,
    patterns: list[str],
) -> tuple[dict[str, dict[str, object]], dict[str, int], list[dict[str, Any]]]:
    resolved_root = root.resolve()
    manifest: dict[str, dict[str, object]] = {}
    excluded_counts: dict[str, int] = {}
    diagnostics: list[dict[str, Any]] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name, reverse=True)
        except OSError as exc:
            relative = PurePosixPath(directory.relative_to(root).as_posix())
            diagnostics.append(
                _diagnostic(
                    "map.freshness_path_unreadable",
                    f"Eligible repository directory cannot be read: {relative.as_posix()}: {exc}.",
                    relative.as_posix(),
                    "Restore read access or explicitly exclude the path in .mapignore.",
                    category="unavailable_prerequisite",
                )
            )
            continue
        for entry in entries:
            path = Path(entry.path)
            relative = PurePosixPath(path.relative_to(root).as_posix())
            try:
                is_directory = entry.is_dir(follow_symlinks=False)
            except OSError:
                is_directory = False
            reason = _excluded(relative, patterns, directory=is_directory)
            if reason is not None:
                excluded_counts[reason] = excluded_counts.get(reason, 0) + 1
                continue
            try:
                if entry.is_symlink() or (is_directory and _directory_alias(resolved_root, path, relative)):
                    if not _contained(root, path):
                        diagnostics.append(
                            _diagnostic(
                                "map.freshness_symlink_unsafe",
                                f"Eligible path resolves outside the repository: {relative.as_posix()}.",
                                relative.as_posix(),
                                "Replace the link or junction with contained files or explicitly exclude it in .mapignore.",
                                category="unsafe_state",
                            )
                        )
                    elif entry.is_dir(follow_symlinks=True):
                        diagnostics.append(
                            _diagnostic(
                                "map.freshness_directory_symlink_unsupported",
                                f"Freshness does not traverse directory links or junctions: {relative.as_posix()}.",
                                relative.as_posix(),
                                "Replace the directory link or junction or explicitly exclude it in .mapignore.",
                                category="contract_contradiction",
                            )
                        )
                    elif entry.is_file(follow_symlinks=True):
                        content_hash, size = _file_digest(path)
                        manifest[relative.as_posix()] = {
                            "content_sha256": content_hash,
                            "identity_sha256": _digest([relative.as_posix(), content_hash]),
                            "size": size,
                        }
                elif is_directory:
                    pending.append(path)
                elif entry.is_file(follow_symlinks=False):
                    content_hash, size = _file_digest(path)
                    manifest[relative.as_posix()] = {
                        "content_sha256": content_hash,
                        "identity_sha256": _digest([relative.as_posix(), content_hash]),
                        "size": size,
                    }
            except OSError as exc:
                diagnostics.append(
                    _diagnostic(
                        "map.freshness_path_unreadable",
                        f"Eligible repository file cannot be hashed: {relative.as_posix()}: {exc}.",
                        relative.as_posix(),
                        "Restore read access or explicitly exclude the path in .mapignore.",
                        category="unavailable_prerequisite",
                    )
                )
    portable: dict[str, str] = {}
    for manifest_path in sorted(manifest):
        folded = manifest_path.casefold()
        if folded in portable:
            diagnostics.append(
                _diagnostic(
                    "map.freshness_path_case_collision",
                    f"Eligible paths collide under portable case rules: {portable[folded]}, {manifest_path}.",
                    manifest_path,
                    "Rename the colliding files so every eligible repository path is portable.",
                    category="unsafe_state",
                )
            )
        else:
            portable[folded] = manifest_path
    return dict(sorted(manifest.items())), dict(sorted(excluded_counts.items())), diagnostics


def _satellite_state(
    pages: Mapping[PurePosixPath, Page],
    manifest: Mapping[str, Mapping[str, object]],
) -> tuple[dict[str, dict[str, object]], list[dict[str, Any]]]:
    satellites: dict[str, dict[str, object]] = {}
    diagnostics: list[dict[str, Any]] = []
    for page_path, page in sorted(pages.items()):
        if page.role != "satellite":
            continue
        source_paths: list[str] = []
        source_identities: list[list[str]] = []
        for source_path in sorted(page.source_links):
            value = source_path.as_posix()
            record = manifest.get(value)
            if record is None:
                diagnostics.append(
                    _diagnostic(
                        "map.freshness_source_excluded",
                        f"Satellite source binding is outside the eligible freshness universe: {page_path.as_posix()} -> {value}.",
                        page_path.as_posix(),
                        "Remove the exclusion or replace the link with an eligible regular source file.",
                        category="contract_contradiction",
                    )
                )
                continue
            source_paths.append(value)
            source_identities.append([value, str(record["identity_sha256"])])
        satellites[page_path.as_posix()] = {
            "content_sha256": page.content_sha256,
            "source_paths": source_paths,
            "source_fingerprint": _digest(source_identities),
        }
    return satellites, diagnostics


def _topology_fingerprint(pages: Mapping[PurePosixPath, Page]) -> str:
    rows = []
    for path, page in sorted(pages.items()):
        rows.append(
            {
                "path": path.as_posix(),
                "role": page.role,
                "parent": page.parent.as_posix() if page.parent else None,
                "content_sha256": page.content_sha256,
                "indexed_children": sorted(item.as_posix() for item in page.indexed_children),
                "cross_links": sorted(item.as_posix() for item in page.cross_links),
                "source_links": sorted(item.as_posix() for item in page.source_links),
            }
        )
    return _digest(rows)


def _valid_manifest(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return all(
        isinstance(path, str)
        and isinstance(item, dict)
        and set(item) == {"content_sha256", "identity_sha256", "size"}
        and isinstance(item["content_sha256"], str)
        and isinstance(item["identity_sha256"], str)
        and isinstance(item["size"], int)
        for path, item in value.items()
    )


def _valid_state(value: object) -> bool:
    if not isinstance(value, dict) or not compatible_version(value.get("schema_version"), STATE_VERSION):
        return False
    if not (
        isinstance(value.get("policy"), dict)
        and isinstance(value["policy"].get("fingerprint"), str)
        and isinstance(value["policy"].get("default_excluded_directories"), list)
        and isinstance(value["policy"].get("patterns"), list)
        and isinstance(value.get("repository"), dict)
        and isinstance(value["repository"].get("fingerprint"), str)
        and _valid_manifest(value["repository"].get("manifest"))
        and isinstance(value.get("topology"), dict)
        and isinstance(value["topology"].get("fingerprint"), str)
        and isinstance(value.get("satellites"), dict)
        and isinstance(value.get("receipts"), dict)
    ):
        return False
    policy_body = {
        "default_excluded_directories": value["policy"]["default_excluded_directories"],
        "patterns": value["policy"]["patterns"],
    }
    if value["policy"]["fingerprint"] != _digest(policy_body):
        return False
    manifest = value["repository"]["manifest"]
    if value["repository"]["fingerprint"] != _digest(manifest):
        return False
    satellites = value["satellites"]
    for path, item in satellites.items():
        if (
            not isinstance(path, str)
            or not isinstance(item, dict)
            or set(item) != {"content_sha256", "source_paths", "source_fingerprint"}
            or not isinstance(item["content_sha256"], str)
            or not isinstance(item["source_paths"], list)
            or not all(isinstance(source, str) and source in manifest for source in item["source_paths"])
            or not isinstance(item["source_fingerprint"], str)
        ):
            return False
        identities = [[source, manifest[source]["identity_sha256"]] for source in item["source_paths"]]
        if item["source_fingerprint"] != _digest(identities):
            return False
    receipts = value["receipts"]
    obligations = receipts.get("obligations")
    reviewed = receipts.get("reviewed_satellites")
    acknowledged = receipts.get("acknowledged_unmapped")
    previous_repository = receipts.get("previous_repository_fingerprint")
    if (
        not isinstance(receipts.get("cycle_fingerprint"), str)
        or previous_repository is not None and not isinstance(previous_repository, str)
        or not isinstance(obligations, dict)
        or set(obligations) != {"satellites", "unmapped_paths", "policy_changed", "topology_changed"}
        or not isinstance(obligations["satellites"], list)
        or not isinstance(obligations["unmapped_paths"], list)
        or not isinstance(obligations["policy_changed"], bool)
        or not isinstance(obligations["topology_changed"], bool)
        or not isinstance(reviewed, dict)
        or not isinstance(acknowledged, list)
        or set(reviewed) != set(obligations["satellites"])
        or set(acknowledged) != set(obligations["unmapped_paths"])
    ):
        return False
    expected_cycle = _digest(
        {
            "previous_repository": previous_repository,
            "current_repository": value["repository"]["fingerprint"],
            "current_policy": value["policy"]["fingerprint"],
            "current_topology": value["topology"]["fingerprint"],
            "obligations": obligations,
        }
    )
    if receipts["cycle_fingerprint"] != expected_cycle:
        return False
    for path, receipt in reviewed.items():
        if (
            path not in satellites
            or not isinstance(receipt, dict)
            or receipt.get("outcome") not in {"updated", "unchanged"}
            or receipt.get("content_sha256") != satellites[path]["content_sha256"]
            or receipt.get("source_fingerprint") != satellites[path]["source_fingerprint"]
        ):
            return False
    return True


def _load_state(root: Path) -> tuple[dict[str, Any] | None, str, list[dict[str, Any]]]:
    path = root / STATE_PATH.as_posix()
    if not path.is_file():
        return None, "missing", []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError):
        return None, "malformed", []
    try:
        valid = _valid_state(value)
    except (TypeError, ValueError, KeyError, AttributeError, RecursionError):
        valid = False
    if not valid:
        return None, "incompatible", []
    return value, "valid", []


def _manifest_deltas(
    previous: Mapping[str, Mapping[str, object]],
    current: Mapping[str, Mapping[str, object]],
) -> dict[str, Any]:
    old_paths = set(previous)
    new_paths = set(current)
    added = sorted(new_paths - old_paths)
    deleted = sorted(old_paths - new_paths)
    modified = sorted(
        path
        for path in old_paths & new_paths
        if previous[path].get("identity_sha256") != current[path].get("identity_sha256")
    )
    moves: list[dict[str, str]] = []
    remaining_added = set(added)
    for old in deleted:
        old_hash = previous[old].get("content_sha256")
        candidates = sorted(
            path for path in remaining_added if current[path].get("content_sha256") == old_hash
        )
        if candidates:
            new = candidates[0]
            remaining_added.remove(new)
            moves.append({"from": old, "to": new})
    return {"added": added, "modified": modified, "deleted": deleted, "moves": moves}


def assess(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = root.resolve()
    _structure_report, pages, structure_diagnostics = analyze(root)
    patterns, ignore_diagnostics = _read_ignore(root)
    manifest, excluded_counts, scan_diagnostics = scan_repository(root, patterns)
    satellites, binding_diagnostics = _satellite_state(pages, manifest)
    diagnostics = sorted_diagnostics(
        [*structure_diagnostics, *ignore_diagnostics, *scan_diagnostics, *binding_diagnostics]
    )
    policy = {
        "default_excluded_directories": sorted(DEFAULT_EXCLUDED_DIRS),
        "patterns": patterns,
    }
    current: dict[str, Any] = {
        "policy": {**policy, "fingerprint": _digest(policy)},
        "repository": {"fingerprint": _digest(manifest), "manifest": manifest},
        "topology": {"fingerprint": _topology_fingerprint(pages)},
        "satellites": satellites,
    }
    previous, state_status, state_diagnostics = _load_state(root)
    if previous is None:
        previous_manifest: Mapping[str, Mapping[str, object]] = {}
        previous_satellites: Mapping[str, Mapping[str, object]] = {}
        previous_policy = ""
        previous_topology = ""
    else:
        previous_manifest = cast(Mapping[str, Mapping[str, object]], previous["repository"]["manifest"])
        previous_satellites = cast(Mapping[str, Mapping[str, object]], previous["satellites"])
        previous_policy = str(previous["policy"]["fingerprint"])
        previous_topology = str(previous["topology"]["fingerprint"])
    deltas = _manifest_deltas(previous_manifest, manifest)
    changed_paths = set(deltas["added"]) | set(deltas["modified"]) | set(deltas["deleted"])
    current_bindings: dict[str, set[str]] = {}
    previous_bindings: dict[str, set[str]] = {}
    for satellite, item in satellites.items():
        for source in cast(list[str], item.get("source_paths", [])):
            current_bindings.setdefault(str(source), set()).add(satellite)
    for satellite, previous_item in previous_satellites.items():
        for source in cast(list[str], previous_item.get("source_paths", [])):
            previous_bindings.setdefault(str(source), set()).add(satellite)
    affected: set[str] = {
        path for path, item in satellites.items() if previous_satellites.get(path) != item
    }
    unmapped: list[str] = []
    for source in sorted(changed_paths):
        candidates = (current_bindings.get(source, set()) | previous_bindings.get(source, set())) & set(satellites)
        if candidates:
            affected.update(candidates)
        else:
            unmapped.append(source)
    policy_changed = previous_policy != current["policy"]["fingerprint"]
    topology_changed = previous_topology != current["topology"]["fingerprint"]
    current_state = (
        state_status == "valid"
        and not changed_paths
        and not affected
        and not unmapped
        and not policy_changed
        and not topology_changed
    )
    obligations = {
        "satellites": sorted(affected),
        "unmapped_paths": unmapped,
        "policy_changed": policy_changed,
        "topology_changed": topology_changed,
    }
    cycle = _digest(
        {
            "previous_repository": previous.get("repository", {}).get("fingerprint") if previous else None,
            "current_repository": current["repository"]["fingerprint"],
            "current_policy": current["policy"]["fingerprint"],
            "current_topology": current["topology"]["fingerprint"],
            "obligations": obligations,
        }
    )
    report = {
        "status": "current" if current_state else "review-required",
        "state_status": state_status,
        "cycle_fingerprint": cycle,
        "deltas": deltas,
        "obligations": obligations,
        "excluded": {"counts": excluded_counts, "patterns": patterns},
        "current": current,
        "previous": previous,
    }
    return report, sorted_diagnostics([*diagnostics, *state_diagnostics])


def _acknowledgement_diagnostics(
    expected_satellites: set[str],
    expected_unmapped: set[str],
    reviewed_satellites: set[str],
    acknowledged_unmapped: set[str],
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    cases = (
        ("satellite", expected_satellites, reviewed_satellites),
        ("unmapped", expected_unmapped, acknowledged_unmapped),
    )
    for kind, expected, supplied in cases:
        missing = expected - supplied
        if missing:
            diagnostics.append(
                _diagnostic(
                    f"map.freshness_{kind}_review_missing",
                    f"{len(missing)} required {kind} freshness decision(s) were not acknowledged: {_examples(missing)}.",
                    STATE_PATH.as_posix(),
                    "Review the exact current obligations and pass their repository-relative paths to baseline.",
                    category="missing_evidence",
                )
            )
        stale = supplied - expected
        if stale:
            diagnostics.append(
                _diagnostic(
                    f"map.freshness_{kind}_review_stale",
                    f"{len(stale)} supplied {kind} acknowledgement(s) are not exact current obligations; received: {_examples(stale)}.",
                    STATE_PATH.as_posix(),
                    "Discard stale acknowledgements, rerun check, and acknowledge only current obligations.",
                    category="stale_evidence",
                )
            )
    return diagnostics


def _atomic_write_state(root: Path, state: dict[str, Any]) -> None:
    if not _valid_state(state):
        raise ValueError("refusing to publish invalid freshness state")
    destination = root / STATE_PATH.as_posix()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_bytes(state) + b"\n"
    handle, temporary_name = tempfile.mkstemp(prefix="freshness-", suffix=".tmp", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        parsed = json.loads(temporary.read_text(encoding="utf-8"))
        if not _valid_state(parsed):
            raise ValueError("temporary freshness state failed validation")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def baseline(
    root: Path,
    cycle_fingerprint: str,
    reviewed_satellites: Iterable[str],
    acknowledged_unmapped: Iterable[str],
    acknowledge_all_unmapped: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reviewed_values = list(reviewed_satellites)
    acknowledged_values = list(acknowledged_unmapped)
    report, diagnostics = assess(root)
    blocking = [item for item in diagnostics if not str(item["code"]).startswith("map.freshness_state_")]
    expected_satellites = set(report["obligations"]["satellites"])
    expected_unmapped = set(report["obligations"]["unmapped_paths"])
    malformed: list[dict[str, Any]] = []
    for name, values, exact in (
        ("cycle_fingerprint", [cycle_fingerprint], {report["cycle_fingerprint"]}),
        ("reviewed_satellite", reviewed_values, expected_satellites),
        ("acknowledged_unmapped", acknowledged_values, expected_unmapped),
    ):
        bad = {value for value in values if value not in exact and _malformed(value)}
        if bad:
            malformed.append(
                _diagnostic(
                    "map.freshness_input_malformed",
                    f"Input {name} has {len(bad)} value(s) with control characters or surrounding whitespace: {_examples(bad)}.",
                    STATE_PATH.as_posix(),
                    "Pass exact values without control characters or surrounding whitespace (for example, strip CRLF line endings), then rerun baseline.",
                    category="malformed_input",
                )
            )
    if malformed:
        return report, sorted_diagnostics([*blocking, *malformed])
    if acknowledge_all_unmapped and acknowledged_values:
        ambiguous = _diagnostic(
            "map.freshness_acknowledgement_ambiguous",
            "acknowledge_unmapped=all cannot be combined with acknowledged_unmapped paths.",
            STATE_PATH.as_posix(),
            "Pass either acknowledge_unmapped=all or one acknowledged_unmapped path per obligation, not both.",
            category="malformed_input",
        )
        return report, sorted_diagnostics([*blocking, ambiguous])
    cycle_diagnostics: list[dict[str, Any]] = []
    if cycle_fingerprint != report["cycle_fingerprint"]:
        cycle_diagnostics.append(
            _diagnostic(
                "map.freshness_cycle_stale",
                "Baseline cycle does not match the exact current freshness assessment.",
                STATE_PATH.as_posix(),
                "Rerun check, review its current obligations, and pass the returned cycle fingerprint.",
                category="stale_evidence",
            )
        )
    supplied_satellites = set(reviewed_values)
    supplied_unmapped = set(expected_unmapped) if acknowledge_all_unmapped else set(acknowledged_values)
    acknowledgements = _acknowledgement_diagnostics(
        expected_satellites,
        expected_unmapped,
        supplied_satellites,
        supplied_unmapped,
    )
    if blocking or cycle_diagnostics or acknowledgements:
        return report, sorted_diagnostics([*blocking, *cycle_diagnostics, *acknowledgements])
    previous_satellites = (
        report["previous"].get("satellites", {}) if isinstance(report.get("previous"), dict) else {}
    )
    receipts = {
        "cycle_fingerprint": report["cycle_fingerprint"],
        "previous_repository_fingerprint": (
            report["previous"].get("repository", {}).get("fingerprint")
            if isinstance(report.get("previous"), dict)
            else None
        ),
        "obligations": report["obligations"],
        "reviewed_satellites": {
            path: {
                "outcome": "unchanged"
                if isinstance(previous_satellites.get(path), dict)
                and previous_satellites[path].get("content_sha256")
                == report["current"]["satellites"][path]["content_sha256"]
                and previous_satellites[path].get("source_paths")
                == report["current"]["satellites"][path]["source_paths"]
                else "updated",
                "content_sha256": report["current"]["satellites"][path]["content_sha256"],
                "source_fingerprint": report["current"]["satellites"][path]["source_fingerprint"],
            }
            for path in sorted(supplied_satellites)
        },
        "acknowledged_unmapped": sorted(supplied_unmapped),
    }
    state = {"schema_version": STATE_VERSION, **report["current"], "receipts": receipts}
    _atomic_write_state(root.resolve(), state)
    return {
        "status": "current",
        "state_path": STATE_PATH.as_posix(),
        "repository_fingerprint": state["repository"]["fingerprint"],
        "topology_fingerprint": state["topology"]["fingerprint"],
        "receipts": receipts,
    }, []


def _render_public(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in report.items()
        if key not in {"current", "previous"}
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--operation", choices=("check", "baseline"), default="check")
    parser.add_argument("--cycle-fingerprint")
    parser.add_argument("--reviewed-satellite", action="append", default=[])
    parser.add_argument("--acknowledged-unmapped", action="append", default=[])
    parser.add_argument("--acknowledge-unmapped", choices=("all",))
    args = parser.parse_args()
    root = args.repo_root.resolve()
    if not root.is_dir():
        parser.error(f"repository root is not a directory: {root}")
    if args.operation != "baseline" and (
        args.cycle_fingerprint or args.reviewed_satellite or args.acknowledged_unmapped or args.acknowledge_unmapped
    ):
        parser.error("cycle and acknowledgements are valid only with baseline")
    if args.operation == "check":
        report, diagnostics = assess(root)
        report = _render_public(report)
    else:
        if not args.cycle_fingerprint:
            parser.error("baseline requires --cycle-fingerprint")
        report, diagnostics = baseline(
            root,
            args.cycle_fingerprint,
            args.reviewed_satellite,
            args.acknowledged_unmapped,
            acknowledge_all_unmapped=args.acknowledge_unmapped == "all",
        )
    payload: object = {"diagnostics": diagnostics} if diagnostics else report
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 3 if diagnostics else 0


if __name__ == "__main__":
    raise SystemExit(main())

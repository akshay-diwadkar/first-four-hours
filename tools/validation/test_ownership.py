#!/usr/bin/env python3
"""Select and run finite, owned repository validation tests."""

from __future__ import annotations

# Public command execution starts in a contained worker before project imports.
import sys as _sys
import time as _time

_VALIDATION_START = _time.monotonic()
from pathlib import Path as _Path

from validation_budget import bounded_main as _bounded_main

_REPO_ROOT = _Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _REPO_ROOT / "tools" / "validation" / "test-ownership.json"

if __name__ == "__main__":
    raise SystemExit(_bounded_main(_Path(__file__), _sys.argv[1:], _REPO_ROOT, started_at=_VALIDATION_START,
                                  manifest=_MANIFEST_PATH, expect_cases=_sys.argv[1:2] == ["run"] and "--dry-run" not in _sys.argv[2:]))

import argparse
import ast
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from size_cap import MAX_TOTAL_ITEMS, SKILL_NAMES, case_group, normalize_test_target
from validation_budget import MAX_STREAM_BYTES, OutputLimitError, run_capture

ROOT = _REPO_ROOT
MANIFEST_PATH = _MANIFEST_PATH
POLICY_FILE_EXTENSIONS = {".json", ".md", ".py", ".toml", ".txt", ".yml", ".yaml"}
UNIVERSAL_TARGETS = [
    "tests/repository/test_routine_validation.py::test_live_repository_metadata",
]
# Deterministic size cap on the gated suite. Counting collected items rather
# than wall time keeps it machine-independent: a loaded host cannot cause a false
# failure, and one function parametrized many times counts as heavily as many
# separate functions, so the cap cannot be side-stepped by merging tests.
MAX_GATED_ITEMS_KEY = "max_gated_items"


@dataclass(frozen=True)
class Change:
    status: str
    old_path: str | None
    new_path: str | None

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(path for path in (self.old_path, self.new_path) if path is not None)


def _norm(path: str | Path) -> str:
    return str(path).replace("\\", "/")


def _safe_relative(path: str) -> bool:
    p = Path(path.replace("\\", "/"))
    return bool(path) and not p.is_absolute() and ":" not in path and ".." not in p.parts and not path.startswith("//")


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _run_git(root: Path, args: list[str]) -> bytes:
    result = run_capture(["git", *args], cwd=root)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace") or f"git {' '.join(args)} exited {result.returncode}")
    return result.stdout


def tracked_paths(root: Path = ROOT) -> list[str]:
    """Return current tracked and untracked, nonignored paths in stable order."""
    raw = _run_git(root, ["ls-files", "--cached", "--others", "--exclude-standard", "-z"])
    return sorted({_norm(path) for path in raw.decode("utf-8", errors="surrogateescape").split("\0") if path})


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("test ownership manifest must be a JSON object")
    return value


def _rule_matches(path: str, rule: dict[str, Any]) -> bool:
    relative = _norm(path).strip("/")
    for prefix in rule.get("path_prefixes", []):
        normalized = _norm(prefix).strip("/")
        if relative == normalized or relative.startswith(normalized + "/"):
            if any(relative == _norm(ex).strip("/") or relative.startswith(_norm(ex).strip("/") + "/") for ex in rule.get("exclude_prefixes", [])):
                continue
            return True
    return False


def resolve_path(path: str, manifest: dict[str, Any] | None = None) -> dict[str, Any] | None:
    payload = manifest if manifest is not None else load_manifest()
    matches = [rule for rule in payload.get("rules", []) if _rule_matches(path, rule)]
    return matches[0] if len(matches) == 1 else None


def _node_parts(node: str) -> list[tuple[str, str | None]]:
    # Like pytest, split the hierarchy before the opaque parameter suffix.
    hierarchy, marker, param = node.partition("[")
    parts: list[tuple[str, str | None]] = [(name, None) for name in hierarchy.split("::")]
    if marker:
        parts[-1] = (parts[-1][0], marker + param)
    return parts


def _node_segments(node: str) -> list[str]:
    return [name for name, _ in _node_parts(node)]


def _target_path(target: str, root: Path) -> tuple[Path, list[str]] | None:
    file_part, separator, node = target.partition("::")
    if not _safe_relative(file_part) or (separator and not node):
        return None
    path = root / normalize_test_target(file_part)
    if not path.is_file() or not _within(path, root):
        return None
    return path, _node_segments(node) if separator else []


@functools.lru_cache(maxsize=None)
def _parse_target_source(source: str, filename: str) -> ast.Module:
    """Parse identical target source once per process; callers still read and check the live file."""
    return ast.parse(source, filename=filename)


def _ast_node_exists(body: list[ast.stmt], segments: list[str]) -> bool:
    if not segments:
        return True
    name, *rest = segments
    node = next((item for item in body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and item.name == name), None)
    return node is not None and _ast_node_exists(node.body, rest)


def _validate_target(target: Any, root: Path, owner: str, errors: list[str]) -> None:
    if not isinstance(target, str):
        errors.append(f"owner {owner}: test target must be a string")
        return
    resolved = _target_path(target, root)
    if resolved is None:
        errors.append(f"owner {owner}: test target is unsafe or missing: {target}")
        return
    path, nodes = resolved
    if path.is_dir():
        errors.append(f"owner {owner}: directory test targets are forbidden: {target}")
        return
    if path.suffix != ".py":
        errors.append(f"owner {owner}: test target must be Python: {target}")
        return
    try:
        case_group(target)
    except ValueError as exc:
        errors.append(f"owner {owner}: {exc}")
    try:
        tree = _parse_target_source(path.read_text(encoding="utf-8"), target.partition("::")[0])
    except (OSError, UnicodeError, SyntaxError) as exc:
        errors.append(f"owner {owner}: cannot parse target {target}: {exc}")
        return
    if nodes and not _ast_node_exists(tree.body, nodes):
        errors.append(f"owner {owner}: pytest node does not exist: {target}")


def _whole_module_targets(manifest: dict[str, Any]) -> set[str]:
    targets: set[str] = set()
    for owner in manifest.get("owners", {}).values():
        if not isinstance(owner, dict) or not isinstance(owner.get("test_targets"), list):
            continue
        for target in owner["test_targets"]:
            if isinstance(target, str) and "::" not in target and _safe_relative(target):
                targets.add(normalize_test_target(target))
    return targets


def _is_pytest_module(path: str) -> bool:
    name = Path(path).name
    return path.startswith("tests/") and name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


def _path_inventory(manifest: dict[str, Any], root: Path, paths: Iterable[str], errors: list[str]) -> None:
    paths = list(paths)
    modules = _whole_module_targets(manifest)
    for path in paths:
        if _is_pytest_module(path) and (root / path).is_file():
            try:
                case_group(path)
            except ValueError as exc:
                errors.append(str(exc))
            if path not in modules:
                errors.append(f"{path}: live pytest module requires a whole-module owner target")
    scope = manifest.get("scope_prefixes", [])
    rules = manifest.get("rules", [])
    for path in paths:
        if not any(path == prefix or path.startswith(prefix.rstrip("/") + "/") for prefix in scope):
            continue
        if sum(_rule_matches(path, rule) for rule in rules) != 1:
            errors.append(f"{path}: expected exactly one ownership rule")

    inventory = manifest.get("inventory", {})
    restricted = inventory.get("restricted_roots", [])
    for item in paths:
        for restriction in restricted:
            prefix = restriction.get("path_prefix", "")
            allowed = restriction.get("allowed_prefixes", [])
            if item == prefix or item.startswith(prefix.rstrip("/") + "/"):
                if not any(item == entry or item.startswith(entry.rstrip("/") + "/") for entry in allowed):
                    errors.append(f"{item}: path is outside permitted {prefix} inventory")
        if any(item == p or item.startswith(p.rstrip("/") + "/") for p in inventory.get("forbidden_prefixes", [])):
            errors.append(f"{item}: forbidden inventory path")
        if any(item.startswith(p) for p in inventory.get("forbidden_file_prefixes", [])):
            errors.append(f"{item}: forbidden file family")
        if any(item == p or item.startswith(p.rstrip("/") + "/") for p in inventory.get("forbidden_paths", [])):
            if (root / item).exists():
                errors.append(f"{item}: forbidden inventory path")
        for pattern in inventory.get("policy_drift_patterns", []):
            roots = pattern.get("roots", [])
            prefixes = pattern.get("prefixes", [])
            if not any(r in {"", "."} or item == r or item.startswith(r.rstrip("/") + "/") for r in roots):
                continue
            if _policy_component_match(item, prefixes):
                errors.append(f"{item}: {pattern.get('reason', 'policy-drift path')}")


def validate_manifest(manifest: dict[str, Any], *, root: Path = ROOT, paths: Iterable[str] | None = None) -> list[str]:
    """Validate schema, exact bounded targets, path rules, and current inventory."""
    errors: list[str] = []
    allowed_fields = {"schema_version", "description", "owners", "rules", "scope_prefixes", "inventory", "skill_owners", "universal_targets", "limits"}
    if set(manifest) != allowed_fields:
        errors.append("test ownership manifest must contain only its supported top-level fields")
    if manifest.get("schema_version") != "1.0.0":
        errors.append("test ownership manifest schema_version must be '1.0.0'")
    owners = manifest.get("owners")
    if not isinstance(owners, dict) or not owners:
        errors.append("test ownership manifest owners must be a non-empty object")
        owners = {}
        manifest = {**manifest, "owners": owners}
    expected_skill_owners = {name: f"{name}-runtime-contract" for name in SKILL_NAMES}
    expected_skill_owners["reason"] = "reason-guidance-contract"
    if manifest.get("skill_owners") != expected_skill_owners:
        errors.append(f"skill_owners must map the exact {len(SKILL_NAMES)} skills to their declared finite owner")
    skill_owners = manifest.get("skill_owners")
    if isinstance(skill_owners, dict):
        for skill, owner in skill_owners.items():
            if not isinstance(owner, str) or owner not in owners:
                errors.append(f"skill_owners {skill}: unknown owner {owner!r}")
    if manifest.get("universal_targets") != UNIVERSAL_TARGETS:
        errors.append("universal_targets must contain the exact routine validation nodes")
    for name, owner in owners.items():
        if not isinstance(owner, dict):
            errors.append(f"owner {name}: definition must be an object")
            continue
        if set(owner) - {"test_targets", "skill_scoped", "description"}:
            errors.append(f"owner {name}: only test_targets, skill_scoped, and description fields are supported")
        targets = owner.get("test_targets")
        if name == "skill-contracts":
            if owner.get("skill_scoped") is not True or targets not in (None, []):
                errors.append("skill-contracts must set skill_scoped:true and no test targets")
            continue
        if not isinstance(targets, list) or not targets:
            errors.append(f"owner {name}: finite non-empty test_targets are required")
            continue
        for target in targets:
            _validate_target(target, root, name, errors)
    rules = manifest.get("rules")
    if not isinstance(rules, list) or not rules:
        errors.append("ownership rules must be a non-empty list")
        rules = []
    rule_ids: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("id"), str):
            errors.append("each ownership rule requires an id")
            continue
        if rule["id"] in rule_ids:
            errors.append(f"duplicate rule id: {rule['id']}")
        rule_ids.add(rule["id"])
        prefixes = rule.get("path_prefixes")
        excludes = rule.get("exclude_prefixes", [])
        if not isinstance(prefixes, list) or not prefixes or any(not isinstance(prefix, str) or not prefix for prefix in prefixes):
            errors.append(f"rule {rule['id']}: path_prefixes must be a non-empty string list")
            prefixes = []
        if not isinstance(excludes, list) or any(not isinstance(prefix, str) or not prefix for prefix in excludes):
            errors.append(f"rule {rule['id']}: exclude_prefixes must be a string list")
            excludes = []
        if rule.get("resolution", "owned") == "owned" and rule.get("owner") not in owners:
            errors.append(f"rule {rule['id']}: unknown owner")
        elif rule.get("resolution") not in (None, "owned", "deferred"):
            errors.append(f"rule {rule['id']}: invalid resolution")
        for prefix in [*prefixes, *excludes]:
            if not _safe_relative(prefix):
                errors.append(f"rule {rule['id']}: unsafe path prefix {prefix!r}")
    scope_prefixes = manifest.get("scope_prefixes", [])
    if not isinstance(scope_prefixes, list) or any(not _safe_relative(prefix) for prefix in scope_prefixes):
        errors.append("scope_prefixes must be safe repository-relative paths")
        scope_prefixes = []
    for prefix in scope_prefixes:
        if prefix not in {".", ""} and not _safe_relative(prefix):
            errors.append(f"unsafe scope prefix: {prefix}")
    limits = manifest.get("limits")
    if not isinstance(limits, dict):
        errors.append("limits must be an object")
    else:
        unknown_limits = set(limits) - {MAX_GATED_ITEMS_KEY}
        if unknown_limits:
            errors.append(f"limits contains unknown keys: {sorted(unknown_limits)}")
        cap = limits.get(MAX_GATED_ITEMS_KEY)
        if not isinstance(cap, int) or isinstance(cap, bool) or not 1 <= cap <= MAX_TOTAL_ITEMS:
            errors.append(f"limits.{MAX_GATED_ITEMS_KEY} must be a positive integer no greater than {MAX_TOTAL_ITEMS}")
    inventory = manifest.get("inventory")
    inventory_shape_ok = True
    if not isinstance(inventory, dict):
        errors.append("inventory must be an object")
        manifest = {**manifest, "inventory": {}}
        inventory_shape_ok = False
    else:
        inventory_lists = ("restricted_roots", "forbidden_prefixes", "forbidden_file_prefixes", "forbidden_paths", "policy_drift_patterns")
        for key in inventory_lists:
            if key in inventory and not isinstance(inventory[key], list):
                errors.append(f"inventory {key} must be a list")
                inventory_shape_ok = False
        if isinstance(inventory.get("restricted_roots", []), list):
            for entry in inventory.get("restricted_roots", []):
                if not isinstance(entry, dict) or not isinstance(entry.get("path_prefix"), str) or not isinstance(entry.get("allowed_prefixes"), list):
                    errors.append("inventory restricted_roots entries require path_prefix and allowed_prefixes")
                    inventory_shape_ok = False
        if isinstance(inventory.get("policy_drift_patterns", []), list):
            for entry in inventory.get("policy_drift_patterns", []):
                if not isinstance(entry, dict) or not isinstance(entry.get("roots"), list) or not isinstance(entry.get("prefixes"), list):
                    errors.append("inventory policy_drift_patterns entries require roots and prefixes")
                    inventory_shape_ok = False
        if inventory_shape_ok:
            inventory_prefixes: list[str] = []
            for entry in inventory.get("restricted_roots", []):
                inventory_prefixes.extend([entry["path_prefix"], *entry["allowed_prefixes"]])
            for key in ("forbidden_prefixes", "forbidden_file_prefixes", "forbidden_paths"):
                inventory_prefixes.extend(inventory.get(key, []))
            for entry in inventory.get("policy_drift_patterns", []):
                inventory_prefixes.extend(entry["roots"])
                inventory_prefixes.extend(entry["prefixes"])
            for prefix in inventory_prefixes:
                if not isinstance(prefix, str) or not prefix or (prefix not in {"", "."} and not _safe_relative(prefix)):
                    errors.append(f"inventory contains unsafe prefix: {prefix!r}")
    inventory_paths = sorted(set(paths if paths is not None else tracked_paths(root)))
    if paths is None:
        inventory_paths = [path for path in inventory_paths if (root / path).exists()]
    if inventory_shape_ok:
        _path_inventory(manifest, root, inventory_paths, errors)
    return sorted(set(errors))


def validate(root: Path = ROOT) -> list[str]:
    try:
        return validate_manifest(load_manifest(root / "tools" / "validation" / "test-ownership.json"), root=root)
    except (OSError, ValueError, RuntimeError) as exc:
        return [str(exc)]


def _parse_git_changes(root: Path, base_ref: str) -> list[Change]:
    base = _run_git(root, ["merge-base", base_ref, "HEAD"]).decode("ascii", errors="replace").strip()
    if not base:
        raise RuntimeError(f"cannot resolve merge-base for {base_ref!r}")
    tokens = _run_git(root, ["diff", "--name-status", "-z", "-M", base]).decode("utf-8", errors="surrogateescape").split("\0")
    changes: list[Change] = []
    index = 0
    while index < len(tokens) and tokens[index]:
        status = tokens[index]
        index += 1
        if status.startswith("R") or status.startswith("C"):
            if index + 1 >= len(tokens):
                raise RuntimeError("malformed NUL-delimited rename record from git diff")
            old, new = tokens[index], tokens[index + 1]
            index += 2
            changes.append(Change(status[0], old, new))
        else:
            if index >= len(tokens):
                raise RuntimeError("malformed NUL-delimited path record from git diff")
            path = tokens[index]
            index += 1
            changes.append(Change(status[0], path if status == "D" else None, None if status == "D" else path))
    untracked = _run_git(root, ["ls-files", "--others", "--exclude-standard", "-z"]).decode("utf-8", errors="surrogateescape")
    changes.extend(Change("?", None, path) for path in untracked.split("\0") if path)
    return changes


def _skill_for_path(path: str) -> str | None:
    parts = _norm(path).split("/")
    if len(parts) >= 3 and parts[0] == "skills":
        return parts[2]
    if len(parts) >= 3 and parts[:2] == ["tests", "skills"]:
        return parts[2]
    return None


def _covers(
    other: tuple[str, list[tuple[str, str | None]] | None],
    target: tuple[str, list[tuple[str, str | None]] | None],
) -> bool:
    other_file, other_parts = other
    file_part, parts = target
    if other_file != file_part:
        return False
    if other_parts is None:
        return True
    if parts is None or len(other_parts) > len(parts):
        return False
    return all(
        other_name == target_name and other_param in (None, target_param)
        for (other_name, other_param), (target_name, target_param) in zip(other_parts, parts)
    )


def _normalize_targets(targets: Iterable[str]) -> list[str]:
    unique = sorted({normalize_test_target(target) for target in targets})
    parsed: list[tuple[str, list[tuple[str, str | None]] | None]] = []
    for target in unique:
        file_part, separator, node = target.partition("::")
        parsed.append((file_part, _node_parts(node) if separator else None))
    kept = [
        target
        for index, target in enumerate(unique)
        if not any(_covers(parsed[other], parsed[index]) for other in range(len(unique)) if other != index)
    ]
    return kept


def _owner_for_path(path: str, manifest: dict[str, Any]) -> tuple[str | None, str]:
    matches = [rule for rule in manifest["rules"] if _rule_matches(path, rule)]
    if len(matches) != 1:
        return None, "unknown" if not matches else "overlapping"
    rule = matches[0]
    resolution = rule.get("resolution", "owned")
    if resolution == "deferred":
        return None, "deferred"
    owner = rule.get("owner")
    if owner == "skill-contracts":
        skill = _skill_for_path(path)
        owner = manifest.get("skill_owners", {}).get(skill)
    return (owner, "owned") if owner in manifest["owners"] else (None, "unknown")


def select_changed_paths(
    paths: Iterable[str] | None = None,
    *, manifest: dict[str, Any] | None = None,
    root: Path = ROOT,
    changes: Iterable[Change] | None = None,
    all_profiles: bool = False,
    tests: Iterable[str] = (),
) -> dict[str, Any]:
    payload = manifest if manifest is not None else load_manifest(root / "tools" / "validation" / "test-ownership.json")
    errors = validate_manifest(payload, root=root, paths=[])
    if errors:
        return {
            "valid": False, "scope": "required" if all_profiles else "changed", "selection_version": "1.0.0",
            "paths": [], "results": [], "selected": {"checks": []},
            "unknown": [], "deferred": [], "policy_drift": [], "errors": errors,
        }
    normalized_changes = list(changes or [Change("M", None, _norm(path)) for path in (paths or [])])
    path_records: list[dict[str, Any]] = []
    selected: list[str] = []
    unknown: list[str] = []
    deferred: list[str] = []
    policy_drift: list[str] = []
    for change in normalized_changes:
        for path in change.paths:
            if not _safe_relative(path):
                errors.append(f"unsafe or absolute path: {path}")
                continue
            owner, resolution = _owner_for_path(path, payload)
            path_records.append({"path": path, "status": change.status, "owner": owner, "resolution": resolution})
            if resolution == "deferred":
                deferred.append(path)
            elif owner is None:
                unknown.append(path)
            else:
                selected.extend(payload["owners"][owner].get("test_targets", []))
            if _policy_drift(path, payload):
                policy_drift.append(path)
    explicit_tests = list(tests)
    for target in explicit_tests:
        resolved = _target_path(target, root)
        if resolved is None or not target.partition("::")[1]:
            errors.append(f"--test requires an existing exact pytest node: {target}")
        else:
            _validate_target(target, root, "--test", errors)
            selected.append(target)
    if all_profiles:
        if normalized_changes:
            errors.append("--all cannot be combined with changed paths")
        selected.extend(UNIVERSAL_TARGETS)
        for owner in payload["owners"].values():
            selected.extend(owner.get("test_targets", []))
    elif not normalized_changes and not explicit_tests:
        errors.append("select/run requires --all, --path, --base-ref, or --test")
    selected.extend(UNIVERSAL_TARGETS)
    targets = _normalize_targets(selected)
    module_targets = _whole_module_targets(payload)
    for change in normalized_changes:
        for path in change.paths:
            live = root / path
            if _is_pytest_module(path) and live.is_file() and path not in module_targets:
                errors.append(f"{path}: live pytest module requires a whole-module owner target")
            if (live.exists() or live.is_symlink()) and not _within(live, root):
                errors.append(f"live path escapes repository: {path}")
            if live.is_file() and live.suffix == ".py":
                try:
                    ast.parse(live.read_text(encoding="utf-8"), filename=path)
                except (OSError, UnicodeError, SyntaxError) as exc:
                    errors.append(f"changed Python source is invalid: {path}: {exc}")
            elif live.is_file() and live.suffix == ".json":
                try:
                    json.loads(live.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    errors.append(f"changed JSON source is invalid: {path}: {exc}")
    return {
        "valid": not (errors or unknown or deferred or policy_drift),
        "scope": "required" if all_profiles else "focused" if explicit_tests and not normalized_changes else "changed",
        "selection_version": "1.0.0",
        "paths": sorted(path_records, key=lambda item: (item["path"], item["status"])),
        "results": [],
        "selected": {"checks": [{"id": "routine-tests", "kind": "pytest", "targets": targets}] if targets else []},
        "unknown": sorted(set(unknown)),
        "deferred": sorted(set(deferred)),
        "policy_drift": sorted(set(policy_drift)),
        "errors": sorted(set(errors)),
    }


def _policy_drift(path: str, manifest: dict[str, Any]) -> bool:
    inventory = manifest.get("inventory", {})
    for pattern in inventory.get("policy_drift_patterns", []):
        if any(root in {"", "."} or path == root or path.startswith(root.rstrip("/") + "/") for root in pattern.get("roots", [])):
            if _policy_component_match(path, pattern.get("prefixes", [])):
                return True
    return any(path == p or path.startswith(p.rstrip("/") + "/") for p in inventory.get("forbidden_prefixes", []))


def _policy_component_match(path: str, prefixes: list[str]) -> bool:
    for component in path.split("/"):
        for prefix in prefixes:
            if component == prefix or component.startswith((prefix + "_", prefix + "-")):
                return True
            if any(component.startswith(prefix + extension) for extension in POLICY_FILE_EXTENSIONS):
                return True
    return False


def _changes_for_args(args: argparse.Namespace, root: Path) -> list[Change]:
    changes = list(_parse_git_changes(root, args.base_ref)) if args.base_ref else []
    changes.extend(
        Change("M" if (root / _norm(path)).exists() else "D", None if (root / _norm(path)).exists() else _norm(path), _norm(path) if (root / _norm(path)).exists() else None)
        for path in args.path
    )
    return changes


# Test files run in at most this many concurrent pytest processes, so idle cores
# absorb host load; every case still counts against one supervisor deadline.
MAX_PARALLEL_SHARDS = 4


def _shards(root: Path, targets: list[str]) -> list[list[str]]:
    """Keep each file's targets together; pack the largest files first into the lightest shard."""
    groups: dict[str, list[str]] = {}
    for target in targets:
        groups.setdefault(target.partition("::")[0], []).append(target)

    def size(path: str) -> int:
        try:
            return (root / path).stat().st_size
        except OSError:
            return 0

    count = min(MAX_PARALLEL_SHARDS, len(groups))
    shards: list[list[str]] = [[] for _ in range(count)]
    loads = [0] * count
    for path in sorted(groups, key=lambda path: (-size(path), path)):
        lightest = loads.index(min(loads))
        shards[lightest].extend(groups[path])
        loads[lightest] += size(path)
    return shards


def _check_output(output: Any) -> None:
    if os.fstat(output.fileno()).st_size > MAX_STREAM_BYTES:
        raise OutputLimitError(f"pytest output exceeded {MAX_STREAM_BYTES} bytes")


def _replay(output: Any) -> None:
    output.seek(0)
    sys.stderr.flush()
    shutil.copyfileobj(output, sys.stderr.buffer)
    sys.stderr.buffer.flush()


# A running shard's unfinished last line is forwarded only when it is short and looks like
# pytest -q progress (status letters, then the start of a "[ NN%]" suffix); any other
# unfinished line, such as part of a traceback, waits for its newline or the shard's exit.
PROGRESS_TAIL = re.compile(rb"[.FEsxX]+(?: +\[ *\d*%?\]?)?")
PROGRESS_TAIL_BYTES = 256


def _run_shards(root: Path, command: list[str], shards: list[list[str]], env: dict[str, str], pytest_root: Path) -> int:
    """Start every shard at once and stream each shard's output to stderr as it arrives."""
    started: list[tuple[subprocess.Popen[bytes], Any, Any]] = []
    handles: list[Any] = []
    try:
        for index, shard in enumerate(shards, start=1):
            temp_root = pytest_root / f"shard-{index}"
            temp_root.mkdir()
            log = pytest_root / f"shard-{index}.log"
            # The child shares the write handle's position, so reading goes through its own handle.
            output = log.open("wb")
            handles.append(output)
            reader = log.open("rb")
            handles.append(reader)
            print(f"shard {index} start: {' '.join(shard)}", file=sys.stderr, flush=True)
            process = subprocess.Popen([*command, *shard], cwd=root, env={**env, "PYTEST_DEBUG_TEMPROOT": str(temp_root)}, stdout=output, stderr=subprocess.STDOUT)
            started.append((process, output, reader))
        # Forwarding as shards run keeps tracebacks and progress in the supervisor's
        # stderr tail even when the deadline stops the worker. Output never continues
        # another shard's unfinished line, so concurrent shards never share a line.
        pending = [b""] * len(started)
        open_line: int | None = None
        while True:
            finished = all(process.poll() is not None for process, _, _ in started)
            for index, (_, output, reader) in enumerate(started):
                _check_output(output)
                pending[index] += reader.read()
                cut = pending[index].rfind(b"\n") + 1
                tail = pending[index][cut:]
                if finished or (len(tail) <= PROGRESS_TAIL_BYTES and PROGRESS_TAIL.fullmatch(tail)):
                    cut = len(pending[index])
                if cut:
                    chunk = pending[index][:cut]
                    if open_line is not None and open_line != index:
                        chunk = b"\n" + chunk
                    sys.stderr.flush()
                    sys.stderr.buffer.write(chunk)
                    sys.stderr.buffer.flush()
                    pending[index] = pending[index][cut:]
                    open_line = None if chunk.endswith(b"\n") else index
            if finished:
                break
            time.sleep(0.05)
        # pytest exits 5 when a shard ends with no cases: a module-level skip, or a size-cap
        # refusal that clears its items. The selection already collected within the limits,
        # and the supervisor fails any collected case left incomplete, so neither can pass a run.
        codes = [0 if process.returncode == 5 else process.returncode for process, _, _ in started]
    finally:
        for process, _, _ in started:
            if process.poll() is None:
                process.kill()
                process.wait()
        for handle in handles:
            handle.close()
    # A test failure wins; otherwise report the first nonzero code (a signal-killed shard is negative).
    return 1 if 1 in codes else next((code for code in codes if code != 0), 0)


def run_pytest(root: Path, targets: list[str], cap: int) -> dict[str, Any]:
    """Execute targets once; the supervisor alone accounts for case verdicts."""
    pytest_env = {
        **os.environ,
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTEST_ADDOPTS": "",
        "PYTEST_PLUGINS": "",
        "PYTHONPATH": os.pathsep.join([str(ROOT), str(Path(__file__).resolve().parent), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep),
        "SKILLS_MAX_GATED_ITEMS": str(cap),
    }
    pytest_command = [sys.executable, "-m", "pytest", "-q", "--rootdir", str(root), "-p", "no:cacheprovider", "-p", "tools.validation.size_cap"]
    run_flags = ["-x", "--tb=short", "--durations=10"]
    shards = _shards(root, targets)
    # A private root avoids stale shared pytest directories and includes
    # cleanup in the contained worker's ceiling. No persistent cache is used
    # by this finite runner, so do not write one into the user's checkout.
    output_limit: OutputLimitError | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="skills-validation-") as pytest_root:
            try:
                case_report = Path(os.environ.get("SKILLS_CASE_REPORT", str(Path(pytest_root) / "cases.jsonl")))
                shard_env = {**pytest_env, "SKILLS_CASE_REPORT": str(case_report)}
                if len(shards) <= 1:
                    # One process collects every case, so its collection hook enforces the limits exactly.
                    returncode = subprocess.run(
                        [*pytest_command, *run_flags, *targets],
                        cwd=root, env={**shard_env, "PYTEST_DEBUG_TEMPROOT": pytest_root},
                        stdout=sys.stderr, stderr=sys.stderr, check=False,
                    ).returncode
                else:
                    # Count every selected case together before any shard runs a body.
                    collection_root = Path(pytest_root) / "collection"
                    collection_root.mkdir()
                    with tempfile.TemporaryFile(dir=pytest_root) as collection_output:
                        collection = subprocess.Popen(
                            [*pytest_command, "--collect-only", *targets],
                            cwd=root, env={**shard_env, "PYTEST_DEBUG_TEMPROOT": str(collection_root)},
                            stdout=collection_output, stderr=subprocess.STDOUT,
                        )
                        try:
                            # Bound collection output while it runs, as the shards' output is bounded.
                            while collection.poll() is None:
                                _check_output(collection_output)
                                time.sleep(0.05)
                            _check_output(collection_output)
                        finally:
                            if collection.poll() is None:
                                collection.kill()
                                collection.wait()
                        returncode = collection.returncode
                        if returncode != 0:
                            _replay(collection_output)
                    if returncode == 0:
                        returncode = _run_shards(root, [*pytest_command, *run_flags], shards, shard_env, Path(pytest_root))
            except OutputLimitError as exc:
                output_limit = exc
    except OSError:
        # A killed shard's lingering descendants can block temp-root removal on
        # Windows; that cleanup error must not replace the output-limit verdict.
        if output_limit is None:
            raise
    if output_limit is not None:
        raise output_limit
    errors = [] if returncode == 0 else [f"routine-tests pytest exited {returncode}"]
    return {"event": "result", "executed": [{"id": "routine-tests", "returncode": returncode, "targets": targets}], "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    for action in ("select", "explain", "run"):
        cmd = subparsers.add_parser(action)
        cmd.add_argument("--all", action="store_true")
        cmd.add_argument("--path", action="append", default=[])
        cmd.add_argument("--base-ref")
        cmd.add_argument("--test", action="append", default=[])
        cmd.add_argument("--format", choices=("json", "human"), default="json")
        if action == "run":
            cmd.add_argument("--dry-run", action="store_true")
            cmd.add_argument("--allow-fallback", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = ROOT
    try:
        manifest = load_manifest(MANIFEST_PATH)
        if args.command is None:
            errors = validate_manifest(manifest, root=root)
            print(json.dumps({"event": "validation", "valid": not errors, "errors": errors}, separators=(",", ":"), sort_keys=True))
            return 0 if not errors else 1
        if getattr(args, "allow_fallback", False):
            raise ValueError("--allow-fallback was removed; unknown paths fail closed")
        if args.all and (args.path or args.base_ref):
            raise ValueError("--all is mutually exclusive with --path and --base-ref")
        if args.command == "explain" and not (args.all or args.path or args.base_ref or args.test):
            raise ValueError("explain requires --all, --path, --base-ref, or --test")
        changes = _changes_for_args(args, root)
        inventory_paths = {path for path in tracked_paths(root) if (root / path).exists()}
        for change in changes:
            if change.status == "D" and change.old_path:
                inventory_paths.discard(_norm(change.old_path))
            if change.status == "R" and change.old_path:
                inventory_paths.discard(_norm(change.old_path))
            if change.new_path and (root / change.new_path).exists():
                inventory_paths.add(_norm(change.new_path))
        inventory_errors = validate_manifest(manifest, root=root, paths=inventory_paths)
        if inventory_errors:
            raise ValueError("manifest/inventory validation failed: " + "; ".join(inventory_errors))
        plan = select_changed_paths(manifest=manifest, root=root, changes=changes, all_profiles=args.all, tests=args.test)
        plan_line = {"event": "plan", "plan": plan}
        print(json.dumps(plan_line, separators=(",", ":"), sort_keys=True))
        if not plan["valid"]:
            return 2
        if args.command != "run" or args.dry_run:
            return 0
        targets = plan["selected"]["checks"][0]["targets"]
        cap = manifest.get("limits", {}).get(MAX_GATED_ITEMS_KEY)
        if not isinstance(cap, int) or isinstance(cap, bool):
            cap = 0
        execution = run_pytest(root, targets, cap)
        print(json.dumps(execution, separators=(",", ":"), sort_keys=True))
        returncode = execution["executed"][0]["returncode"]
        return 0 if returncode == 0 else 1 if returncode == 1 else 3
    except OutputLimitError:
        raise
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"event": "validation", "valid": False, "errors": [str(exc)]}, separators=(",", ":"), sort_keys=True), file=sys.stderr)
        return 2

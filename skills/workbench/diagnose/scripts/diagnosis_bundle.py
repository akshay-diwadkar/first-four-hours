#!/usr/bin/env python3
"""Validate and bind the minimal diagnosis input that seals diagnosis.md."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Collection
from pathlib import Path, PurePath, PurePosixPath
from typing import Any

from _skill_protocol_runtime import compatible_version
from diagnosis_handoff import CONTRACT_VERSION, contains_reserved_delimiter
from diagnosis_workspace import WORKSPACE_DIR, WORKSPACE_PARTS

EVIDENCE_KIND_FAMILIES = {
    "source": "current-file",
    "config": "current-file",
    "test": "current-file",
    "history": "history",
    "command": "command",
    "external": "external",
    "capture": "capture",
}
EVIDENCE_KINDS = frozenset(EVIDENCE_KIND_FAMILIES)
CURRENT_FILE_KINDS = frozenset(
    kind for kind, family in EVIDENCE_KIND_FAMILIES.items() if family == "current-file"
)
TOP_LEVEL_FIELDS = {"schema_version", "diagnosis_context", "findings"}
CONTEXT_FIELDS = {
    "target",
    "snapshot",
    "evidence_root",
    "material_surfaces",
    "limitations",
    "ruled_out",
    "open_probes",
}
SNAPSHOT_COMMON_FIELDS = {"kind", "project_root"}
SNAPSHOT_GIT_FIELDS = {*SNAPSHOT_COMMON_FIELDS, "repository_id", "revision"}
SURFACE_FIELDS = {"path", "start_line", "end_line", "sha256"}
FINDING_FIELDS = {"id", "title", "summary", "cause_or_boundary", "cause_status", "impact", "evidence"}
FILE_EVIDENCE_FIELDS = {*SURFACE_FIELDS, "kind", "observation"}
HISTORY_EVIDENCE_FIELDS = {*FILE_EVIDENCE_FIELDS, "revision"}
COMMAND_BASE_FIELDS = {"kind", "argv", "cwd", "status", "observation"}
COMMAND_RAN_FIELDS = {*COMMAND_BASE_FIELDS, "exit_code", "stdout", "stderr"}
COMMAND_NOT_RUN_FIELDS = {*COMMAND_BASE_FIELDS, "reason"}
OUTPUT_FIELDS = {"sha256", "excerpt", "truncated"}
EXTERNAL_EVIDENCE_FIELDS = {"kind", "locator", "observation"}
CAPTURE_EVIDENCE_FIELDS = {
    "kind",
    "path",
    "start_line",
    "end_line",
    "sha256",
    "provenance",
    "origin",
    "observation",
}
CAPTURE_PROVENANCES = frozenset({"agent-probe", "user-supplied", "exported"})
CAUSE_STATUSES = frozenset({"demonstrated", "inferred"})
RULED_OUT_FIELDS = {"hypothesis", "evidence"}
OPEN_PROBE_FIELDS = {"question", "probe", "expected_outcomes"}
UNVERIFIED_EVIDENCE_MESSAGE = (
    "must contain verified local evidence (current file, history, ran command, or capture)"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_OBJECT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
COMMAND_EXCERPT_LIMIT = 4096
GIT_TIMEOUT_SECONDS = 10


class DiagnosisBundleError(Exception):
    """Raised when a diagnosis bundle cannot be read or bound."""


@dataclasses.dataclass(frozen=True)
class BindingProof:
    """Captured objective facts used for the final pre-publication recheck."""

    snapshot: dict[str, str]
    bindings: tuple[tuple[str, str], ...]
    opened_paths: tuple[str, ...]
    git_commands: tuple[tuple[str, ...], ...]


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DiagnosisBundleError(f"input file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DiagnosisBundleError(f"invalid JSON in {path}: {exc}") from exc


def _object(value: Any, path: str, errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return None
    return value


def _objects(value: Any, path: str, errors: list[str], *, nonempty: bool = False) -> list[dict[str, Any]]:
    if not isinstance(value, list) or (nonempty and not value):
        qualifier = "a non-empty" if nonempty else "an"
        errors.append(f"{path} must be {qualifier} array of objects")
        return []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"{path}[{index}] must be an object")
        else:
            result.append(item)
    return result


def _string(obj: dict[str, Any], key: str, path: str, errors: list[str], *, single_line: bool = False) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}.{key} must be a non-empty string")
        return ""
    if single_line and ("\r" in value or "\n" in value):
        errors.append(f"{path}.{key} must be a single-line string")
        return ""
    return value.strip()


def _identifier(obj: dict[str, Any], key: str, path: str, errors: list[str]) -> str:
    raw = obj.get(key)
    if isinstance(raw, str) and raw and any(character.isspace() for character in raw):
        errors.append(f"{path}.{key} must be a non-whitespace token")
        return ""
    return _string(obj, key, path, errors, single_line=True)


def _strings(obj: dict[str, Any], key: str, path: str, errors: list[str]) -> list[str]:
    value = obj.get(key)
    if not isinstance(value, list):
        errors.append(f"{path}.{key} must be an array of strings")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{path}.{key}[{index}] must be a non-empty string")
        else:
            result.append(item.strip())
    return result


def _enum(value: Any, allowed: Collection[str], path: str, errors: list[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        errors.append(f"{path} must be one of: {', '.join(sorted(allowed))}")
        return ""
    return value


def _unsupported_fields(obj: dict[str, Any], allowed: set[str], path: str, errors: list[str]) -> None:
    for key in sorted(set(obj) - allowed):
        errors.append(f"{path}.{key} is not supported by this Diagnose version; regenerate from the diagnosis template")


def _reserved_free(value: str, path: str, errors: list[str]) -> None:
    if value and contains_reserved_delimiter(value):
        errors.append(f"{path} contains a reserved handoff delimiter")


def _sha256(value: Any, path: str, errors: list[str]) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        errors.append(f"{path} must be a lowercase SHA-256 digest")
        return ""
    return value


def _git_object(value: Any, path: str, errors: list[str]) -> str:
    if not isinstance(value, str) or GIT_OBJECT_RE.fullmatch(value) is None:
        errors.append(f"{path} must be a full lowercase Git object ID")
        return ""
    return value


def _canonical_relative(value: Any, path: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value:
        errors.append(f"{path} must be a canonical repository-relative POSIX path")
        return ""
    pure = PurePosixPath(value)
    if ("\\" in value or value.startswith("/") or value.endswith("/") or "//" in value or pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts) or any(ord(character) < 32 or ord(character) == 127 for character in value) or pure.as_posix() != value):
        errors.append(f"{path} must be a canonical repository-relative POSIX path")
        return ""
    return value


def _positive_line(value: Any, path: str, errors: list[str]) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        errors.append(f"{path} must be a positive integer")
        return 0
    return value


def _validate_span_fields(
    item: dict[str, Any], path: str, errors: list[str]
) -> tuple[str, int, int] | None:
    relative = _canonical_relative(item.get("path"), f"{path}.path", errors)
    start = _positive_line(item.get("start_line"), f"{path}.start_line", errors)
    end = _positive_line(item.get("end_line"), f"{path}.end_line", errors)
    if start and end and end < start:
        errors.append(f"{path}.end_line must be greater than or equal to start_line")
        end = 0
    if "sha256" in item:
        _sha256(item["sha256"], f"{path}.sha256", errors)
    if relative and start and end:
        return relative, start, end
    return None


def _validate_output(value: Any, path: str, errors: list[str]) -> None:
    output = _object(value, path, errors)
    if output is None:
        return
    _unsupported_fields(output, OUTPUT_FIELDS, path, errors)
    digest = _sha256(output.get("sha256"), f"{path}.sha256", errors)
    excerpt = output.get("excerpt")
    if not isinstance(excerpt, str):
        errors.append(f"{path}.excerpt must be a string")
        excerpt = ""
    elif len(excerpt.encode("utf-8")) > COMMAND_EXCERPT_LIMIT:
        errors.append(f"{path}.excerpt must be at most {COMMAND_EXCERPT_LIMIT} UTF-8 bytes")
    truncated = output.get("truncated")
    if not isinstance(truncated, bool):
        errors.append(f"{path}.truncated must be a boolean")
    elif not truncated and digest and isinstance(excerpt, str):
        actual = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
        if digest != actual:
            errors.append(f"{path}.sha256 does not match the exact untruncated excerpt")


def _validate_command(item: dict[str, Any], path: str, errors: list[str]) -> bool:
    status = _enum(item.get("status"), {"ran", "not-run"}, f"{path}.status", errors)
    allowed = COMMAND_RAN_FIELDS if status == "ran" else COMMAND_NOT_RUN_FIELDS
    _unsupported_fields(item, allowed, path, errors)
    argv = item.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(value, str) and value for value in argv):
        errors.append(f"{path}.argv must be a non-empty array of non-empty strings")
    cwd = item.get("cwd")
    if cwd != ".":
        _canonical_relative(cwd, f"{path}.cwd", errors)
    _reserved_free(_string(item, "observation", path, errors, single_line=True), f"{path}.observation", errors)
    if status == "ran":
        if not isinstance(item.get("exit_code"), int) or isinstance(item.get("exit_code"), bool):
            errors.append(f"{path}.exit_code must be an integer for a ran command")
        _validate_output(item.get("stdout"), f"{path}.stdout", errors)
        _validate_output(item.get("stderr"), f"{path}.stderr", errors)
        return True
    if status == "not-run":
        _reserved_free(_string(item, "reason", path, errors), f"{path}.reason", errors)
    return False


def _validate_capture(item: dict[str, Any], path: str, errors: list[str], *, has_evidence_root: bool) -> None:
    _unsupported_fields(item, CAPTURE_EVIDENCE_FIELDS, path, errors)
    _canonical_relative(item.get("path"), f"{path}.path", errors)
    _sha256(item.get("sha256"), f"{path}.sha256", errors)
    if ("start_line" in item) != ("end_line" in item):
        errors.append(f"{path} must declare both start_line and end_line or neither")
    elif "start_line" in item:
        start = _positive_line(item.get("start_line"), f"{path}.start_line", errors)
        end = _positive_line(item.get("end_line"), f"{path}.end_line", errors)
        if start and end and end < start:
            errors.append(f"{path}.end_line must be greater than or equal to start_line")
    _enum(item.get("provenance"), CAPTURE_PROVENANCES, f"{path}.provenance", errors)
    for field in ("origin", "observation"):
        _reserved_free(_string(item, field, path, errors, single_line=True), f"{path}.{field}", errors)
    if not has_evidence_root:
        errors.append(f"{path} requires diagnosis_context.evidence_root")


def _validate_evidence(
    evidence: list[dict[str, Any]],
    path: str,
    errors: list[str],
    *,
    material_key_owners: dict[tuple[str, int, int], int],
    has_evidence_root: bool,
) -> tuple[bool, bool]:
    """Validate one inline evidence list; return (has_verified, has_executed)."""
    has_verified = False
    has_executed = False
    for evidence_index, item in enumerate(evidence):
        evidence_path = f"{path}[{evidence_index}]"
        kind = _enum(item.get("kind"), EVIDENCE_KINDS, f"{evidence_path}.kind", errors)
        family = EVIDENCE_KIND_FAMILIES.get(kind)
        if family == "current-file":
            _unsupported_fields(item, FILE_EVIDENCE_FIELDS, evidence_path, errors)
            key = _validate_span_fields(item, evidence_path, errors)
            if key is not None and key in material_key_owners:
                errors.append(
                    f"{evidence_path} duplicates "
                    f"diagnosis_context.material_surfaces[{material_key_owners[key]}]"
                )
            _reserved_free(_string(item, "observation", evidence_path, errors, single_line=True), f"{evidence_path}.observation", errors)
            has_verified = True
        elif family == "history":
            _unsupported_fields(item, HISTORY_EVIDENCE_FIELDS, evidence_path, errors)
            _validate_span_fields(item, evidence_path, errors)
            _git_object(item.get("revision"), f"{evidence_path}.revision", errors)
            _reserved_free(_string(item, "observation", evidence_path, errors, single_line=True), f"{evidence_path}.observation", errors)
            has_verified = True
        elif family == "command":
            ran = _validate_command(item, evidence_path, errors)
            has_verified = has_verified or ran
            has_executed = has_executed or ran
        elif family == "capture":
            _validate_capture(item, evidence_path, errors, has_evidence_root=has_evidence_root)
            has_verified = True
            has_executed = True
        elif family == "external":
            _unsupported_fields(item, EXTERNAL_EVIDENCE_FIELDS, evidence_path, errors)
            for field in ("locator", "observation"):
                _reserved_free(_string(item, field, evidence_path, errors, single_line=True), f"{evidence_path}.{field}", errors)
    return has_verified, has_executed


def validate_diagnosis_bundle(raw: Any) -> list[str]:
    """Validate the authorable schema without reading the target project."""
    errors: list[str] = []
    bundle = _object(raw, "bundle", errors)
    if bundle is None:
        return errors
    if not compatible_version(bundle.get("schema_version"), CONTRACT_VERSION):
        errors.append(
            f"schema_version must share major version {CONTRACT_VERSION.split('.')[0]} with {CONTRACT_VERSION!r}; "
            "regenerate from the diagnosis template"
        )
    _unsupported_fields(bundle, TOP_LEVEL_FIELDS, "bundle", errors)

    context = _object(bundle.get("diagnosis_context"), "diagnosis_context", errors) or {}
    _unsupported_fields(context, CONTEXT_FIELDS, "diagnosis_context", errors)
    _reserved_free(_string(context, "target", "diagnosis_context", errors), "diagnosis_context.target", errors)
    snapshot = _object(context.get("snapshot"), "diagnosis_context.snapshot", errors) or {}
    snapshot_kind = _enum(snapshot.get("kind"), {"git", "filesystem"}, "diagnosis_context.snapshot.kind", errors)
    snapshot_fields = SNAPSHOT_GIT_FIELDS if snapshot_kind == "git" else SNAPSHOT_COMMON_FIELDS
    _unsupported_fields(snapshot, snapshot_fields, "diagnosis_context.snapshot", errors)
    _string(snapshot, "project_root", "diagnosis_context.snapshot", errors, single_line=True)
    if snapshot_kind == "git":
        _string(snapshot, "repository_id", "diagnosis_context.snapshot", errors, single_line=True)
        _git_object(snapshot.get("revision"), "diagnosis_context.snapshot.revision", errors)
    material_surfaces = _objects(context.get("material_surfaces"), "diagnosis_context.material_surfaces", errors)
    material_key_owners: dict[tuple[str, int, int], int] = {}
    for index, surface in enumerate(material_surfaces):
        path = f"diagnosis_context.material_surfaces[{index}]"
        _unsupported_fields(surface, SURFACE_FIELDS, path, errors)
        key = _validate_span_fields(surface, path, errors)
        if key is not None and key in material_key_owners:
            errors.append(f"{path} duplicates an earlier material surface")
        elif key is not None:
            material_key_owners[key] = index
    _strings(context, "limitations", "diagnosis_context", errors)
    evidence_root = context.get("evidence_root")
    has_evidence_root = (
        isinstance(evidence_root, str)
        and bool(evidence_root.strip())
        and "\n" not in evidence_root
        and "\r" not in evidence_root
        and Path(evidence_root).is_absolute()
    )
    if "evidence_root" not in context or (evidence_root is not None and not has_evidence_root):
        errors.append("diagnosis_context.evidence_root must be null or an absolute directory path")
    for index, entry in enumerate(_objects(context.get("ruled_out"), "diagnosis_context.ruled_out", errors)):
        path = f"diagnosis_context.ruled_out[{index}]"
        _unsupported_fields(entry, RULED_OUT_FIELDS, path, errors)
        _string(entry, "hypothesis", path, errors)
        evidence = _objects(entry.get("evidence"), f"{path}.evidence", errors, nonempty=True)
        verified, _executed = _validate_evidence(
            evidence,
            f"{path}.evidence",
            errors,
            material_key_owners=material_key_owners,
            has_evidence_root=has_evidence_root,
        )
        if evidence and not verified:
            errors.append(f"{path}.evidence {UNVERIFIED_EVIDENCE_MESSAGE}")
    for index, entry in enumerate(_objects(context.get("open_probes"), "diagnosis_context.open_probes", errors)):
        path = f"diagnosis_context.open_probes[{index}]"
        _unsupported_fields(entry, OPEN_PROBE_FIELDS, path, errors)
        for field in ("question", "probe", "expected_outcomes"):
            _string(entry, field, path, errors)

    finding_ids: set[str] = set()
    findings = _objects(bundle.get("findings"), "findings", errors)
    if not findings:
        limitations = context.get("limitations")
        if not isinstance(limitations, list) or not any(
            isinstance(item, str) and item.strip() for item in limitations
        ):
            errors.append(
                "a zero-finding diagnosis_context.limitations must bound what the current investigation established"
            )
    for finding_index, finding in enumerate(findings):
        path = f"findings[{finding_index}]"
        _unsupported_fields(finding, FINDING_FIELDS, path, errors)
        identifier = _identifier(finding, "id", path, errors)
        if identifier and identifier in finding_ids:
            errors.append(f"{path}.id duplicates {identifier!r}")
        finding_ids.add(identifier)
        for field in ("title", "summary", "cause_or_boundary", "impact"):
            _reserved_free(_string(finding, field, path, errors), f"{path}.{field}", errors)
        cause_status = _enum(finding.get("cause_status"), CAUSE_STATUSES, f"{path}.cause_status", errors)
        evidence = _objects(finding.get("evidence"), f"{path}.evidence", errors, nonempty=True)
        verified, executed = _validate_evidence(
            evidence,
            f"{path}.evidence",
            errors,
            material_key_owners=material_key_owners,
            has_evidence_root=has_evidence_root,
        )
        if evidence and not verified:
            errors.append(f"{path}.evidence {UNVERIFIED_EVIDENCE_MESSAGE}")
        if cause_status == "demonstrated" and evidence and not executed:
            errors.append(f"{path}.cause_status 'demonstrated' requires a ran command or capture evidence record")
    return errors


def _normalized_span(payload: bytes, start: int, end: int, label: str) -> tuple[bytes | None, str | None]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None, f"{label} is not valid UTF-8"
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized:
        lines: list[str] = []
    else:
        parts = normalized.split("\n")
        lines = [part + "\n" for part in parts[:-1]]
        if parts[-1]:
            lines.append(parts[-1])
    if start < 1 or end < start or end > len(lines):
        return None, f"{label} line range {start}-{end} is outside the declared content"
    return "".join(lines[start - 1 : end]).encode("utf-8"), None


class _RepositoryView:
    def __init__(self, repo_root: Path, *, reserved_workspace: bool = False):
        self.root = repo_root.resolve()
        self.reserved_workspace = reserved_workspace
        self.opened_paths: list[str] = []
        self.git_commands: list[tuple[str, ...]] = []
        self.is_git = False
        self.actual_snapshot: dict[str, str] = {}

    def _git(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        self.git_commands.append(tuple(args))
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, timeout=GIT_TIMEOUT_SECONDS, check=False)

    def _has_git_marker(self) -> bool:
        try:
            return os.path.lexists(self.root / ".git")
        except OSError:
            return True

    def inspect_identity(self) -> list[str]:
        if not self.root.is_dir():
            return [f"diagnosis_context.snapshot.project_root is not a directory: {self.root}"]
        try:
            inside = self._git("rev-parse", "--is-inside-work-tree")
        except FileNotFoundError:
            if self._has_git_marker():
                return ["diagnosis_context.snapshot cannot inspect Git identity because git is unavailable"]
            self.actual_snapshot = {"kind": "filesystem", "project_root": str(self.root)}
            return []
        except subprocess.TimeoutExpired:
            return ["diagnosis_context.snapshot Git identity inspection timed out"]
        if inside.returncode == 0 and inside.stdout.strip() == b"true":
            self.is_git = True
            values: list[str] = []
            for args in (("rev-parse", "--show-toplevel"), ("rev-parse", "--git-common-dir"), ("rev-parse", "HEAD")):
                result = self._git(*args)
                if result.returncode != 0:
                    return [f"diagnosis_context.snapshot could not inspect Git {' '.join(args)}"]
                values.append(result.stdout.decode("utf-8", errors="strict").strip())
            common = Path(values[1])
            if not common.is_absolute():
                common = self.root / common
            self.actual_snapshot = {"kind": "git", "project_root": str(Path(values[0]).resolve()), "repository_id": str(common.resolve()), "revision": values[2]}
        else:
            if self._has_git_marker():
                return ["diagnosis_context.snapshot has a Git marker but Git identity is unavailable"]
            self.actual_snapshot = {"kind": "filesystem", "project_root": str(self.root)}
        return []

    def compare_snapshot(self, declared: dict[str, Any]) -> list[str]:
        if self.is_git and declared.get("kind") != "git":
            return ["diagnosis_context.snapshot must use kind 'git' for a Git worktree"]
        if not self.is_git and declared.get("kind") != "filesystem":
            return ["diagnosis_context.snapshot must use kind 'filesystem' for a non-Git project"]
        errors: list[str] = []
        for field, actual in self.actual_snapshot.items():
            if declared.get(field) != actual:
                errors.append(f"diagnosis_context.snapshot.{field} does not match the inspected project (expected {actual!r})")
        return errors

    def workspace_error(self, raw: str, label: str, relative: PurePath | None = None) -> str | None:
        leading = tuple(part.casefold() for part in (relative or PurePosixPath(raw)).parts[:2])
        if self.reserved_workspace and leading == WORKSPACE_PARTS:
            return f"{label}.path is inside the Diagnose workspace ({WORKSPACE_DIR}/) and is never evidence: {raw}"
        return None

    def resolve_current(self, raw: str, label: str, *, directory: bool = False) -> tuple[Path | None, str | None]:
        reserved = self.workspace_error(raw, label)
        if reserved:
            return None, reserved
        try:
            current = self.root
            for part in PurePosixPath(raw).parts:
                current = current / part
                if current.is_symlink():
                    return None, f"{label}.path traverses a symlink: {raw}"
            resolved = current.resolve()
        except (OSError, ValueError) as exc:
            return None, f"{label}.path is unsafe or inaccessible: {raw} ({exc})"
        try:
            relative = resolved.relative_to(self.root)
        except ValueError:
            return None, f"{label}.path escapes the project root: {raw}"
        reserved = self.workspace_error(raw, label, relative)
        if reserved:
            return None, reserved
        try:
            if directory:
                if not resolved.is_dir():
                    return None, f"{label} is not an existing directory: {raw}"
            elif not resolved.is_file():
                return None, f"{label}.path is not an existing regular file: {raw}"
        except (OSError, ValueError) as exc:
            return None, f"{label}.path is unsafe or inaccessible: {raw} ({exc})"
        return resolved, None

    def read_current(self, raw: str, label: str) -> tuple[bytes | None, str | None]:
        path, error = self.resolve_current(raw, label)
        if error:
            return None, error
        assert path is not None
        if raw not in self.opened_paths:
            self.opened_paths.append(raw)
        try:
            return path.read_bytes(), None
        except OSError as exc:
            return None, f"{label}.path could not be read: {exc}"

    def read_history(self, revision: str, raw: str, label: str) -> tuple[bytes | None, str | None]:
        if not self.is_git:
            return None, f"{label} requires a Git snapshot"
        reserved = self.workspace_error(raw, label)
        if reserved:
            return None, reserved
        resolved = self._git("rev-parse", "--verify", f"{revision}^{{commit}}")
        if resolved.returncode != 0 or resolved.stdout.decode("ascii", errors="ignore").strip() != revision:
            return None, f"{label}.revision is not the declared immutable commit object"
        parts = PurePosixPath(raw).parts
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            args = ("ls-tree", "-d", revision, "--", prefix) if index < len(parts) else ("ls-tree", revision, "--", prefix)
            entry = self._git(*args)
            line = entry.stdout.decode("utf-8", errors="replace").strip()
            if not line:
                return None, f"{label}.path is missing from Git history: {raw}"
            metadata = line.split("\t", 1)[0].split()
            if len(metadata) < 2:
                return None, f"{label}.path has malformed Git tree metadata: {raw}"
            mode, object_type = metadata[:2]
            if mode == "120000":
                return None, f"{label}.path traverses a Git symlink: {raw}"
            if mode == "160000":
                return None, f"{label}.path crosses a Git submodule boundary: {raw}"
            if index == len(parts) and object_type != "blob":
                return None, f"{label}.path is not a regular Git blob: {raw}"
        blob = self._git("show", f"{revision}:{raw}")
        if blob.returncode != 0:
            return None, f"{label}.path could not be read from Git history: {raw}"
        return blob.stdout, None


def _bind_span(item: dict[str, Any], label: str, view: _RepositoryView, *, history: bool = False) -> tuple[str | None, str | None]:
    raw_path = str(item["path"])
    payload, error = view.read_history(str(item["revision"]), raw_path, label) if history else view.read_current(raw_path, label)
    if error:
        return None, error
    assert payload is not None
    span, error = _normalized_span(payload, int(item["start_line"]), int(item["end_line"]), label)
    if error:
        return None, error
    assert span is not None
    actual = hashlib.sha256(span).hexdigest()
    if "sha256" not in item:
        item["sha256"] = actual
    elif actual != item["sha256"]:
        return None, f"{label}.sha256 does not match the normalized declared span"
    return actual, None


def _bind_capture(item: dict[str, Any], label: str, view: _RepositoryView) -> tuple[str | None, str | None]:
    payload, error = view.read_current(str(item["path"]), label)
    if error:
        return None, error
    assert payload is not None
    if "start_line" in item:
        span, error = _normalized_span(payload, int(item["start_line"]), int(item["end_line"]), label)
        if error:
            return None, error
        assert span is not None
        payload = span
    actual = hashlib.sha256(payload).hexdigest()
    if actual != item["sha256"]:
        return None, f"{label}.sha256 does not match the declared capture bytes"
    return actual, None


def _bind_evidence(
    evidence: list[dict[str, Any]],
    prefix: str,
    view: _RepositoryView,
    capture_view: _RepositoryView | None,
    bindings: list[tuple[str, str]],
    errors: list[str],
) -> None:
    for evidence_index, item in enumerate(evidence):
        family = EVIDENCE_KIND_FAMILIES[item["kind"]]
        label = f"{prefix}[{evidence_index}]"
        digest: str | None = None
        error: str | None = None
        if family == "current-file":
            digest, error = _bind_span(item, label, view)
        elif family == "history":
            digest, error = _bind_span(item, label, view, history=True)
        elif family == "command":
            cwd = item["cwd"]
            path, error = (view.root, None) if cwd == "." else view.resolve_current(cwd, f"{label}.cwd", directory=True)
            if path is not None:
                digest = hashlib.sha256(json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        elif family == "capture":
            if capture_view is None:
                error = f"{label} requires diagnosis_context.evidence_root"
            else:
                digest, error = _bind_capture(item, label, capture_view)
        if error:
            errors.append(error)
        elif digest:
            bindings.append((label, digest))


def validate_diagnosis_bindings(raw: Any, repo_root: Path) -> tuple[list[str], BindingProof | None]:
    """Verify authored identity and only the explicitly declared evidence boundary.

    Omitted span digests are computed and written into the bundle in place, so rendering records them.
    """
    errors = validate_diagnosis_bundle(raw)
    if errors or not isinstance(raw, dict):
        return errors, None
    context = raw["diagnosis_context"]
    view = _RepositoryView(Path(repo_root), reserved_workspace=True)
    errors.extend(view.inspect_identity())
    if not errors:
        errors.extend(view.compare_snapshot(context["snapshot"]))
    if errors:
        return errors, None
    capture_view: _RepositoryView | None = None
    if context["evidence_root"] is not None:
        capture_view = _RepositoryView(Path(context["evidence_root"]))
        if not capture_view.root.is_dir():
            return [f"diagnosis_context.evidence_root is not an existing directory: {context['evidence_root']}"], None
    bindings: list[tuple[str, str]] = []
    for index, surface in enumerate(context["material_surfaces"]):
        label = f"diagnosis_context.material_surfaces[{index}]"
        material_digest, material_error = _bind_span(surface, label, view)
        if material_error:
            errors.append(material_error)
        elif material_digest:
            bindings.append((label, material_digest))
    for index, entry in enumerate(context["ruled_out"]):
        _bind_evidence(entry["evidence"], f"diagnosis_context.ruled_out[{index}].evidence", view, capture_view, bindings, errors)
    for finding_index, finding in enumerate(raw["findings"]):
        _bind_evidence(finding["evidence"], f"findings[{finding_index}].evidence", view, capture_view, bindings, errors)
    if errors:
        return errors, None
    return [], BindingProof(snapshot=dict(view.actual_snapshot), bindings=tuple(bindings), opened_paths=tuple(view.opened_paths), git_commands=tuple(view.git_commands))


def revalidate_diagnosis_bindings(raw: Any, repo_root: Path, proof: BindingProof) -> list[str]:
    """Recheck the captured facts immediately before publication."""
    errors, current = validate_diagnosis_bindings(raw, repo_root)
    if errors:
        return errors
    if current is None or current.snapshot != proof.snapshot or current.bindings != proof.bindings:
        return ["declared snapshot or evidence changed after initial validation"]
    return []

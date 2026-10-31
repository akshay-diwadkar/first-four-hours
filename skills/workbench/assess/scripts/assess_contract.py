"""Provider-free Assess result, revision, source-snapshot, and publication contract."""

from __future__ import annotations

import bisect
import dataclasses
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from _diagnostic_contract import normalize_diagnostic
from _skill_protocol_runtime import compatible_version, compatible_version_pattern

CONTRACT_VERSION = "1.0.1"
RESULT_FILENAME = "assessment.md"
ASSESSMENT_ARTIFACT_ROOT = ".first-four-hours"
ASSESSMENT_WORKSPACE_PARTS = (ASSESSMENT_ARTIFACT_ROOT, "assessments")
ASSESSMENT_WORKSPACE_DIR = "/".join(ASSESSMENT_WORKSPACE_PARTS)
ASSESSMENT_WORKSPACE_RULE = f"/{ASSESSMENT_WORKSPACE_DIR}/"
RESULTS = {"clear", "findings", "blocked"}
TOP_LEVEL_FIELDS = {
    "schema_version",
    "target",
    "base_ref",
    "head_ref",
    "assessed_sources",
    "result",
    "examined",
    "findings",
    "limitations",
}
SOURCE_FIELDS = {"id", "role", "locator", "path"}
SOURCE_ROLES = {"target", "authority", "evidence", "proof", "diagnosis"}
SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
FINDING_FIELDS = {
    "severity",
    "basis",
    "defect",
    "locators",
    "consequence",
    "required_truth",
}
FILE_LOCATOR_FIELDS = {"kind", "path", "start_line", "end_line"}
SOURCE_LOCATOR_FIELDS = {"kind", "source_id"}
FILE_LOCATOR_KINDS = {"base-file", "head-file"}
PATH_LOCATOR_FIELDS = {"kind", "path"}
PATH_LOCATOR_KINDS = {"base-path", "head-path"}
BASES = {"observed", "reasoned"}
FINDING_SEVERITIES = ("P0", "P1", "P2", "P3")
NO_LIMITATIONS = "Assessor declared no material limitations."
LEADING_HEADINGS = ["# Assessment", "## Result", "## Findings"]
TRAILING_HEADINGS = [
    "## Limitations",
    "## Changed paths not examined",
    "## Target",
    "## Assessed snapshots",
    "## Examined",
]
SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RECEIPT_RE = re.compile(rf"^<!-- assessment-result: {compatible_version_pattern(CONTRACT_VERSION)}; sha256: ([0-9a-f]{{64}}) -->$")
RETIRED_RECEIPT_RE = re.compile(r"^<!-- assessment-result: ([^;\s]+); ")
HEADING_RE = re.compile(r"^#{1,6} .+$", re.MULTILINE)
PATH_CHAR_RE = re.compile(r"[\w./\\-]")
PATH_CONTINUATION_RE = re.compile(r"[\w/\\-]|\.[\w/\\-]")
GIT_TIMEOUT_SECONDS = 10
SKILL_ROOT = Path(__file__).resolve().parent.parent


class AssessError(ValueError):
    """One repair-ready deterministic Assess contract failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        category: str = "malformed_input",
        path: str | Path = RESULT_FILENAME,
        evidence: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.category = category
        self.path = str(path)
        self.evidence = evidence or (message,)

    def diagnostic(self, *, phase: str) -> dict[str, Any]:
        if self.category == "stale_evidence":
            action = "Perform a fresh full assessment against the current exact base/head and assessed snapshots, then seal a new assessment.md."
        elif self.category == "unsafe_state":
            action = "Use the prepared ignored .first-four-hours/assessments/<slug>/assessment.md output path, keep source snapshots external, repair the named unsafe workspace/output condition, and retry without changing the assessed head."
        elif self.category in {"missing_evidence", "unavailable_prerequisite"}:
            action = "Provide the named local Git ref, snapshot, path, or proof and retry the same Assess command."
        else:
            action = "Correct the named Assess bundle or artifact field and retry the same command."
        return normalize_diagnostic(
            {
                "code": self.code,
                "category": self.category,
                "severity": "error",
                "message": self.message,
                "path": self.path,
                "required_action": action,
                "valid_repairs": [action],
                "supporting_evidence": list(self.evidence),
            },
            skill="assess",
            phase=phase,
            artifact=RESULT_FILENAME,
            path=self.path,
        )


@dataclasses.dataclass(frozen=True)
class GitBinding:
    repository_root: str
    repository_id: str
    base_ref: str
    base_revision: str
    head_ref: str
    head_revision: str


@dataclasses.dataclass(frozen=True)
class SourceBinding:
    id: str
    role: str
    locator: str
    path: str
    sha256: str

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "role": self.role,
            "locator": self.locator,
            "path": self.path,
            "sha256": self.sha256,
        }


@dataclasses.dataclass(frozen=True)
class AssessmentWorkspace:
    slug: str
    output_path: Path
    relative_output_path: str
    git_exclude: Path | None
    git_ignored: bool


def _fail(code: str, message: str, **kwargs: Any) -> AssessError:
    return AssessError(code, message, **kwargs)


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise _fail(
            "git.unavailable",
            "Git is required to bind an exact Assess base/head",
            category="unavailable_prerequisite",
            path=repo,
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise _fail(
            "git.timeout",
            "Git identity inspection timed out",
            category="unavailable_prerequisite",
            path=repo,
        ) from exc


def _git_text(repo: Path, *args: str, code: str, message: str) -> str:
    result = _git(repo, *args)
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise _fail(
            code,
            message,
            category="missing_evidence",
            path=repo,
            evidence=tuple(item for item in (message, detail) if item),
        )
    try:
        return result.stdout.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise _fail(code, f"{message}: Git returned non-UTF-8 identity data", path=repo) from exc


def _workspace_fail(code: str, message: str, *, path: str | Path) -> AssessError:
    return _fail(code, message, category="unsafe_state", path=path)


def _normalize_assessment_slug(name: str) -> str:
    if not isinstance(name, str):
        raise _workspace_fail("workspace.slug.type", "assessment slug must be a string", path=ASSESSMENT_WORKSPACE_DIR)
    normalized = name.strip().casefold()
    slug = re.sub(r"-+", "-", "".join(character if character.isalnum() else "-" for character in normalized)).strip("-")
    if not slug:
        raise _workspace_fail(
            "workspace.slug.empty",
            "assessment slug must contain at least one letter or digit",
            path=ASSESSMENT_WORKSPACE_DIR,
        )
    return slug


def _prepare_git_context(repo_root: Path) -> tuple[Path, Path]:
    try:
        supplied = repo_root.resolve(strict=True)
    except OSError as exc:
        raise _fail(
            "target.repository_missing",
            f"assessed repository is unavailable: {repo_root}",
            category="unavailable_prerequisite",
            path=repo_root,
        ) from exc
    if not supplied.is_dir():
        raise _workspace_fail(
            "target.repository_invalid", f"assessed repository is not a directory: {supplied}", path=supplied
        )
    top_result = _git(supplied, "rev-parse", "--show-toplevel")
    top_raw = top_result.stdout.decode("utf-8", errors="replace").strip()
    if top_result.returncode != 0 or not top_raw:
        raise _workspace_fail(
            "target.not_git",
            "Assess prepare requires a Git repository worktree root",
            path=supplied,
        )
    top = Path(top_raw).resolve()
    if supplied != top:
        raise _fail(
            "target.root_mismatch",
            f"repo-root must be the Git worktree root (expected {top})",
            category="contract_contradiction",
            path=supplied,
        )
    result = _git(top, "rev-parse", "--git-path", "info/exclude")
    git_path = result.stdout.decode("utf-8", errors="replace").strip()
    if result.returncode != 0 or not git_path:
        raise _workspace_fail(
            "workspace.git.exclude_unresolved",
            "Git repository has no resolvable worktree-local info/exclude path",
            path=top,
        )
    exclude = Path(git_path)
    if not exclude.is_absolute():
        exclude = top / exclude
    exclude = exclude.resolve(strict=False)
    if exclude.exists() and (exclude.is_dir() or exclude.is_symlink()):
        raise _workspace_fail(
            "workspace.git.exclude_unsafe",
            f"Git exclude path is not a regular file: {exclude}",
            path=exclude,
        )
    return top, exclude


def _ensure_assessments_git_exclude(root: Path, relative_path: str, exclude: Path) -> tuple[Path, bool]:
    ignored = _git(root, "check-ignore", "--no-index", "--quiet", "--", relative_path)
    if ignored.returncode == 0:
        return exclude, True
    if ignored.returncode != 1:
        raise _workspace_fail(
            "workspace.git.ignore_check",
            "cannot query the repository ignore boundary",
            path=root,
        )
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    lines = {line.strip() for line in existing.replace("\r\n", "\n").splitlines()}
    if ASSESSMENT_WORKSPACE_RULE not in lines and f"{ASSESSMENT_WORKSPACE_DIR}/" not in lines:
        separator = "" if not existing or existing.endswith(("\n", "\r")) else "\n"
        _atomic_write_text(exclude, existing + separator + ASSESSMENT_WORKSPACE_RULE + "\n")
    final = _git(root, "check-ignore", "--no-index", "--quiet", "--", relative_path)
    if final.returncode != 0:
        raise _workspace_fail(
            "workspace.git.ignore_boundary",
            "the local Git exclude does not cover the Assess workspace output",
            path=exclude,
        )
    return exclude, True


def _refuse_tracked_namespace(root: Path) -> None:
    head = _git(root, "rev-parse", "--verify", "--quiet", "HEAD")
    # Exit 1 also covers a branch ref holding garbage; only a resolvable symbolic HEAD is truly unborn.
    unborn = head.returncode == 1 and _git(root, "symbolic-ref", "--quiet", "HEAD").returncode == 0
    if head.returncode != 0 and not unborn:
        raise _workspace_fail(
            "workspace.git.tracked_check",
            f"cannot establish whether the {ASSESSMENT_WORKSPACE_DIR}/ namespace is tracked; repair Git metadata and retry",
            path=root,
        )
    tree_args = ["--with-tree=HEAD"] if head.returncode == 0 else []
    listed = _git(root, "ls-files", *tree_args, "--", f":(icase){ASSESSMENT_WORKSPACE_DIR}")
    if listed.returncode != 0:
        raise _workspace_fail(
            "workspace.git.tracked_check",
            f"cannot establish whether the {ASSESSMENT_WORKSPACE_DIR}/ namespace is tracked; repair Git metadata and retry",
            path=root,
        )
    if listed.stdout.strip():
        raise _workspace_fail(
            "workspace.namespace_tracked",
            f"the {ASSESSMENT_WORKSPACE_DIR}/ namespace already contains tracked project files; resolve that project conflict before preparing or sealing",
            path=root / ASSESSMENT_WORKSPACE_DIR,
        )


def _is_linked(path: Path) -> bool:
    """Return whether path is a link, including a dangling one or a Windows junction pathlib does not report."""
    if path.is_symlink() or os.path.lexists(path) and not path.exists():
        return True
    return path.exists() and os.path.normcase(str(path.resolve())) != os.path.normcase(str(path.absolute()))


def prepare_assessment_workspace(repo_root: Path, slug: str) -> AssessmentWorkspace:
    root, exclude = _prepare_git_context(repo_root)
    _refuse_tracked_namespace(root)
    normalized = _normalize_assessment_slug(slug)
    artifact_root = root / ASSESSMENT_ARTIFACT_ROOT
    workspace = root / ASSESSMENT_WORKSPACE_DIR
    task_dir = workspace / normalized
    # Refuse every linked or non-directory entry before any exclude write or directory creation.
    for path, code, label in (
        (artifact_root, "workspace.namespace_unsafe", "Assess artifact root"),
        (workspace, "workspace.namespace_unsafe", "Assess workspace namespace"),
        (task_dir, "workspace.task_unsafe", "Assess workspace task path"),
    ):
        if _is_linked(path) or path.exists() and not path.is_dir():
            raise _workspace_fail(code, f"{label} is not a real directory: {path}", path=path)
    relative_output = PurePosixPath(ASSESSMENT_WORKSPACE_DIR, normalized, RESULT_FILENAME).as_posix()
    git_exclude, git_ignored = _ensure_assessments_git_exclude(root, relative_output, exclude)
    task_dir.mkdir(parents=True, exist_ok=True)
    return AssessmentWorkspace(
        slug=normalized,
        output_path=task_dir / RESULT_FILENAME,
        relative_output_path=relative_output,
        git_exclude=git_exclude,
        git_ignored=git_ignored,
    )


def _resolve_ref(repo: Path, ref: str, role: str) -> str:
    revision = _git_text(
        repo,
        "rev-parse",
        "--verify",
        "--end-of-options",
        f"{ref}^{{commit}}",
        code=f"target.{role}_unavailable",
        message=f"{role.replace('_', ' ')} does not resolve to an exact commit: {ref}",
    )
    if not SHA_RE.fullmatch(revision):
        raise _fail(f"target.{role}_invalid", f"{role.replace('_', ' ')} did not resolve to a full commit ID: {ref}")
    return revision


def inspect_binding(repo_root: Path, base_ref: str, head_ref: str) -> GitBinding:
    try:
        supplied = repo_root.resolve(strict=True)
    except OSError as exc:
        raise _fail(
            "target.repository_missing",
            f"assessed repository is unavailable: {repo_root}",
            category="unavailable_prerequisite",
            path=repo_root,
        ) from exc
    if not supplied.is_dir():
        raise _fail("target.repository_invalid", f"assessed repository is not a directory: {supplied}", path=supplied)
    top = Path(
        _git_text(
            supplied,
            "rev-parse",
            "--show-toplevel",
            code="target.not_git",
            message="Assess requires a Git repository with exact base/head commits",
        )
    ).resolve()
    if supplied != top:
        raise _fail(
            "target.root_mismatch",
            f"repo-root must be the Git worktree root (expected {top})",
            category="contract_contradiction",
            path=supplied,
        )
    common_raw = _git_text(
        top,
        "rev-parse",
        "--git-common-dir",
        code="target.identity_unavailable",
        message="cannot resolve the assessed repository identity",
    )
    common = Path(common_raw)
    if not common.is_absolute():
        common = top / common
    return GitBinding(
        repository_root=str(top),
        repository_id=str(common.resolve()),
        base_ref=base_ref,
        base_revision=_resolve_ref(top, base_ref, "base_ref"),
        head_ref=head_ref,
        head_revision=_resolve_ref(top, head_ref, "head_ref"),
    )


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _fail("bundle.shape", f"{label} must be an object")
    return value


def _fields(value: dict[str, Any], expected: set[str], label: str) -> None:
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing:
        raise _fail("bundle.field_missing", f"{label} is missing fields: {', '.join(missing)}")
    if extra:
        raise _fail("bundle.field_unsupported", f"{label} contains unsupported fields: {', '.join(extra)}")


def _string(value: Any, label: str, *, single_line: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail("bundle.string_invalid", f"{label} must be a non-empty string")
    if "\x00" in value or (single_line and ("\n" in value or "\r" in value)):
        raise _fail("bundle.string_invalid", f"{label} must be a safe{' single-line' if single_line else ''} string")
    return value.strip()


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise _fail("bundle.array_invalid", f"{label} must be an array of strings")
    return [_string(item, f"{label}[{index}]") for index, item in enumerate(value)]


def _repository_path(value: Any, label: str) -> str:
    raw = _string(value, label, single_line=True)
    if "\\" in raw:
        raise _fail("locator.path_unsafe", f"{label} must use repository-relative forward slashes")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise _fail("locator.path_unsafe", f"{label} must be a safe repository-relative path: {raw}")
    return pure.as_posix()


def _source_id(value: Any, label: str) -> str:
    raw = _string(value, label, single_line=True)
    if not SOURCE_ID_RE.fullmatch(raw):
        raise _fail("source.id_invalid", f"{label} must be 1-80 letters, digits, dot, underscore, or hyphen")
    return raw


def _assessed_sources(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise _fail("source.invalid", "assessed_sources must be an array")
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw_source in enumerate(value):
        label = f"assessed_sources[{index}]"
        source = _object(raw_source, label)
        _fields(source, SOURCE_FIELDS, label)
        source_id = _source_id(source["id"], f"{label}.id")
        if source_id in seen:
            raise _fail("source.id_duplicate", f"{label}.id duplicates an earlier assessed source: {source_id}")
        seen.add(source_id)
        role = _string(source["role"], f"{label}.role", single_line=True)
        if role not in SOURCE_ROLES:
            raise _fail(
                "source.role_unsupported", f"{label}.role must be target, authority, evidence, proof, or diagnosis"
            )
        sources.append(
            {
                "id": source_id,
                "role": role,
                "locator": _string(source["locator"], f"{label}.locator", single_line=True),
                "path": _string(source["path"], f"{label}.path", single_line=True),
            }
        )
    return sources


def _locators(value: list[Any], label: str, source_ids: set[str]) -> list[dict[str, Any]]:
    locators: list[dict[str, Any]] = []
    for locator_index, raw_locator in enumerate(value):
        locator_label = f"{label}[{locator_index}]"
        locator = _object(raw_locator, locator_label)
        kind = locator.get("kind")
        if kind in FILE_LOCATOR_KINDS:
            _fields(locator, FILE_LOCATOR_FIELDS, locator_label)
            start = locator["start_line"]
            end = locator["end_line"]
            if (
                not isinstance(start, int)
                or isinstance(start, bool)
                or not isinstance(end, int)
                or isinstance(end, bool)
                or start < 1
                or end < start
            ):
                raise _fail("locator.range_invalid", f"{locator_label} has an invalid positive line range")
            locators.append(
                {
                    "kind": kind,
                    "path": _repository_path(locator["path"], f"{locator_label}.path"),
                    "start_line": start,
                    "end_line": end,
                }
            )
        elif kind in PATH_LOCATOR_KINDS:
            _fields(locator, PATH_LOCATOR_FIELDS, locator_label)
            locators.append({"kind": kind, "path": _repository_path(locator["path"], f"{locator_label}.path")})
        elif kind == "source":
            _fields(locator, SOURCE_LOCATOR_FIELDS, locator_label)
            source_id = _source_id(locator["source_id"], f"{locator_label}.source_id")
            if source_id not in source_ids:
                raise _fail(
                    "locator.source_unknown",
                    f"{locator_label}.source_id references unknown assessed source: {source_id}",
                )
            locators.append({"kind": kind, "source_id": source_id})
        else:
            raise _fail(
                "locator.kind_unsupported",
                f"{locator_label}.kind must be base-file, head-file, base-path, head-path, or source",
            )
    return locators


def validate_bundle(raw: Any) -> dict[str, Any]:
    bundle = _object(raw, "bundle")
    if not compatible_version(bundle.get("schema_version"), CONTRACT_VERSION):
        raise _fail(
            "bundle.version_unsupported",
            f"schema_version must share major version {CONTRACT_VERSION.split('.')[0]} with {CONTRACT_VERSION!r}; "
            "a bundle authored under another schema requires a fresh full assessment",
            category="stale_evidence",
        )
    _fields(bundle, TOP_LEVEL_FIELDS, "bundle")
    target = _string(bundle["target"], "target")
    base_ref = _string(bundle["base_ref"], "base_ref", single_line=True)
    head_ref = _string(bundle["head_ref"], "head_ref", single_line=True)
    assessed_sources = _assessed_sources(bundle["assessed_sources"])
    source_ids = {source["id"] for source in assessed_sources}
    source_roles = {source["id"]: source["role"] for source in assessed_sources}
    result = bundle["result"]
    if not isinstance(result, str) or result not in RESULTS:
        raise _fail("result.unsupported", "result must be exactly clear, findings, or blocked")
    limitations = _string_list(bundle["limitations"], "limitations")
    if not isinstance(bundle["examined"], list):
        raise _fail("bundle.array_invalid", "examined must be an array of locators")
    examined = _locators(bundle["examined"], "examined", source_ids)
    if not isinstance(bundle["findings"], list):
        raise _fail("bundle.array_invalid", "findings must be an array")
    findings: list[dict[str, Any]] = []
    for finding_index, raw_finding in enumerate(bundle["findings"]):
        label = f"findings[{finding_index}]"
        finding = _object(raw_finding, label)
        severity = finding.get("severity")
        if not isinstance(severity, str) or severity not in FINDING_SEVERITIES:
            raise _fail(
                "finding.severity_invalid",
                f"{label}.severity must be exactly one of {', '.join(FINDING_SEVERITIES)}, "
                "most to least severe as defined under Severity in the assess guidance",
            )
        _fields(finding, FINDING_FIELDS, label)
        raw_locators = finding["locators"]
        if not isinstance(raw_locators, list) or not raw_locators:
            raise _fail("finding.locators_missing", f"{label}.locators must be a non-empty array")
        locators = _locators(raw_locators, f"{label}.locators", source_ids)
        basis = finding["basis"]
        if not isinstance(basis, str) or basis not in BASES:
            raise _fail("finding.basis_invalid", f"{label}.basis must be exactly observed or reasoned")
        if basis == "observed" and not any(
            locator["kind"] == "source" and source_roles[locator["source_id"]] == "proof" for locator in locators
        ):
            raise _fail(
                "finding.basis_unproven",
                f"{label}.basis observed requires a source locator whose assessed source role is proof",
            )
        findings.append(
            {
                "severity": severity,
                "basis": basis,
                "defect": _string(finding["defect"], f"{label}.defect"),
                "locators": locators,
                "consequence": _string(finding["consequence"], f"{label}.consequence"),
                "required_truth": _string(finding["required_truth"], f"{label}.required_truth"),
            }
        )
    if result == "clear" and findings:
        raise _fail("result.contradiction", "clear cannot contain accepted findings", category="contract_contradiction")
    if result == "clear" and not examined:
        raise _fail(
            "result.coverage_missing",
            "clear requires at least one examined locator naming what the assessment inspected",
            category="contract_contradiction",
        )
    if result == "findings" and not findings:
        raise _fail(
            "result.contradiction", "findings requires at least one accepted finding", category="contract_contradiction"
        )
    if result == "blocked" and not limitations:
        raise _fail(
            "result.contradiction",
            "blocked requires at least one material limitation",
            category="contract_contradiction",
        )
    return {
        "schema_version": CONTRACT_VERSION,
        "target": target,
        "base_ref": base_ref,
        "head_ref": head_ref,
        "assessed_sources": assessed_sources,
        "result": result,
        "examined": examined,
        "findings": findings,
        "limitations": limitations,
    }


def read_bundle(path: Path, repo_root: Path) -> dict[str, Any]:
    if not path.is_file():
        raise _fail(
            "bundle.missing",
            f"bundle must be an existing regular JSON file: {path}",
            category="missing_evidence",
            path=path,
        )
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise _fail(
            "bundle.missing", f"bundle cannot be resolved: {path}", category="missing_evidence", path=path
        ) from exc
    if _within(resolved, SKILL_ROOT) or _within(resolved, repo_root.resolve()):
        raise _fail(
            "bundle.location_unsafe",
            "temporary Assess bundle must be outside the installed skill and assessed repository",
            category="unsafe_state",
            path=resolved,
        )
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail("bundle.invalid", f"cannot read Assess bundle: {exc}", path=resolved) from exc
    return validate_bundle(raw)


def _canonical_source_path(raw: str, repo_root: Path, output: Path | None) -> Path:
    path = Path(raw)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise _fail(
            "source.missing", f"assessed source snapshot is missing: {raw}", category="missing_evidence", path=raw
        ) from exc
    if not resolved.is_file():
        raise _fail(
            "source.type_invalid",
            f"assessed source snapshot is not a regular file: {resolved}",
            category="missing_evidence",
            path=resolved,
        )
    if os.path.lexists(resolved) and resolved.is_symlink():
        raise _fail(
            "source.symlink_unsafe",
            "assessed source snapshot cannot be a symlink",
            category="unsafe_state",
            path=resolved,
        )
    if _within(resolved, SKILL_ROOT):
        raise _fail(
            "source.in_skill",
            "assessed source snapshot cannot be inside the installed skill",
            category="unsafe_state",
            path=resolved,
        )
    if _within(resolved, repo_root.resolve()):
        raise _fail(
            "source.in_repo",
            "assessed source snapshot must be outside the assessed repository",
            category="unsafe_state",
            path=resolved,
        )
    if output is not None:
        try:
            if resolved == output.resolve():
                raise _fail(
                    "source.output_alias",
                    "assessed source snapshot cannot be the assessment.md output",
                    category="unsafe_state",
                    path=resolved,
                )
        except OSError:
            pass
    return resolved


def bind_sources(bundle: dict[str, Any], repo_root: Path, output: Path | None = None) -> tuple[SourceBinding, ...]:
    bindings: list[SourceBinding] = []
    for source in bundle["assessed_sources"]:
        path = _canonical_source_path(source["path"], repo_root, output)
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise _fail(
                "source.missing",
                f"assessed source snapshot cannot be read: {path}",
                category="missing_evidence",
                path=path,
            ) from exc
        bindings.append(
            SourceBinding(
                id=source["id"],
                role=source["role"],
                locator=source["locator"],
                path=str(path),
                sha256=hashlib.sha256(payload).hexdigest(),
            )
        )
    return tuple(bindings)


def _source_map(sources: tuple[SourceBinding, ...]) -> dict[str, SourceBinding]:
    return {source.id: source for source in sources}


def _git_blob(repo: Path, revision: str, path: str, label: str) -> bytes:
    parts = PurePosixPath(path).parts
    for index in range(1, len(parts) + 1):
        prefix = "/".join(parts[:index])
        entry = _git(repo, "ls-tree", revision, "--", f":(literal){prefix}")
        line = entry.stdout.decode("utf-8", errors="replace").strip()
        if entry.returncode or not line:
            raise _fail(
                "locator.path_missing",
                f"{label} is missing from {revision}: {path}",
                category="missing_evidence",
                path=path,
            )
        metadata = line.split("\t", 1)[0].split()
        if len(metadata) < 2:
            raise _fail("locator.path_invalid", f"{label} has malformed Git tree metadata: {path}", path=path)
        mode, object_type = metadata[:2]
        if mode == "120000":
            raise _fail(
                "locator.path_unsafe", f"{label} traverses a Git symlink: {path}", category="unsafe_state", path=path
            )
        if mode == "160000":
            raise _fail(
                "locator.path_unsafe", f"{label} crosses a Git submodule: {path}", category="unsafe_state", path=path
            )
        if index == len(parts) and object_type != "blob":
            raise _fail("locator.path_invalid", f"{label} is not a regular Git blob: {path}", path=path)
    blob = _git(repo, "cat-file", "blob", f"{revision}:{path}")
    if blob.returncode:
        raise _fail(
            "locator.path_missing",
            f"{label} cannot read {path} from {revision}",
            category="missing_evidence",
            path=path,
        )
    return blob.stdout


def _bind_locator(
    locator: dict[str, Any], label: str, binding: GitBinding, source_by_id: dict[str, SourceBinding]
) -> dict[str, str]:
    kind = locator["kind"]
    if kind == "source":
        source = source_by_id[locator["source_id"]]
        return {
            "kind": kind,
            "source_id": source.id,
            "role": source.role,
            "locator": source.locator,
            "sha256": source.sha256,
        }
    repo = Path(binding.repository_root)
    if kind in PATH_LOCATOR_KINDS:
        revision = binding.base_revision if kind == "base-path" else binding.head_revision
        entry = _git(repo, "ls-tree", revision, "--", f":(literal){locator['path']}")
        if entry.returncode or not entry.stdout.strip():
            raise _fail(
                "locator.path_missing",
                f"{label} is missing from {revision}: {locator['path']}",
                category="missing_evidence",
                path=locator["path"],
            )
        return {"kind": kind, "locator": f"{revision}:{locator['path']}"}
    revision = binding.base_revision if kind == "base-file" else binding.head_revision
    payload = _git_blob(repo, revision, locator["path"], label)
    try:
        text = payload.decode("utf-8", errors="strict").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as exc:
        raise _fail(
            "locator.content_invalid", f"{label} must refer to UTF-8 text", path=locator["path"]
        ) from exc
    lines = text.splitlines()
    if locator["end_line"] > len(lines):
        raise _fail(
            "locator.range_invalid",
            f"{label} line range {locator['start_line']}-{locator['end_line']} exceeds {len(lines)} lines",
            category="missing_evidence",
            path=locator["path"],
        )
    return {"kind": kind, "locator": f"{revision}:{locator['path']}#L{locator['start_line']}-L{locator['end_line']}"}


def bind_locators(
    bundle: dict[str, Any], binding: GitBinding, sources: tuple[SourceBinding, ...]
) -> list[dict[str, Any]]:
    source_by_id = _source_map(sources)
    return [
        {
            **finding,
            "locators": [
                _bind_locator(locator, f"findings[{finding_index}].locators[{locator_index}]", binding, source_by_id)
                for locator_index, locator in enumerate(finding["locators"])
            ],
        }
        for finding_index, finding in enumerate(bundle["findings"])
    ]


def bind_examined(
    bundle: dict[str, Any], binding: GitBinding, sources: tuple[SourceBinding, ...]
) -> list[dict[str, str]]:
    source_by_id = _source_map(sources)
    return [
        _bind_locator(locator, f"examined[{index}]", binding, source_by_id)
        for index, locator in enumerate(bundle["examined"])
    ]


def _changed_paths(binding: GitBinding) -> list[str]:
    repo = Path(binding.repository_root)
    options = ("diff", "--name-only", "--no-renames", "--no-ext-diff", "-z")
    diff = _git(repo, *options, f"{binding.base_revision}...{binding.head_revision}", "--")
    if diff.returncode:
        diff = _git(repo, *options, binding.base_revision, binding.head_revision, "--")
    if diff.returncode:
        message = "changed paths between base and head cannot be listed"
        detail = diff.stderr.decode("utf-8", errors="replace").strip()
        raise _fail(
            "target.delta_unavailable",
            message,
            category="missing_evidence",
            path=repo,
            evidence=tuple(item for item in (message, detail) if item),
        )
    return sorted({item for item in diff.stdout.decode("utf-8", errors="replace").split("\0") if item})


def _unexamined_paths(bundle: dict[str, Any], changed: list[str]) -> list[str]:
    cited = {
        locator["path"]
        for locator in [*bundle["examined"], *(item for finding in bundle["findings"] for item in finding["locators"])]
        if locator["kind"] in FILE_LOCATOR_KINDS | PATH_LOCATOR_KINDS
    }
    return [path for path in changed if path not in cited]


def _unnamed_paths(paths: list[str], changed: list[str], limitations: list[str]) -> list[str]:
    """Return paths that no limitation names as a complete path rather than inside a longer one."""
    # Paths never contain NUL, so no match spans two limitations.
    text = "\0".join(limitations)
    spans = sorted(span for other in changed for span in _occurrences(other, text))
    starts = [start for start, _ in spans]
    reach: list[int] = []
    longest_at: dict[int, int] = {}
    for start, end in spans:
        reach.append(max(end, reach[-1]) if reach else end)
        longest_at[start] = max(end, longest_at.get(start, end))

    def covered(start: int, end: int) -> bool:
        # Any other changed-path match enclosing this span is longer and contains the path.
        before = bisect.bisect_left(starts, start)
        return (before > 0 and reach[before - 1] >= end) or longest_at.get(start, end) > end

    return [path for path in paths if all(covered(*span) for span in _occurrences(path, text, bounded=True))]


def _occurrences(path: str, text: str, *, bounded: bool = False) -> list[tuple[int, int]]:
    """Return non-overlapping spans of path in text; bounded spans must not continue a longer path-like name."""
    spans: list[tuple[int, int]] = []
    start = text.find(path)
    while start >= 0:
        end = start + len(path)
        if bounded and (
            (start and PATH_CHAR_RE.match(text, start - 1))
            or PATH_CONTINUATION_RE.match(text, end)
        ):
            start = text.find(path, start + 1)
            continue
        spans.append((start, end))
        start = text.find(path, end)
    return spans


def _scalar(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def render_result(
    bundle: dict[str, Any],
    binding: GitBinding,
    sources: tuple[SourceBinding, ...],
    examined: list[dict[str, str]],
    findings: list[dict[str, Any]],
    unexamined: list[str],
) -> str:
    lines = ["# Assessment", "", "## Result", "", f"`{bundle['result']}`", "", "## Findings", ""]
    if not findings:
        lines.append("No material findings.")
    for index, finding in enumerate(findings, start=1):
        if index > 1:
            lines.append("")
        lines.extend(
            [
                f"### Finding {index}",
                "",
                f"- Severity: {_scalar(finding['severity'])}",
                f"- Basis: {_scalar(finding['basis'])}",
                f"- Defect: {_scalar(finding['defect'])}",
                "- Evidence / authority:",
                *[f"  - {_scalar(locator)}" for locator in finding["locators"]],
                f"- Consequence: {_scalar(finding['consequence'])}",
                f"- Required truth: {_scalar(finding['required_truth'])}",
            ]
        )
    lines.extend(["", "## Limitations", ""])
    if not bundle["limitations"]:
        lines.append(NO_LIMITATIONS)
    else:
        lines.extend(f"- {_scalar(item)}" for item in bundle["limitations"])
    lines.extend(["", "## Changed paths not examined", ""])
    if not unexamined:
        lines.append("None.")
    lines.extend(f"- {_scalar(path)}" for path in unexamined)
    lines.extend(
        [
            "",
            "## Target",
            "",
            f"- Target: {_scalar(bundle['target'])}",
            f"- Repository root: {_scalar(binding.repository_root)}",
            f"- Repository ID: {_scalar(binding.repository_id)}",
            f"- Base ref: {_scalar(binding.base_ref)}",
            f"- Base revision: {_scalar(binding.base_revision)}",
            f"- Head ref: {_scalar(binding.head_ref)}",
            f"- Head revision: {_scalar(binding.head_revision)}",
            "",
            "## Assessed snapshots",
            "",
        ]
    )
    lines.extend(f"- {_scalar(source.as_dict())}" for source in sources)
    lines.extend(["", "## Examined", ""])
    if not examined:
        lines.append("No examined locators.")
    lines.extend(f"- {_scalar(locator)}" for locator in examined)
    body = "\n".join(lines) + "\n"
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return body + f"<!-- assessment-result: {CONTRACT_VERSION}; sha256: {digest} -->\n"


def _json_field(body: str, label: str) -> str:
    prefix = f"- {label}: "
    values = [line[len(prefix) :] for line in body.splitlines() if line.startswith(prefix)]
    if len(values) != 1:
        raise _fail("artifact.shape_invalid", f"assessment.md must contain exactly one {label} field", path=RESULT_FILENAME)
    try:
        value = json.loads(values[0])
    except json.JSONDecodeError as exc:
        raise _fail("artifact.shape_invalid", f"assessment.md {label} field is malformed", path=RESULT_FILENAME) from exc
    if not isinstance(value, str) or not value:
        raise _fail(
            "artifact.shape_invalid", f"assessment.md {label} field must be a non-empty string", path=RESULT_FILENAME
        )
    return value


def _parse_sources(body: str) -> list[dict[str, str]]:
    try:
        raw_section = body.split("\n## Assessed snapshots\n\n", 1)[1].split("\n## Examined\n", 1)[0]
    except IndexError as exc:
        raise _fail(
            "artifact.shape_invalid", "assessment.md assessed snapshots section is missing", path=RESULT_FILENAME
        ) from exc
    entries: list[dict[str, str]] = []
    for line in [item for item in raw_section.splitlines() if item]:
        if not line.startswith("- "):
            raise _fail(
                "artifact.shape_invalid",
                "assessment.md assessed snapshot entries must be list items",
                path=RESULT_FILENAME,
            )
        try:
            entry = json.loads(line[2:])
        except json.JSONDecodeError as exc:
            raise _fail(
                "artifact.shape_invalid", "assessment.md assessed snapshot entry is malformed", path=RESULT_FILENAME
            ) from exc
        if not isinstance(entry, dict) or set(entry) != {"id", "role", "locator", "path", "sha256"}:
            raise _fail(
                "artifact.shape_invalid",
                "assessment.md assessed snapshot entry has unsupported shape",
                path=RESULT_FILENAME,
            )
        values: dict[str, str] = {}
        for key, value in entry.items():
            if not isinstance(value, str) or not value:
                raise _fail(
                    "artifact.shape_invalid",
                    f"assessment.md assessed snapshot {key} must be a non-empty string",
                    path=RESULT_FILENAME,
                )
            values[key] = value
        if not SOURCE_ID_RE.fullmatch(values["id"]):
            raise _fail("artifact.shape_invalid", "assessment.md assessed snapshot id is invalid", path=RESULT_FILENAME)
        if values["role"] not in SOURCE_ROLES:
            raise _fail("artifact.shape_invalid", "assessment.md assessed snapshot role is invalid", path=RESULT_FILENAME)
        if not SHA256_RE.fullmatch(values["sha256"]):
            raise _fail("artifact.shape_invalid", "assessment.md assessed snapshot sha256 is invalid", path=RESULT_FILENAME)
        entries.append(values)
    if len({entry["id"] for entry in entries}) != len(entries):
        raise _fail("artifact.shape_invalid", "assessment.md assessed snapshot ids must be unique", path=RESULT_FILENAME)
    return entries


def parse_result(text: str) -> dict[str, Any]:
    head, separator, final = text.removesuffix("\n").rpartition("\n")
    body = head + "\n"
    match = RECEIPT_RE.fullmatch(final) if separator else None
    if match is None:
        for candidate in (final, text.partition("\n")[0]):
            retired = RETIRED_RECEIPT_RE.match(candidate)
            if retired is not None and not compatible_version(retired.group(1), CONTRACT_VERSION):
                raise _fail(
                    "artifact.version_unsupported",
                    f"assessment.md was sealed under unsupported Assess result contract {retired.group(1)}; "
                    f"contract {CONTRACT_VERSION} requires a fresh full assessment",
                    category="stale_evidence",
                    path=RESULT_FILENAME,
                )
        raise _fail(
            "artifact.receipt_invalid",
            "assessment.md receipt is missing, malformed, or not its final line",
            path=RESULT_FILENAME,
        )
    if any(line.startswith("<!-- assessment-result:") for line in body.splitlines()):
        raise _fail(
            "artifact.receipt_invalid",
            "assessment.md must carry exactly one receipt, on its final line",
            path=RESULT_FILENAME,
        )
    actual = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if actual != match.group(1):
        raise _fail(
            "artifact.integrity_stale",
            "assessment.md receipt does not match its content",
            category="stale_evidence",
            path=RESULT_FILENAME,
        )
    headings = HEADING_RE.findall(body)
    if (
        len(headings) < len(LEADING_HEADINGS) + len(TRAILING_HEADINGS)
        or headings[: len(LEADING_HEADINGS)] != LEADING_HEADINGS
        or headings[-len(TRAILING_HEADINGS) :] != TRAILING_HEADINGS
    ):
        raise _fail("artifact.shape_invalid", "assessment.md headings are not canonical", path=RESULT_FILENAME)
    finding_headings = headings[len(LEADING_HEADINGS) : -len(TRAILING_HEADINGS)]
    if finding_headings != [f"### Finding {index}" for index in range(1, len(finding_headings) + 1)]:
        raise _fail(
            "artifact.shape_invalid",
            "assessment.md finding headings must be contiguous and canonical",
            path=RESULT_FILENAME,
        )
    result_match = re.search(r"^## Result\n\n`(clear|findings|blocked)`$", body, re.MULTILINE)
    if result_match is None:
        raise _fail("artifact.shape_invalid", "assessment.md result is not canonical", path=RESULT_FILENAME)
    result = result_match.group(1)
    if result == "clear" and finding_headings:
        raise _fail("artifact.shape_invalid", "clear assessment.md cannot contain findings", path=RESULT_FILENAME)
    if result == "findings" and not finding_headings:
        raise _fail("artifact.shape_invalid", "findings assessment.md must contain a finding", path=RESULT_FILENAME)
    limitations = body.split("\n## Limitations\n\n", 1)[1].split("\n## Changed paths not examined\n", 1)[0]
    if result == "blocked" and limitations == f"{NO_LIMITATIONS}\n":
        raise _fail("artifact.shape_invalid", "blocked assessment.md requires a material limitation", path=RESULT_FILENAME)
    base_revision = _json_field(body, "Base revision")
    head_revision = _json_field(body, "Head revision")
    if not SHA_RE.fullmatch(base_revision) or not SHA_RE.fullmatch(head_revision):
        raise _fail("artifact.shape_invalid", "assessment.md revisions must be full commit IDs", path=RESULT_FILENAME)
    return {
        "target": _json_field(body, "Target"),
        "repository_root": _json_field(body, "Repository root"),
        "repository_id": _json_field(body, "Repository ID"),
        "base_ref": _json_field(body, "Base ref"),
        "base_revision": base_revision,
        "head_ref": _json_field(body, "Head ref"),
        "head_revision": head_revision,
        "assessed_sources": _parse_sources(body),
        "result": result,
    }


def _canonical_output(repo_root: Path, output: Path) -> Path:
    if output.name != RESULT_FILENAME:
        raise _fail(
            "output.name_invalid",
            f"Assess output must be named exactly {RESULT_FILENAME}",
            category="unsafe_state",
            path=output,
        )
    if os.path.lexists(output) and output.is_symlink():
        raise _fail("output.symlink_unsafe", "Assess output cannot be a symlink", category="unsafe_state", path=output)
    try:
        parent = output.parent.resolve(strict=True)
    except OSError as exc:
        raise _fail(
            "output.parent_missing",
            f"Assess output parent must already exist: {output.parent}",
            category="unsafe_state",
            path=output,
        ) from exc
    if not parent.is_dir():
        raise _fail(
            "output.parent_invalid",
            f"Assess output parent is not a directory: {parent}",
            category="unsafe_state",
            path=output,
        )
    root = repo_root.resolve()
    parts = parent.relative_to(root).parts if _within(parent, root) else ()
    try:
        valid_slug = (
            len(parts) == 3
            and parts[:2] == ASSESSMENT_WORKSPACE_PARTS
            and _normalize_assessment_slug(parts[2]) == parts[2]
        )
    except AssessError:
        valid_slug = False
    if not valid_slug:
        raise _fail(
            "output.outside_workspace",
            "Assess output must resolve to .first-four-hours/assessments/<slug>/assessment.md inside the assessed repository",
            category="unsafe_state",
            path=output,
        )
    destination = parent / RESULT_FILENAME
    if destination.exists() and not destination.is_file():
        raise _fail(
            "output.type_invalid",
            f"Assess output is not a regular file: {destination}",
            category="unsafe_state",
            path=destination,
        )
    if _within(destination, SKILL_ROOT):
        raise _fail(
            "output.in_skill",
            "Assess output cannot be stored inside the installed skill",
            category="unsafe_state",
            path=destination,
        )
    _refuse_tracked_namespace(root)
    relative = destination.relative_to(root).as_posix()
    ignored = _git(root, "check-ignore", "--no-index", "--quiet", "--", relative)
    if ignored.returncode != 0:
        raise _fail(
            "output.not_ignored",
            "Assess output inside the assessed repository must be ignored",
            category="unsafe_state",
            path=destination,
        )
    return destination


def _source_bindings_match(current: tuple[SourceBinding, ...], expected: tuple[SourceBinding, ...]) -> bool:
    return tuple(source.as_dict() for source in current) == tuple(source.as_dict() for source in expected)


def _publish(
    destination: Path,
    content: str,
    repo_root: Path,
    bundle: dict[str, Any],
    binding: GitBinding,
    source_bindings: tuple[SourceBinding, ...],
) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=destination.parent, delete=False
        ) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            temporary = Path(stream.name)
        current = inspect_binding(repo_root, bundle["base_ref"], bundle["head_ref"])
        current_sources = bind_sources(bundle, repo_root, destination)
        if current != binding or not _source_bindings_match(current_sources, source_bindings):
            raise _fail(
                "result.stale",
                "base/head or assessed snapshot identity changed while assessment.md was being sealed",
                category="stale_evidence",
                path=destination,
            )
        if _canonical_output(repo_root, destination) != destination:
            raise _fail(
                "output.changed",
                "Assess output identity changed before publication",
                category="unsafe_state",
                path=destination,
            )
        os.replace(temporary, destination)
        temporary = None
    except OSError as exc:
        raise _fail(
            "output.write_failed", f"Assess publication failed: {exc}", category="unsafe_state", path=destination
        ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def seal_result(repo_root: Path, bundle_path: Path, output: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    bundle = read_bundle(bundle_path, root)
    binding = inspect_binding(root, bundle["base_ref"], bundle["head_ref"])
    destination = _canonical_output(Path(binding.repository_root), output)
    source_bindings = bind_sources(bundle, Path(binding.repository_root), destination)
    findings = bind_locators(bundle, binding, source_bindings)
    examined = bind_examined(bundle, binding, source_bindings)
    changed = _changed_paths(binding)
    unexamined = _unexamined_paths(bundle, changed)
    unnamed = _unnamed_paths(unexamined, changed, bundle["limitations"])
    if unnamed:
        raise _fail(
            "result.unexamined_undisclosed",
            "changed paths that no examined or finding locator cites must be inspected or named in limitations "
            "by their complete repository paths; unnamed: " + ", ".join(unnamed),
            category="contract_contradiction",
            evidence=tuple(unnamed),
        )
    content = render_result(bundle, binding, source_bindings, examined, findings, unexamined)
    _publish(destination, content, Path(binding.repository_root), bundle, binding, source_bindings)
    return {
        "path": str(destination),
        "target": bundle["target"],
        "result": bundle["result"],
        "base_revision": binding.base_revision,
        "head_revision": binding.head_revision,
        "current": True,
        "unexamined_changed_paths": unexamined,
    }


def _stored_sources_current(stored: list[dict[str, str]], root: Path, destination: Path) -> list[str]:
    mismatches: list[str] = []
    for source in stored:
        try:
            path = _canonical_source_path(source["path"], root, destination)
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except AssessError as exc:
            raise exc
        except OSError as exc:
            raise _fail(
                "source.missing",
                f"assessed source snapshot cannot be read: {source['path']}",
                category="missing_evidence",
                path=source["path"],
            ) from exc
        expected_binding = {key: source[key] for key in ("id", "role", "locator", "path", "sha256")}
        actual_binding = {
            "id": source["id"],
            "role": source["role"],
            "locator": source["locator"],
            "path": str(path),
            "sha256": actual,
        }
        if actual_binding != expected_binding:
            mismatches.append(f"source {source['id']}: stored={expected_binding!r}, current={actual_binding!r}")
    return mismatches


def check_result(repo_root: Path, output: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    destination = _canonical_output(root, output)
    if not destination.is_file():
        raise _fail(
            "artifact.missing",
            f"assessment.md is missing: {destination}",
            category="missing_evidence",
            path=destination,
        )
    try:
        stored = parse_result(destination.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise _fail("artifact.invalid", f"cannot read assessment.md: {exc}", path=destination) from exc
    current = inspect_binding(root, stored["base_ref"], stored["head_ref"])
    expected = {
        "repository_root": current.repository_root,
        "repository_id": current.repository_id,
        "base_revision": current.base_revision,
        "head_revision": current.head_revision,
    }
    mismatches = [field for field, value in expected.items() if stored[field] != value]
    source_mismatches = _stored_sources_current(stored["assessed_sources"], root, destination)
    if mismatches or source_mismatches:
        evidence = tuple(
            [f"{field}: stored={stored[field]!r}, current={expected[field]!r}" for field in mismatches]
            + source_mismatches
        )
        raise _fail(
            "result.stale",
            "assessment.md no longer matches current target identity: "
            + ", ".join(mismatches + ["assessed_sources"] if source_mismatches else mismatches),
            category="stale_evidence",
            path=destination,
            evidence=evidence,
        )
    return {
        "path": str(destination),
        "target": stored["target"],
        "result": stored["result"],
        "base_revision": stored["base_revision"],
        "head_revision": stored["head_revision"],
        "current": True,
    }

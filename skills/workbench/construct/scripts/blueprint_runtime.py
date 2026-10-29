"""Mechanical runtime for the implementation-complete Blueprint contract.

The runtime deliberately knows only the document shape and facts that can be
checked without making a planning judgment. Meaningful engineering decisions
remain in the authored Markdown; the receipt binds that Markdown to its
request, repository, and declared locations and sources.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unicodedata
from importlib import import_module
from pathlib import Path
from typing import Any, Iterable, NoReturn

from _diagnostic_contract import normalize_diagnostic
from _skill_protocol_runtime import compatible_version, compatible_version_pattern


def write_utf8(text: str) -> None:
    """Emit CLI output as UTF-8 bytes regardless of console encoding.

    Sealed artifacts and verification payloads are UTF-8 documents; writing raw
    bytes through the stream's buffer keeps them intact on cp1252 consoles
    instead of crashing after the work is already done.
    """
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(text.encode("utf-8"))
        sys.stdout.flush()
        return
    sys.stdout.write(text)


CONTRACT_VERSION = "1.0.4"
STEP_ATTEMPT_LIMIT = 3
BLUEPRINT_FILENAME = "blueprint.md"
REQUEST_FILENAME = "request.md"
ARTIFACT_ROOT = ".first-four-hours"
BLUEPRINT_WORKSPACE_PARTS = (ARTIFACT_ROOT, "blueprints")
BLUEPRINT_WORKSPACE_DIR = "/".join(BLUEPRINT_WORKSPACE_PARTS)
BLUEPRINT_WORKSPACE_RULE = f"/{BLUEPRINT_WORKSPACE_DIR}/"
RETIRED_BLUEPRINT_ARTIFACTS = {"plan.md", "plan-context.md", "blueprint-context.md"}
CONTRACT_MARKER_RE = re.compile(rf"^<!--\x20blueprint-contract: {compatible_version_pattern(CONTRACT_VERSION)} -->$")
CONTRACT_MARKER = f"<!-- blueprint-contract: {CONTRACT_VERSION} -->"

PROOF_RE = re.compile(r"^<!-- blueprint-proof: (?P<json>.+) -->$", re.MULTILINE)
VALIDATION_RE = re.compile(
    rf"^<!-- blueprint-validation: {compatible_version_pattern(CONTRACT_VERSION)}; plan-sha256: (?P<plan>[0-9a-f]{{64}}); "
    r"proof-sha256: (?P<proof>[0-9a-f]{64}) -->$",
    re.MULTILINE,
)
RECEIPT_PREFIX_RE = re.compile(r"<!--\s*blueprint-(?:proof|validation)\b", re.IGNORECASE)

DIAGNOSIS_HANDOFF_VERSION = "1.0.0"
ARCHITECTURE_HANDOFF_VERSION = "1.0.0"
TICKET_SCOPE_HANDOFF_VERSION = "1.0.0"
HANDOFF_RECEIPT_RE = re.compile(
    r"^<!-- (?P<marker>diagnosis|architecture|ticket-scope): "
    r"(?P<version>[^;\s]+); sha256: (?P<digest>[0-9a-f]{64}) -->$"
)
CANONICAL_HANDOFF_MARKER_RE = re.compile(
    r"^<!--\s*(?:diagnosis|architecture|ticket-scope|optimization)(?=\s|:|-->|$)",
    re.IGNORECASE,
)
HANDOFF_LIKE_RE = re.compile(r"^<!-- [^>]*handoff[^>]*-->$", re.IGNORECASE)
RECEIPT_SHAPED_RE = re.compile(
    r"^<!--\s*(?:diagnosis|architecture|ticket-scope|optimization)"
    r"(?:\s*:\s*\d+(?:\.\d+)*\s*(?:;|-->)|(?=\s|:)[^\n]*\bsha256\b)",
    re.IGNORECASE,
)


def _clean_architecture_view(text: str) -> str:
    """Remove fenced code, blockquotes and inline code for intake recognition.

    Reserved architecture receipts, proofs, decision headings and source
    declarations are authoritative only outside fenced code and blockquotes.
    Ordinary prose mentions, inline examples and fenced quoted examples stay
    non-authoritative generic input. Signed bytes are never normalized here."""
    lines = text.splitlines()
    cleaned: list[str] = []
    in_fence = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.lstrip().startswith(">"):
            continue
        cleaned.append(re.sub(r"`[^`\n]*`", "", line))
    return "\n".join(cleaned)


def _has_unquoted_architecture_source(cleaned: str) -> bool:
    return bool(re.search(r"<!--\s*architecture-source\b", cleaned))


def _has_unquoted_architecture_raw(cleaned: str) -> bool:
    if re.search(r"<!--\s*architecture:\s*\d+\s*;", cleaned):
        return True
    if re.search(r"<!--\s*architecture-proof\b", cleaned):
        return True
    if re.search(r"(?m)^[ \t]*# Architecture Decision:", cleaned):
        return True
    without_source = re.sub(r"<!--\s*architecture-source\b[^\n]*", "", cleaned)
    return bool(re.search(r"<!--\s*architecture\b", without_source))


def _looks_like_architecture_input(text: str) -> bool:
    cleaned = _clean_architecture_view(text)
    return _has_unquoted_architecture_raw(cleaned) or _has_unquoted_architecture_source(cleaned)


RETIRED_HANDOFF_ARTIFACTS = {
    "audit-handoff.md",
    "optimization-handoff.md",
    "optimization.md",
    "design-handoff.md",
    "ticket-handoff.md",
    "issue-handoff.md",
}

TOP_LEVEL_HEADING_RE = re.compile(r"^##[ \t]+(?P<name>[^#].*?)[ \t]*$", re.ASCII)
H3_HEADING_RE = re.compile(r"^###[ \t]+(?P<name>[^#].*?)[ \t]*$", re.ASCII)
STEP_HEADING_RE = re.compile(r"^###[ \t]+(?P<number>[1-9]\d*)\.(?P<title>[ \t]+\S.*?)?[ \t]*$")
LOCATION_RE = re.compile(r"^\s*(?:[-*][ \t]+)?\*\*Location\:\*\*", re.IGNORECASE)
STATE_RE = re.compile(r"^\s*(?:[-*][ \t]+)?\*\*[Ss][Tt][Aa][Tt][Ee]\:\*\*[ \t]*(?P<value>existing|new|deleted)[ \t]*$")
STATE_LIKE_RE = re.compile(r"^\s*(?:[-*][ \t]+)?\*\*[Ss][Tt][Aa][Tt][Ee]\:\*\*", re.IGNORECASE)
SOURCE_RE = re.compile(r"^\s*(?:[-*][ \t]+)?\*\*Source\:\*\*", re.IGNORECASE)
RETIRED_DECLARATION_RE = re.compile(
    r"^\s*(?:[-*][ \t]+)?\*\*(?:Evidence|Locator)\:\*\*", re.IGNORECASE
)
STRICT_SPAN_RE = re.compile(r"^\s*`(?P<content>[^`\r\n]+)`\s*$")
CONTRACT_FAMILY_RE = re.compile(r"<!--\s*blueprint-contract\b", re.IGNORECASE)
RUN_LIKE_RE = re.compile(r"^\s*(?:[-*][ \t]+)?Run\:\s*", re.IGNORECASE)
EXPECT_LIKE_RE = re.compile(r"^\s*(?:[-*][ \t]+)?Expect\:\s*", re.IGNORECASE)
TIMEOUT_LIKE_RE = re.compile(r"^\s*(?:[-*][ \t]+)?Timeout\:\s*", re.IGNORECASE)
TIMEOUT_VALUE_RE = re.compile(r"^(?P<value>\d+)$")
BLOCK_LABEL_RE = re.compile(r"^\s*(?:[-*][ \t]+)?\*\*(?P<kind>Exact|Frozen)\:\*\*", re.IGNORECASE)
WITH_LABEL_RE = re.compile(r"^\s*(?:[-*][ \t]+)?\*\*With\:\*\*", re.IGNORECASE)
PROOF_LABEL_RE = re.compile(r"^\s*(?:[-*][ \t]+)?\*\*Proof run\:\*\*", re.IGNORECASE)
RED_LIKE_RE = re.compile(r"^\s*(?:[-*][ \t]+)?Red\:\s*", re.IGNORECASE)
INCOMPLETE_LIKE_RE = re.compile(r"^\s*(?:[-*][ \t]+)?Incomplete\:\s*", re.IGNORECASE)
NEAR_LABEL_RE = re.compile(
    r"^\s*(?:(?:[-*+]|\d+\.)[ \t]+)?[*_`]{0,3}\s*(?:exact|frozen|with|proof(?:\s+run)?|red|incomplete)\s*[*_`]{0,3}\s*:",
    re.IGNORECASE,
)
FENCE_OPEN_RE = re.compile(r"^(?P<fence>`{3,}|~{3,})")
EXIT_NUMERIC_STATUS_RE = re.compile(
    r"\b(?:"
    r"exit(?:s|ed)?(?:[\s:=\-]*(?:code|status|with|of|is)){0,2}"
    r"|returncode"
    r"|return(?:s|ed)?[\s:=\-]+(?:code|status)"
    r")\b[\s:=\-]*`?\s*(?P<value>[+-]?[0-9]+)\b",
    re.IGNORECASE,
)
EXIT_RELATIONAL_STATUS_RE = re.compile(
    r"\b(?:exit(?:[\s:=\-]+(?:code|status))?|return[\s:=\-]+(?:code|status)|returncode|status)\b"
    r"[\s:=\-]*(?:is[\s:=\-]*)?(?P<qualifier>greater\s+than[\s:=\-]+(?:zero|0))\b",
    re.IGNORECASE,
)
EXIT_QUALIFIER_BEFORE_STATUS_RE = re.compile(
    r"(?<![\w-])(?P<qualifier>non[-\s]?zero|failing|unsuccessful)(?![\w-])"
    r"[\s:=\-]+(?:exit(?:[\s:=\-]+(?:code|status))?"
    r"|return[\s:=\-]+(?:code|status)|returncode|status)\b",
    re.IGNORECASE,
)
EXIT_QUALIFIER_AFTER_STATUS_RE = re.compile(
    r"\b(?:exit(?:s|ed)?(?:[\s:=\-]+(?:code|status))?"
    r"|returncode|return(?:s|ed)?[\s:=\-]+(?:code|status)|status)\b"
    r"(?:[\s:=\-]*(?:is|with|of))?[\s:=\-]+"
    r"(?P<qualifier>non[-\s]?zero|failing|unsuccessful)(?![\w-])",
    re.IGNORECASE,
)
EXIT_CLAUSE_BOUNDARY_RE = re.compile(
    r"[,;:.!?]|\s[\u2013\u2014]\s|\b(?:and|but|or|yet|while|whereas|although|though)\b",
    re.IGNORECASE,
)
EXIT_NEGATION_RE = re.compile(
    r"\b(?:no|not|never|without|neither|nor|rather\s+than)\b", re.IGNORECASE
)
EMBEDDED_PLACEHOLDER_RE = re.compile(r"<\s*fill[\s-]?me\s*>|<\s*value\s*>|=\s*TBD\b", re.IGNORECASE)
SYMBOL_SUFFIX_RE = re.compile(r"::(?P<symbol>[^:\s`]+)$")
LOCATOR_SUFFIX_RE = re.compile(
    r"(?:(?::(?P<start>[1-9]\d*)(?:[-\u2013](?P<end>[1-9]\d*))?)|"
    r"#L(?P<hash_start>[1-9]\d*)(?:-L?(?P<hash_end>[1-9]\d*))?)$"
)
LOCATOR_SUFFIX_LIKE_RE = re.compile(r"(?:\:[0-9][^/\\\s]*|#L[0-9][^/\\\s]*)$")
SHELL_CHAIN_TOKENS = frozenset({"&&", "||", ";", "|"})
MUTATING_GIT_COMMANDS = frozenset(
    {
        "add",
        "apply",
        "checkout",
        "cherry-pick",
        "clean",
        "commit",
        "merge",
        "mv",
        "push",
        "rebase",
        "reset",
        "restore",
        "revert",
        "rm",
        "stash",
        "switch",
        "update-index",
    }
)
SHELL_EXECUTABLES = frozenset(
    {"bash", "cmd", "cmd.exe", "dash", "fish", "ksh", "powershell", "powershell.exe", "pwsh", "sh", "zsh"}
)
TEMPLATE_SENTINEL_RE = re.compile(
    r"^(?:TBD|<fill[ -]?me>|<value>)[.!?]?$",
    re.IGNORECASE,
)
REQUIRED_SECTIONS = ("Goal", "Current State", "Implementation", "Verification", "Completion Conditions")
OPTIONAL_SECTIONS = ("Risks / Recovery",)
SECTION_ORDER = REQUIRED_SECTIONS + OPTIONAL_SECTIONS
VERIFICATION_PHASES = ("Before implementation", "After implementation")
DEFAULT_VERIFICATION_TIMEOUT_SECONDS = 900


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclasses.dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    required_action: str
    path: str | None = None
    line: int | None = None
    category: str = "malformed_input"

    def __str__(self) -> str:
        location = f" line {self.line}" if self.line else ""
        return f"{self.code}{location}: {self.message}"

    def to_dict(self, *, artifact: str = BLUEPRINT_FILENAME) -> dict[str, Any]:
        supporting = [self.message]
        if self.line:
            supporting.append(f"{artifact} line {self.line}")
        return normalize_diagnostic(
            {
                "code": self.code,
                "category": self.category,
                "message": self.message,
                "path": self.path or artifact,
                "required_action": self.required_action,
                "valid_repairs": [self.required_action],
                "supporting_evidence": supporting,
                "why_it_matters": "The Blueprint cannot be sealed until this exact mechanical defect is repaired.",
            },
            skill="blueprint",
            phase="seal",
            artifact=artifact,
            path=self.path or artifact,
        )


@dataclasses.dataclass(frozen=True)
class SourceLocator:
    path: str
    start: int | None
    end: int | None
    line: int

    def shape(self) -> dict[str, Any]:
        return {"path": self.path, "start": self.start, "end": self.end}


@dataclasses.dataclass(frozen=True)
class TargetLocation:
    path: str
    symbol: str | None
    state: str
    line: int

    def shape(self) -> dict[str, Any]:
        value: dict[str, Any] = {"path": self.path, "state": self.state}
        if self.symbol is not None:
            value["symbol"] = self.symbol
        return value


@dataclasses.dataclass(frozen=True)
class VerificationStep:
    argv: tuple[str, ...]
    timeout_seconds: int
    phase: str
    line: int
    incomplete: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "phase": self.phase,
            "argv": list(self.argv),
            "timeout_seconds": self.timeout_seconds,
            "line": self.line,
        }
        if self.incomplete is not None:
            value["incomplete"] = self.incomplete
        return value


@dataclasses.dataclass(frozen=True)
class TextBlock:
    """Exact planned text for one step Location.

    ``exact`` blocks are implementation text; ``frozen`` blocks are
    planner-authored proof the executor writes verbatim and never edits. With
    ``old`` unset the block is the file's entire final content; otherwise the
    whole lines in ``old`` are replaced by ``text``. Every block line ends in
    one newline, and comparison is over UTF-8 text with CRLF read as LF.
    """

    kind: str
    path: str
    text: str
    line: int
    old: str | None = None

    def to_dict(self) -> dict[str, Any]:
        form = "file" if self.old is None else "replace"
        return {"kind": self.kind, "path": self.path, "line": self.line, "form": form}


@dataclasses.dataclass(frozen=True)
class ImplementationStep:
    number: int
    title: str
    line: int
    locations: tuple[TargetLocation, ...]
    blocks: tuple[TextBlock, ...] = ()
    proof: VerificationStep | None = None
    red: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "line": self.line,
            "locations": [item.shape() for item in self.locations],
            "blocks": [item.to_dict() for item in self.blocks],
            "proof": self.proof.to_dict() if self.proof is not None else None,
            "red": self.red,
        }


@dataclasses.dataclass(frozen=True)
class Blueprint:
    title: str
    text: str
    sections: tuple[str, ...]
    steps: tuple[ImplementationStep, ...]
    verification: tuple[VerificationStep, ...]
    locations: tuple[TargetLocation, ...] = ()
    sources: tuple[SourceLocator, ...] = ()
    binding: dict[str, Any] | None = None
    receipt: dict[str, str] | None = None
    plan_sha256: str | None = None

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        result = {
            "contract_version": CONTRACT_VERSION,
            "title": self.title,
            "sections": list(self.sections),
            "steps": [item.to_dict() for item in self.steps],
            "verification": [item.to_dict() for item in self.verification],
            "locations": [item.shape() for item in self.locations],
            "sources": [item.shape() for item in self.sources],
        }
        if self.plan_sha256 is not None:
            result["plan_sha256"] = self.plan_sha256
        return result


@dataclasses.dataclass(frozen=True)
class ValidationResult:
    blueprint: Blueprint | None
    diagnostics: tuple[Diagnostic, ...]
    view: "RepositoryView"

    @property
    def valid(self) -> bool:
        return self.blueprint is not None and not self.diagnostics

    @property
    def counters(self) -> dict[str, Any]:
        return self.view.counters()


@dataclasses.dataclass(frozen=True)
class SealResult:
    text: str
    proof: dict[str, Any]
    counters: dict[str, Any]


@dataclasses.dataclass(frozen=True)
class WorkspaceReservation:
    slug: str
    request_path: Path
    blueprint_path: Path
    relative_request_path: str
    relative_blueprint_path: str
    git_exclude: Path | None
    git_ignored: bool


class RepositoryView:
    """Read only declared locator files and minimal Git identity metadata."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()
        if not self.repo_root.is_dir():
            raise ValueError(f"repository root is not a directory: {self.repo_root}")
        self.opened_paths: list[str] = []
        self.bytes_read = 0
        self.hash_count = 0
        self._identity: tuple[str, str | None] | None = None
        self.inside_worktree: bool | None = None

    def _relative(self, raw: str) -> Path:
        normalized = raw.replace("\\", "/")
        if not raw:
            raise ValueError("source locator path must be repository-relative")
        if re.match(r"^[A-Za-z]:/", normalized) or normalized.startswith("//"):
            raise ValueError("source locator path must be repository-relative")
        relative = Path(normalized)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("source locator path must be repository-relative")
        if is_blueprint_workspace_path(normalized):
            raise ValueError("source locator path must not reference the Blueprint workspace")
        return relative

    def resolve(self, raw: str) -> Path:
        relative = self._relative(raw)
        candidate = (self.repo_root / relative).resolve()
        try:
            candidate.relative_to(self.repo_root)
        except ValueError as exc:
            raise ValueError("source locator path escapes the repository") from exc
        return candidate

    def entry_path(self, raw: str) -> Path:
        """Return the lexical repository path for directory-entry checks.

        Existence must use directory-entry (lstat) semantics so a broken
        symlink counts as an occupied path; ``Path.exists`` would report a
        dangling symlink as absent and let a declared-new target hide an
        occupied path.
        """
        return self.repo_root / self._relative(raw)

    def path_key(self, raw: str) -> str:
        """One state per resolved file, respecting the host's path case rules."""
        return os.path.normcase(str(self.resolve(raw)))

    def entry_key(self, raw: str) -> str:
        """Identify the directory entry a spelling names, by each directory's stored names.

        A component the directory does not list but still opens was folded by the
        filesystem (case or Unicode normalization), so it takes the one stored name it
        composes to, else the one it case-folds to; a listed name, such as a hardlinked
        twin, is always its own entry.
        """
        current = self.repo_root
        for part in self.resolve(raw).relative_to(self.repo_root).parts:
            try:
                names = os.listdir(current)
            except OSError:
                names = []
            if part not in names and os.path.lexists(current / part):
                composed = unicodedata.normalize("NFC", part)
                stored = [name for name in names if unicodedata.normalize("NFC", name) == composed]
                if len(stored) != 1:
                    folded = composed.casefold()
                    stored = [name for name in names if unicodedata.normalize("NFC", name).casefold() == folded]
                if len(stored) == 1:
                    part = stored[0]
            current = current / part
        return os.path.normcase(str(current))

    def declared_path_key(self, raw: str) -> str:
        """Normalize authored aliases without following a changed filesystem link."""
        return os.path.normcase(os.path.abspath(self.entry_path(raw)))

    def read(self, raw: str) -> bytes:
        path = self.resolve(raw)
        if not path.is_file():
            raise FileNotFoundError(raw)
        data = path.read_bytes()
        relative = path.relative_to(self.repo_root).as_posix()
        if relative not in self.opened_paths:
            self.opened_paths.append(relative)
            self.bytes_read += len(data)
        return data

    def digest(self, raw: str) -> str:
        digest = _sha256(self.read(raw))
        self.hash_count += 1
        return digest

    def repository_identity(self) -> tuple[str, str | None]:
        if self._identity is not None:
            return self._identity
        metadata = _git(self.repo_root, "rev-parse", "--is-inside-work-tree", "HEAD")
        metadata_lines = metadata.stdout.strip().splitlines()
        if metadata.returncode == 0 and len(metadata_lines) == 2 and metadata_lines[0].strip() == "true" and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", metadata_lines[1].strip()):
            remote = _git(self.repo_root, "config", "--get", "remote.origin.url").stdout.strip()
            head = metadata_lines[1].strip() or None
            self._identity = (remote or str(self.repo_root), head)
            self.inside_worktree = True
        else:
            inside = _git(self.repo_root, "rev-parse", "--is-inside-work-tree")
            self.inside_worktree = inside.returncode == 0 and inside.stdout.strip() == "true"
            if self.inside_worktree:
                remote = _git(self.repo_root, "config", "--get", "remote.origin.url").stdout.strip()
                candidate_head = _git(self.repo_root, "rev-parse", "HEAD").stdout.strip()
                head = candidate_head if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", candidate_head) else None
                self._identity = (remote or str(self.repo_root), head)
            else:
                self._identity = (str(self.repo_root), None)
        return self._identity

    def counters(self) -> dict[str, Any]:
        return {
            "opened_paths": list(self.opened_paths),
            "bytes_read": self.bytes_read,
            "hash_count": self.hash_count,
        }


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


def _workspace_error(code: str, message: str, action: str) -> ValueError:
    error = ValueError(f"{code}: {message}")
    setattr(error, "diagnostics", (Diagnostic(code, message, action, category="unsafe_state"),))
    return error


def is_blueprint_workspace_path(raw: str | Path) -> bool:
    """Return whether a repository-relative value starts at the reserved workspace."""
    normalized = str(raw).replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    return tuple(part.casefold() for part in parts[:2]) == BLUEPRINT_WORKSPACE_PARTS


def normalize_task_slug(raw: str) -> str:
    """Normalize one explicit human task name to a safe lower-kebab segment."""
    if not isinstance(raw, str):
        raise _workspace_error(
            "workspace.slug.type", "task name must be a string", "Choose one human-readable task name."
        )
    value = raw.strip()
    if not value or value in {".", ".."}:
        raise _workspace_error(
            "workspace.slug.empty", "task name must not be empty or a dot segment", "Choose one concise task name."
        )
    if Path(value).is_absolute() or "/" in value or "\\" in value:
        raise _workspace_error(
            "workspace.slug.path",
            "task name must be one path segment",
            "Remove separators and absolute-path syntax from the task name.",
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise _workspace_error(
            "workspace.slug.control",
            "task name contains a control character",
            "Use printable task-name characters only.",
        )
    normalized = unicodedata.normalize("NFKC", value).casefold()
    slug = re.sub(r"-+", "-", "".join(character if character.isalnum() else "-" for character in normalized)).strip("-")
    if not slug or slug in {".", ".."}:
        raise _workspace_error(
            "workspace.slug.empty",
            "task name normalizes to an empty segment",
            "Choose a task name containing letters or digits.",
        )
    return slug


def _relative_to_root(root: Path, raw: str | Path) -> tuple[Path, Path]:
    root = root.resolve()
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise _workspace_error(
            "workspace.path.outside",
            f"path is not inside the bound repository: {raw}",
            f"Use repo/{BLUEPRINT_WORKSPACE_DIR}/<task-slug>/blueprint.md.",
        ) from exc
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise _workspace_error(
            "workspace.path.traversal",
            f"path contains an unsafe relative segment: {raw}",
            "Use exactly four clean repository-relative path segments.",
        )
    return root, candidate


def _canonical_workspace_path(
    repo_root: Path,
    raw: str | Path,
    filename: str,
    *,
    require_existing: bool = False,
) -> Path:
    """Validate one exact canonical file in a task-scoped workspace."""
    root, candidate = _relative_to_root(repo_root, raw)
    relative = candidate.relative_to(root)
    parts = relative.parts
    if len(parts) != 4 or parts[:2] != BLUEPRINT_WORKSPACE_PARTS or parts[3] != filename:
        raise _workspace_error(
            "workspace.path.shape",
            f"canonical workspace path must be {BLUEPRINT_WORKSPACE_DIR}/<task-slug>/{filename}: {relative.as_posix()}",
            f"Use the exact task-scoped {filename} path.",
        )
    if parts[2] != normalize_task_slug(parts[2]):
        raise _workspace_error(
            "workspace.path.slug",
            f"task directory is not normalized lower-kebab: {parts[2]}",
            "Use the normalized task path returned by workspace preparation.",
        )
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise _workspace_error(
                "workspace.path.symlink",
                f"Blueprint path contains a symlink: {current}",
                "Replace the symlink with a real repository-local directory or file.",
            )
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise _workspace_error(
            "workspace.path.escape",
            f"Blueprint path escapes the repository after resolution: {relative.as_posix()}",
            "Use a real repository-local task directory without symlink traversal.",
        ) from exc
    if require_existing and not candidate.is_file():
        raise _workspace_error(
            "workspace.path.missing",
            f"canonical workspace file does not exist: {candidate}",
            f"Create the canonical {filename} file before continuing.",
        )
    return candidate


def canonical_blueprint_path(repo_root: Path, raw: str | Path, *, require_existing: bool = False) -> Path:
    """Validate the exact repository path reserved for one Blueprint artifact."""
    return _canonical_workspace_path(repo_root, raw, BLUEPRINT_FILENAME, require_existing=require_existing)


def canonical_request_path(repo_root: Path, raw: str | Path, *, require_existing: bool = False) -> Path:
    """Validate the exact repository path reserved for one frozen request snapshot."""
    return _canonical_workspace_path(repo_root, raw, REQUEST_FILENAME, require_existing=require_existing)


def _workspace_task_directory(task_directory: Path, *, require_request: bool = False) -> frozenset[str]:
    """Validate one task workspace directory and return what its validated pass observed."""
    if task_directory.is_symlink():
        raise _workspace_error(
            "workspace.task.symlink", f"task directory is a symlink: {task_directory}", "Use a real task directory."
        )
    if task_directory.exists() and not task_directory.is_dir():
        raise _workspace_error(
            "workspace.task.not_directory",
            f"task path is not a directory: {task_directory}",
            "Use a directory for the task scope.",
        )
    observed: set[str] = set()
    if task_directory.is_dir():
        for child in task_directory.iterdir():
            observed.add(child.name)
            if child.name not in {REQUEST_FILENAME, BLUEPRINT_FILENAME}:
                raise _workspace_error(
                    "workspace.task.extra_artifact",
                    f"task directory contains an extra entry: {child}",
                    f"Keep each task directory to {REQUEST_FILENAME} and {BLUEPRINT_FILENAME} only.",
                )
            if child.is_symlink():
                raise _workspace_error(
                    "workspace.path.symlink",
                    f"canonical workspace file is a symlink: {child}",
                    "Use a real canonical workspace file.",
                )
            if not child.is_file():
                raise _workspace_error(
                    "workspace.task.unsafe_entry",
                    f"canonical workspace entry is not a regular file: {child}",
                    "Replace it with a regular canonical workspace file.",
                )
        if require_request and not (task_directory / REQUEST_FILENAME).is_file():
            raise _workspace_error(
                "workspace.task.request_missing",
                f"task directory is missing its canonical {REQUEST_FILENAME}: {task_directory}",
                f"Preserve the existing workspace and restore its exact {REQUEST_FILENAME} before retrying.",
            )
    return frozenset(observed)


def _git_context(root: Path) -> tuple[bool, Path | None]:
    result = _git(root, "rev-parse", "--is-inside-work-tree", "--git-path", "info/exclude")
    result_lines = result.stdout.strip().splitlines()
    if result.returncode == 0 and len(result_lines) == 2 and result_lines[0].strip() == "true":
        exclude_raw = result_lines[1].strip()
    else:
        inside = _git(root, "rev-parse", "--is-inside-work-tree")
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return False, None
        result = _git(root, "rev-parse", "--git-path", "info/exclude")
        exclude_raw = result.stdout.strip()
    if result.returncode != 0 or not exclude_raw:
        raise _workspace_error(
            "workspace.git.exclude_unresolved",
            "Git repository has no resolvable worktree-local info/exclude path",
            "Repair Git metadata or use a genuinely non-Git repository.",
        )
    exclude = Path(exclude_raw)
    if not exclude.is_absolute():
        exclude = root / exclude
    exclude = exclude.resolve(strict=False)
    if exclude.exists() and (exclude.is_dir() or exclude.is_symlink()):
        raise _workspace_error(
            "workspace.git.exclude_unsafe",
            f"Git exclude path is not a regular file: {exclude}",
            "Repair the Git exclude path before preparing a Blueprint.",
        )
    return True, exclude


def _assert_namespace_not_tracked(root: Path) -> None:
    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return
    tracked = _git(root, "ls-files", "--", BLUEPRINT_WORKSPACE_DIR)
    if tracked.returncode != 0:
        raise _workspace_error(
            "workspace.git.tracked_check",
            "cannot establish whether the Blueprint namespace is tracked",
            "Repair Git metadata before preparing a Blueprint.",
        )
    if tracked.stdout.strip():
        raise _workspace_error(
            "workspace.namespace.tracked",
            "the Blueprint namespace already contains tracked project files",
            f"Choose a repository without a tracked {BLUEPRINT_WORKSPACE_DIR}/ namespace or resolve the project conflict explicitly.",
        )


def _is_linked_directory(path: Path) -> bool:
    """Return whether path is a link, including a dangling one or a Windows junction pathlib does not report."""
    if path.is_symlink() or os.path.lexists(path) and not path.exists():
        return True
    return path.exists() and os.path.normcase(str(path.resolve())) != os.path.normcase(str(path.absolute()))


def _ensure_namespace(root: Path, task_slug: str) -> Path:
    artifact_root = root / ARTIFACT_ROOT
    if _is_linked_directory(artifact_root):
        raise _workspace_error(
            "workspace.namespace.symlink",
            f"Blueprint artifact root is a link: {artifact_root}",
            "Replace it with a real repository-local directory.",
        )
    if artifact_root.exists() and not artifact_root.is_dir():
        raise _workspace_error(
            "workspace.namespace.not_directory",
            f"Blueprint artifact root is not a directory: {artifact_root}",
            "Resolve the namespace conflict before preparing a Blueprint.",
        )
    workspace = root / BLUEPRINT_WORKSPACE_DIR
    if _is_linked_directory(workspace):
        raise _workspace_error(
            "workspace.namespace.symlink",
            f"Blueprint namespace is a link: {workspace}",
            "Replace it with a real repository-local directory.",
        )
    if workspace.exists() and not workspace.is_dir():
        raise _workspace_error(
            "workspace.namespace.not_directory",
            f"Blueprint namespace is not a directory: {workspace}",
            "Resolve the namespace conflict before preparing a Blueprint.",
        )
    _assert_namespace_not_tracked(root)
    if not workspace.exists():
        workspace.mkdir(parents=True)
    for child in workspace.iterdir():
        if child.is_symlink() or not child.is_dir():
            raise _workspace_error(
                "workspace.namespace.project_owned",
                f"Blueprint namespace contains an unsafe non-task entry: {child}",
                "Preserve the existing entry and resolve the namespace conflict explicitly.",
            )
        try:
            canonical_name = normalize_task_slug(child.name)
        except ValueError as exc:
            raise _workspace_error(
                "workspace.namespace.project_owned",
                f"Blueprint namespace contains a task directory with an invalid name: {child}",
                "Preserve the existing entry and resolve the namespace conflict explicitly.",
            ) from exc
        if child.name != canonical_name:
            raise _workspace_error(
                "workspace.namespace.project_owned",
                f"Blueprint namespace contains a noncanonical task directory: {child}; expected directory name {canonical_name}",
                "Preserve the existing entry and resolve the namespace conflict explicitly.",
            )
        try:
            _workspace_task_directory(child, require_request=True)
        except ValueError as exc:
            if child.name == task_slug:
                raise
            raise _workspace_error(
                "workspace.namespace.project_owned",
                f"Blueprint namespace contains invalid task workspace content: {child}; {exc}",
                "Preserve the existing entry and resolve the namespace conflict explicitly.",
            ) from exc
    return workspace


def _ensure_git_exclude(root: Path, relative_paths: Iterable[str]) -> tuple[Path | None, bool]:
    is_git, exclude = _git_context(root)
    if not is_git or exclude is None:
        return None, False
    paths = tuple(relative_paths)
    if not paths:
        raise _workspace_error(
            "workspace.git.ignore_check",
            "no canonical workspace paths were supplied for ignore validation",
            "Prepare the canonical request and Blueprint paths together.",
        )
    def check_batch() -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", "check-ignore", "--no-index", "--stdin", "-z"],
            cwd=root,
            input="".join(f"{path}\0" for path in paths).encode("utf-8"),
            capture_output=True,
            check=False,
        )

    ignored = check_batch()
    ignored_output = ignored.stdout.decode() if isinstance(ignored.stdout, bytes) else ignored.stdout
    ignored_paths = {value for value in ignored_output.split("\0") if value}
    if ignored.returncode == 0 and ignored_paths == set(paths):
        return exclude, True
    if ignored.returncode not in {0, 1}:
        raise _workspace_error(
            "workspace.git.ignore_check",
            "cannot query the repository ignore boundary",
            "Repair Git ignore metadata before preparing a Blueprint.",
        )
    existing = ""
    if exclude.exists():
        existing = exclude.read_text(encoding="utf-8")
    lines = {line.strip() for line in existing.replace("\r\n", "\n").splitlines()}
    if BLUEPRINT_WORKSPACE_RULE not in lines and f"{BLUEPRINT_WORKSPACE_DIR}/" not in lines:
        separator = "" if not existing or existing.endswith(("\n", "\r")) else "\n"
        _atomic_write_text(exclude, existing + separator + BLUEPRINT_WORKSPACE_RULE + "\n")
    final = check_batch()
    final_output = final.stdout.decode() if isinstance(final.stdout, bytes) else final.stdout
    final_paths = {value for value in final_output.split("\0") if value}
    if final.returncode != 0 or final_paths != set(paths):
        raise _workspace_error(
            "workspace.git.ignore_boundary",
            "the local Git exclude does not cover both canonical workspace files",
            "Repair the repository-local ignore boundary and retry.",
        )
    return exclude, True


def _binding_hash(binding: dict[str, Any]) -> str:
    return _sha256(_canonical_json(binding).encode("utf-8"))


def _base_binding(binding: dict[str, Any]) -> dict[str, Any]:
    """Workspace ownership identity; deliberately excludes git_head.

    Workspace collision and state comparisons bind ``repository_id`` and the
    frozen request bytes only. HEAD movement is unrelated to ownership and
    must never redirect a task to a suffixed workspace; it stays recorded in
    the sealed proof as provenance alone.
    """
    return {key: binding.get(key) for key in ("repository_id", "request_sha256")}


def _binding_shape_valid(binding: dict[str, Any]) -> bool:
    """Strict sealed-proof binding schema.

    Exact key sets with explicit types: repository_id is a non-empty string,
    git_head is null or 40/64-char lowercase hex (provenance only),
    request_sha256 is 64-char lowercase hex, and source_item is a non-empty
    string accepted only with the diagnosis keys.
    """
    keys = set(binding)
    if keys not in (
        {"repository_id", "git_head", "request_sha256"},
        {"repository_id", "git_head", "request_sha256", "source_item"},
    ):
        return False
    repository_id = binding.get("repository_id")
    git_head = binding.get("git_head")
    request_sha256 = binding.get("request_sha256")
    source_item = binding.get("source_item")
    if not isinstance(repository_id, str) or not repository_id:
        return False
    if git_head is not None and (
        not isinstance(git_head, str) or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", git_head) is None
    ):
        return False
    if not isinstance(request_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", request_sha256) is None:
        return False
    if "source_item" in keys and (not isinstance(source_item, str) or not source_item):
        return False
    return True


def _sealed_binding(text: str) -> dict[str, Any] | None:
    proof_matches = list(PROOF_RE.finditer(text))
    validation_matches = list(VALIDATION_RE.finditer(text))
    if len(proof_matches) != 1 or len(validation_matches) != 1:
        return None
    try:
        proof = json.loads(proof_matches[0].group("json"))
    except json.JSONDecodeError:
        return None
    if (
        not isinstance(proof, dict)
        or set(proof) != {"version", "binding", "locations", "sources"}
        or not compatible_version(proof.get("version"), CONTRACT_VERSION)
        or not isinstance(proof.get("locations"), list)
        or not isinstance(proof.get("sources"), list)
    ):
        return None
    binding = proof.get("binding")
    if not isinstance(binding, dict) or not _binding_shape_valid(binding):
        return None
    receipt = validation_matches[0]
    try:
        current_plan = plan_sha256(text)
    except ValueError:
        return None
    if receipt.group("plan") != current_plan or receipt.group("proof") != _sha256(
        _canonical_json(proof).encode("utf-8")
    ):
        return None
    return _base_binding(binding)


def _workspace_binding(root: Path, request_bytes: bytes) -> dict[str, Any]:
    repository_id, _git_head = RepositoryView(root).repository_identity()
    return {"repository_id": repository_id, "request_sha256": _sha256(request_bytes)}


def _candidate_binding(path: Path) -> dict[str, Any] | None:
    if not path.is_file() or path.is_symlink():
        return None
    try:
        return _sealed_binding(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return None


def _workspace_state(
    task_directory: Path,
    binding: dict[str, Any],
    request_bytes: bytes,
) -> str:
    """Classify an existing task directory without repairing any state."""
    _workspace_task_directory(task_directory, require_request=True)
    request_path = task_directory / REQUEST_FILENAME
    existing_request = request_path.read_bytes()
    blueprint_path = task_directory / BLUEPRINT_FILENAME
    candidate = _candidate_binding(blueprint_path) if blueprint_path.exists() else None
    if candidate is not None:
        if candidate.get("request_sha256") != _sha256(existing_request):
            raise _workspace_error(
                "workspace.request.mismatch",
                f"canonical {REQUEST_FILENAME} does not match the sealed Blueprint binding: {request_path}",
                f"Preserve the existing workspace and restore its exact sealed {REQUEST_FILENAME}; do not replace it automatically.",
            )
        return "same" if candidate == binding and existing_request == request_bytes else "foreign"
    if existing_request == request_bytes:
        return "same"
    if blueprint_path.exists():
        raise _workspace_error(
            "workspace.request.ambiguous",
            f"canonical {REQUEST_FILENAME} differs in an unsealed or invalid existing workspace: {request_path}",
            "Preserve the existing Blueprint and request, then retry with the binding that owns this task directory.",
        )
    raise _workspace_error(
        "workspace.request.mismatch",
        f"canonical {REQUEST_FILENAME} differs from the authoritative request: {request_path}",
        "Preserve the existing snapshot and retry with its owning authoritative request; do not repair it automatically.",
    )


def _select_workspace_directory(root: Path, slug: str, binding: dict[str, Any], request_bytes: bytes) -> Path:
    base = root / BLUEPRINT_WORKSPACE_DIR / slug
    if not base.exists():
        return base
    if _workspace_state(base, binding, request_bytes) == "same":
        return base
    digest = _binding_hash(binding)
    for length in (12, 16, 24, 32, 64):
        collision_slug = f"{slug}-{digest[:length]}"
        candidate = root / BLUEPRINT_WORKSPACE_DIR / collision_slug
        if not candidate.exists() or _workspace_state(candidate, binding, request_bytes) == "same":
            return candidate
    raise _workspace_error(
        "workspace.collision.exhausted",
        f"cannot derive a free collision-safe task path for {slug}",
        "Choose a different concise task name after preserving the existing task files.",
    )


def prepare_blueprint_workspace(repo_root: Path, task_name: str, request_file: Path) -> WorkspaceReservation:
    """Reserve one task directory, write the initial Blueprint shell, and the narrow local untracked boundary."""
    root = repo_root.resolve()
    if not root.is_dir():
        raise _workspace_error(
            "workspace.repository.missing",
            f"repository root is not a directory: {root}",
            "Provide an existing repository root.",
        )
    request = request_file.absolute()
    if request.name in RETIRED_HANDOFF_ARTIFACTS:
        raise _request_error(
            "handoff.path.retired", f"Retired handoff artifact filename is not accepted: {request.name}."
        )
    if not request.is_file():
        raise _workspace_error(
            "workspace.request.missing",
            f"request file does not exist: {request}",
            "Provide the exact authoritative request file.",
        )
    request_bytes = request.read_bytes()
    # Validate upstream truth before creating a namespace or freezing any bytes.
    try:
        request_text = request_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _request_error("request.encoding", "Request files must be valid UTF-8.") from exc
    architecture_input = request.name == "architecture.md" or _looks_like_architecture_input(request_text)
    source = detect_request_source(request_bytes, repo_root=root) if architecture_input else {"kind": "generic"}
    if source["kind"] == "architecture" and HANDOFF_RECEIPT_RE.fullmatch(
        request_text.removesuffix("\n").rpartition("\n")[2].rstrip("\r")
    ):
        architecture_handoff = import_module("architecture_handoff")
        read_primary = architecture_handoff.read_primary

        try:
            if request.name == REQUEST_FILENAME:
                canonical_request_path(root, request, require_existing=True)
            elif read_primary(request, root) != request_bytes:
                raise ValueError("architecture source changed while reading")
        except (OSError, ValueError) as exc:
            raise _request_error("handoff.architecture.identity", str(exc)) from exc
    elif request.name == "architecture.md" and source["kind"] != "architecture":
        raise _request_error(
            "handoff.architecture.receipt", "architecture.md requires a verified architecture receipt."
        )
    slug = normalize_task_slug(task_name)
    _ensure_namespace(root, slug)
    binding = _workspace_binding(root, request_bytes)
    task_directory = _select_workspace_directory(root, slug, binding, request_bytes)
    if not task_directory.exists():
        try:
            task_directory.mkdir()
        except FileExistsError:
            pass
    _workspace_task_directory(task_directory, require_request=False)
    request_path = task_directory / REQUEST_FILENAME
    _materialize_request_snapshot(request_path, request_bytes)
    observed = _workspace_task_directory(task_directory, require_request=True)
    request_path = canonical_request_path(root, request_path, require_existing=True)
    blueprint_path = canonical_blueprint_path(root, task_directory / BLUEPRINT_FILENAME)
    _materialize_blueprint_scaffold(blueprint_path, task_name, existed=BLUEPRINT_FILENAME in observed)
    git_exclude, git_ignored = _ensure_git_exclude(
        root,
        (
            request_path.relative_to(root).as_posix(),
            blueprint_path.relative_to(root).as_posix(),
        ),
    )
    return WorkspaceReservation(
        slug,
        request_path,
        blueprint_path,
        request_path.relative_to(root).as_posix(),
        blueprint_path.relative_to(root).as_posix(),
        git_exclude,
        git_ignored,
    )


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _atomic_write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"))


def blueprint_scaffold_text(task_name: str) -> str:
    """Return the fixed initial Blueprint shell for one authorized task name."""
    title = " ".join(task_name.split())
    return "\n".join(
        [
            CONTRACT_MARKER,
            f"# {title}",
            "",
            "## Goal",
            "",
            "## Current State",
            "",
            "## Implementation",
            "",
            "## Verification",
            "",
            "### After implementation",
            "",
            "## Completion Conditions",
        ]
    ) + "\n"


def _materialize_blueprint_scaffold(path: Path, task_name: str, *, existed: bool) -> None:
    """Create the canonical Blueprint shell once for a caller that validated the workspace boundary.

    ``existed`` carries the boundary observation: True means the validated
    workspace pass already saw a regular non-symlink Blueprint file, which is
    agent-owned and preserved without inspection; materialization re-checks
    that the same path is still a regular non-symlink file and fails closed
    with ``workspace.blueprint.concurrent`` when it disappeared or became
    unsafe after validation. False means the validated pass saw the path
    absent, so any occupancy at entry or during the create attempt appeared
    after that boundary and must be a regular file holding exactly the
    scaffold bytes, or preparation fails closed with
    ``workspace.blueprint.concurrent``.
    """
    scaffold_bytes = blueprint_scaffold_text(task_name).encode("utf-8")
    if existed:
        if path.is_symlink() or not path.is_file():
            raise _workspace_error(
                "workspace.blueprint.concurrent",
                f"canonical {BLUEPRINT_FILENAME} disappeared or became unsafe after workspace validation: {path}",
                "Preserve the concurrent workspace and retry after resolving ownership.",
            )
        return
    if path.is_symlink():
        raise _workspace_error(
            "workspace.blueprint.concurrent",
            f"canonical {BLUEPRINT_FILENAME} appeared as a symlink: {path}",
            "Preserve the concurrent workspace and retry after resolving ownership.",
        )
    if path.exists():
        raise _workspace_error(
            "workspace.blueprint.concurrent",
            f"canonical {BLUEPRINT_FILENAME} appeared before creation: {path}",
            "Preserve the concurrent workspace and retry after resolving ownership.",
        )
    try:
        stream = path.open("xb")
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != scaffold_bytes:
            raise _workspace_error(
                "workspace.blueprint.concurrent",
                f"canonical {BLUEPRINT_FILENAME} appeared with different or unsafe contents: {path}",
                "Preserve the concurrent workspace and retry after resolving ownership.",
            )
        return
    except (IsADirectoryError, PermissionError):
        raise _workspace_error(
            "workspace.blueprint.concurrent",
            f"canonical {BLUEPRINT_FILENAME} appeared with unsafe contents: {path}",
            "Preserve the concurrent workspace and retry after resolving ownership.",
        )
    try:
        with stream:
            stream.write(scaffold_bytes)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _materialize_request_snapshot(path: Path, request_bytes: bytes) -> None:
    """Create the canonical request once, never replace an existing snapshot."""
    if path.is_symlink():
        raise _workspace_error(
            "workspace.request.symlink",
            f"canonical {REQUEST_FILENAME} is a symlink: {path}",
            "Replace the symlink with the exact canonical request snapshot.",
        )
    if path.exists():
        if not path.is_file():
            raise _workspace_error(
                "workspace.request.unsafe",
                f"canonical {REQUEST_FILENAME} is not a regular file: {path}",
                "Preserve the existing workspace and restore a regular request snapshot.",
            )
        if path.read_bytes() != request_bytes:
            raise _workspace_error(
                "workspace.request.mismatch",
                f"canonical {REQUEST_FILENAME} does not match the authoritative request: {path}",
                "Preserve the existing snapshot and retry with its owning authoritative request.",
            )
        return
    try:
        with path.open("xb") as stream:
            stream.write(request_bytes)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != request_bytes:
            raise _workspace_error(
                "workspace.request.concurrent",
                f"canonical {REQUEST_FILENAME} appeared with different or unsafe contents: {path}",
                "Preserve the concurrent workspace and retry after resolving ownership.",
            )


def replace_canonical_blueprint(
    repo_root: Path, draft_file: Path, text: str, *, expected_sha256: str | None = None
) -> Path:
    """Atomically replace the canonical Blueprint after an expected-byte check."""
    path = canonical_blueprint_path(repo_root, draft_file, require_existing=True)
    _workspace_task_directory(path.parent, require_request=True)
    before = path.read_bytes()
    if expected_sha256 is not None and _sha256(before) != expected_sha256:
        raise _workspace_error(
            "workspace.concurrent_change",
            f"Blueprint draft changed during sealing: {path}",
            "Re-read the draft and retry without overwriting the concurrent change.",
        )
    _atomic_write_text(path, text)
    return path


def _error(
    code: str,
    message: str,
    action: str,
    *,
    path: str | None = None,
    line: int | None = None,
    category: str = "malformed_input",
) -> Diagnostic:
    return Diagnostic(code, message, action, path=path, line=line, category=category)


def _substantive(value: str) -> bool:
    normalized = " ".join(value.split()).strip()
    return bool(normalized) and not _is_template_sentinel(normalized)


def _is_template_sentinel(value: str) -> bool:
    normalized = " ".join(value.split()).strip()
    return bool(TEMPLATE_SENTINEL_RE.fullmatch(normalized))


def _section_spans(
    lines: list[str], fenced: set[int]
) -> tuple[list[str], dict[str, tuple[int, int]], list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    headings: list[tuple[str, int]] = []
    for index, raw in enumerate(lines):
        if index in fenced:
            continue
        match = TOP_LEVEL_HEADING_RE.fullmatch(raw)
        if match:
            headings.append((match.group("name").strip(), index))
    if not headings or headings[0][1] < 2:
        diagnostics.append(
            _error(
                "shape.title",
                "The contract marker must be followed by the H1 title and the contract sections.",
                f"Put '{CONTRACT_MARKER}' on line 1, '# <Task>' as the next line, then the sections.",
            )
        )
        return [], {}, diagnostics
    names = [name for name, _index in headings]
    if len(names) != len(set(names)):
        diagnostics.append(
            _error(
                "shape.heading.duplicate",
                "A top-level Blueprint heading appears more than once.",
                "Keep each contract heading exactly once.",
            )
        )
    allowed = set(REQUIRED_SECTIONS) | set(OPTIONAL_SECTIONS)
    unknown = [name for name in names if name not in allowed]
    if unknown:
        diagnostics.append(
            _error(
                "shape.heading.unsupported",
                f"Unsupported top-level heading: {unknown[0]!r}.",
                "Use the plain implementation-complete Blueprint headings from the current contract.",
            )
        )
    required_present = [name for name in REQUIRED_SECTIONS if name not in names]
    if required_present:
        diagnostics.append(
            _error(
                "shape.heading.missing",
                f"Required heading {required_present[0]!r} is missing.",
                f"Add '## {required_present[0]}'.",
            )
        )
    expected_prefix = [name for name in SECTION_ORDER if name in names]
    if names != expected_prefix:
        diagnostics.append(
            _error(
                "shape.heading.order",
                "Blueprint headings are not in the required order.",
                "Order headings as Goal, Current State, Implementation, Verification, Completion Conditions, and Risks / Recovery.",
            )
        )
    spans: dict[str, tuple[int, int]] = {}
    for position, (name, start) in enumerate(headings):
        end = headings[position + 1][1] if position + 1 < len(headings) else len(lines)
        spans[name] = (start + 1, end)
        content = [line for line in lines[start + 1 : end] if line.strip()]
        if not content:
            diagnostics.append(
                _error(
                    "shape.section.empty",
                    f"Section {name!r} is empty.",
                    f"Add the decision-useful content required by '## {name}'.",
                    line=start + 1,
                )
            )
    return names, spans, diagnostics


def _is_mutating_git_argv(argv: tuple[str, ...]) -> bool:
    executable = Path(argv[0]).name.casefold()
    if executable not in {"git", "git.exe"}:
        return False
    index = 1
    options_with_values = {"-c", "-C", "--git-dir", "--work-tree", "--namespace"}
    while index < len(argv) and argv[index].startswith("-"):
        option = argv[index]
        index += 1
        if option in options_with_values and index < len(argv):
            index += 1
    return index < len(argv) and argv[index].casefold() in MUTATING_GIT_COMMANDS


def _invokes_shell_interpreter(argv: tuple[str, ...]) -> bool:
    executable = Path(argv[0]).name.casefold()
    if executable not in SHELL_EXECUTABLES:
        return False
    options = [token.casefold() for token in argv[1:]]
    if executable in {"cmd", "cmd.exe"}:
        return any(option in {"/c", "/k"} or option.startswith("/c") for option in options)
    if executable in {"powershell", "powershell.exe", "pwsh"}:
        return any(
            option in {"-e", "-ec"}
            or len(option) >= 2
            and ("-command".startswith(option) or "-encodedcommand".startswith(option))
            for option in options
        )
    # POSIX shells: any short-option bundle carrying the command-mode flag
    # (for example -c, -lc, or -ec) or its direct long command form invokes
    # the shell, so a Run remains one directly executable argv command.
    return any(
        option.startswith("-") and not option.startswith("--") and "c" in option[1:]
        or option == "--command"
        for option in options
    )


def _fenced_indexes(lines: list[str]) -> set[int]:
    """Return line indexes on or inside fenced code blocks.

    Structural-looking text inside fenced code is inert: headings and
    declaration lines there never alter parsing. Generated receipt markers
    are deliberately excluded from this carve-out and stay reserved in every
    byte of the document. A closing fence must be a same-character run at
    least as long as the opener and followed only by whitespace, so an inner
    three-backtick example never terminates a four-backtick outer fence.
    """
    fenced: set[int] = set()
    closer: tuple[str, int] | None = None
    for index, raw in enumerate(lines):
        stripped = raw.lstrip()
        if closer is None:
            match = re.match(r"(`{3,}|~{3,})", stripped)
            if match:
                opener = match.group(1)
                closer = (opener[0], len(opener))
                fenced.add(index)
        else:
            fenced.add(index)
            char, run = closer
            if re.fullmatch(rf"{re.escape(char)}{{{run},}}[ \t]*", stripped):
                closer = None
    return fenced


def _strict_span(value: str) -> str | None:
    """Return one declaration value that is exactly one backticked span.

    The entire text after the declaration label must be the code span; any
    surrounding prose, a second span, or an empty label fails so a plan can
    never bind different bytes than the author appears to declare.
    """
    match = STRICT_SPAN_RE.fullmatch(value)
    return match.group("content") if match is not None else None


def _location_token(token: str, line: int, state: str) -> TargetLocation | None:
    """Parse one Location span content literally: `path` or `path::symbol`.

    Range suffixes are Location-invalid, and the content is never punctuation-
    stripped: a malformed path fails at resolution instead of silently binding
    a different file.
    """
    value = token
    if not value or _is_template_sentinel(value):
        return None
    if LOCATOR_SUFFIX_RE.search(value) or LOCATOR_SUFFIX_LIKE_RE.search(value):
        return None
    match = SYMBOL_SUFFIX_RE.search(value)
    if match:
        symbol = match.group("symbol")
        path = value[: match.start()]
    else:
        symbol = None
        path = value
    if not path:
        return None
    return TargetLocation(path.replace("\\", "/"), symbol, state, line)


def _source_token(token: str, line: int) -> SourceLocator | None:
    """Parse one Source span content literally: `path` or `path` plus a line range.

    `::symbol` cannot be mechanically established for a cited source and is
    never recorded in the receipt, so it fails closed here; symbol context
    belongs on executor-facing Location lines. Punctuation inside the span is
    never stripped, so a malformed path fails at resolution.
    """
    value = token
    if not value or _is_template_sentinel(value):
        return None
    if SYMBOL_SUFFIX_RE.search(value):
        return None
    match = LOCATOR_SUFFIX_RE.search(value)
    if match:
        path = value[: match.start()]
        start = match.group("start") or match.group("hash_start")
        end = match.group("end") or match.group("hash_end") or start
    else:
        if LOCATOR_SUFFIX_LIKE_RE.search(value):
            return None
        path = value
        start = end = None
    if not path:
        return None
    return SourceLocator(path.replace("\\", "/"), int(start) if start else None, int(end) if end else None, line)


def _collect_sources(
    lines: list[str],
    spans: dict[str, tuple[int, int]],
    fenced: set[int],
    diagnostics: list[Diagnostic],
) -> tuple[SourceLocator, ...]:
    """Bind author-declared decision-critical sources from Current State only."""
    sources: list[SourceLocator] = []
    if "Current State" not in spans:
        return ()
    start, end = spans["Current State"]
    for index, raw in enumerate(lines[start:end], start=start):
        if index in fenced:
            continue
        match = SOURCE_RE.match(raw)
        if match is None:
            continue
        span = _strict_span(raw[match.end() :])
        if span is None:
            diagnostics.append(
                _error(
                    "source.locator.shape",
                    "A Source line must cite exactly one backticked repository-relative path with no surrounding text.",
                    "Write **Source:** `path/to/file.py` (optionally `path/to/file.py:12-18`).",
                    line=index + 1,
                )
            )
            continue
        locator = _source_token(span, index + 1)
        if locator is None:
            diagnostics.append(
                _error(
                    "source.locator.shape",
                    f"Declared source {span!r} has an invalid path, symbol, or line-range suffix.",
                    "Use `path/to/file.py` or `path/to/file.py:12-18`; `::symbol` belongs on Location lines.",
                    line=index + 1,
                )
            )
            continue
        sources.append(locator)
    return tuple(sources)


def _parse_verification_command(
    span: str,
    *,
    phase: str,
    line: int,
    diagnostics: list[Diagnostic],
) -> tuple[tuple[str, ...], int] | None:
    try:
        argv = tuple(shlex.split(span, posix=True))
    except ValueError:
        argv = ()
    if not argv:
        diagnostics.append(
            _error(
                "verification.run.shape",
                "Run command is empty or not a valid command line.",
                "Provide the exact executable and arguments from the repository root.",
                line=line,
            )
        )
        return None
    if any(_is_template_sentinel(token) or EMBEDDED_PLACEHOLDER_RE.search(token) for token in argv):
        diagnostics.append(
            _error(
                "verification.argv.placeholder",
                "Run command contains a placeholder token.",
                "Replace the placeholder with the exact executable or argument.",
                line=line,
            )
        )
        return None
    if any(token.strip() in SHELL_CHAIN_TOKENS or "\n" in token or "\r" in token for token in argv):
        diagnostics.append(
            _error(
                "verification.argv.chained",
                "Run command contains shell chaining syntax.",
                "Declare each check as its own Run line or invoke one repository-owned script.",
                line=line,
            )
        )
        return None
    if _invokes_shell_interpreter(argv):
        diagnostics.append(
            _error(
                "verification.argv.shell",
                "Run command invokes a shell command interpreter.",
                "Declare separate Run lines or invoke one repository-owned runner without a shell command mode.",
                line=line,
                category="contract_contradiction",
            )
        )
        return None
    if _is_mutating_git_argv(argv):
        diagnostics.append(
            _error(
                "verification.git.mutation",
                "Run command invokes a known repository-mutating Git command.",
                "Keep index, worktree, HEAD, and publication mutations outside verification.",
                line=line,
                category="contract_contradiction",
            )
        )
        return None
    return argv, line


def _exit_claim_is_negated(value: str, qualifier_start: int) -> bool:
    """Return whether a negator governs the claim within its own clause."""
    clause_start = 0
    for boundary in EXIT_CLAUSE_BOUNDARY_RE.finditer(value, 0, qualifier_start):
        clause_start = boundary.end()
    return EXIT_NEGATION_RE.search(value[clause_start:qualifier_start]) is not None


def _admits_nonzero_exit(value: str) -> str | None:
    """Return an explicit nonzero process-status claim, or None.

    Mechanical recognition is deliberately narrow. Numeric values require an
    exit or return-code/status noun; comparative and failure qualifiers require
    an exit/status noun; and a qualifier is negated only by its own clause.
    Data-return values, counts, unrelated adjectives, and nounless failure
    paraphrases remain challenge and rehearsal obligations.
    """
    for match in EXIT_NUMERIC_STATUS_RE.finditer(value):
        if int(match.group("value")) != 0 and not _exit_claim_is_negated(
            value, match.start("value")
        ):
            return f"claimed exit {match.group('value')}"
    for pattern in (
        EXIT_RELATIONAL_STATUS_RE,
        EXIT_QUALIFIER_BEFORE_STATUS_RE,
        EXIT_QUALIFIER_AFTER_STATUS_RE,
    ):
        for match in pattern.finditer(value):
            if not _exit_claim_is_negated(value, match.start("qualifier")):
                return f"claimed {match.group(0).strip()}"
    return None


def _parse_verification(
    lines: list[str],
    *,
    start: int,
    end: int,
    fenced: set[int],
    diagnostics: list[Diagnostic],
) -> tuple[VerificationStep, ...]:
    steps: list[VerificationStep] = []
    phase = ""
    seen: list[str] = []
    pending: dict[str, Any] | None = None

    def finish_pending(*, nested_line: int) -> None:
        nonlocal pending
        if pending is None:
            return
        if not pending["expect"]:
            diagnostics.append(
                _error(
                    "verification.expect.missing",
                    "The previous Run line has no observable Expect.",
                    "Add the exact observable result or measurable threshold for that Run.",
                    line=nested_line,
                )
            )
        pending = None

    for index, raw in enumerate(lines[start:end], start=start):
        if index in fenced:
            continue
        heading = H3_HEADING_RE.fullmatch(raw)
        if heading:
            finish_pending(nested_line=index + 1)
            name = heading.group("name").strip()
            if name not in VERIFICATION_PHASES:
                diagnostics.append(
                    _error(
                        "verification.heading.unsupported",
                        f"Unsupported Verification subsection {name!r}.",
                        "Use only '### Before implementation' and '### After implementation'.",
                        line=index + 1,
                    )
                )
            elif name in seen:
                diagnostics.append(
                    _error(
                        "verification.heading.duplicate",
                        f"Verification subsection {name!r} appears more than once.",
                        "Keep each verification phase exactly once.",
                        line=index + 1,
                    )
                )
            else:
                seen.append(name)
                phase = name
            continue
        run_like = RUN_LIKE_RE.match(raw)
        if run_like:
            finish_pending(nested_line=index + 1)
            if steps and steps[-1].incomplete is not None and steps[-1].phase == phase:
                diagnostics.append(
                    _error(
                        "verification.incomplete.not_last",
                        "A Run with an Incomplete outcome must be the last Run in its phase.",
                        "Move the Run that declares Incomplete after every other After implementation Run.",
                        line=index + 1,
                    )
                )
            if phase not in VERIFICATION_PHASES:
                diagnostics.append(
                    _error(
                        "verification.phase.missing",
                        "A Run line must appear under a verification phase heading.",
                        "Place it under '### Before implementation' or '### After implementation'.",
                        line=index + 1,
                    )
                )
                continue
            span = _strict_span(raw[run_like.end() :])
            if span is None:
                diagnostics.append(
                    _error(
                        "verification.run.shape",
                        "Each Run line must hold exactly one backticked command with no surrounding text.",
                        "Write one command per Run line so the executor can run it directly.",
                        line=index + 1,
                    )
                )
                continue
            parsed = _parse_verification_command(span, phase=phase, line=index + 1, diagnostics=diagnostics)
            if parsed is not None:
                pending = {"argv": parsed[0], "line": index + 1, "timeout": None, "expect": False, "incomplete": False}
            continue
        timeout_like = TIMEOUT_LIKE_RE.match(raw)
        if timeout_like:
            if pending is None or pending["expect"]:
                diagnostics.append(
                    _error(
                        "verification.timeout.orphan",
                        "A Timeout line must follow its Run line and precede its Expect.",
                        "Place Timeout between the Run it bounds and that Run's Expect.",
                        line=index + 1,
                    )
                )
            elif pending["timeout"] is not None:
                diagnostics.append(
                    _error(
                        "verification.timeout.duplicate",
                        "A Run line has more than one Timeout.",
                        "Keep one positive Timeout per Run.",
                        line=index + 1,
                    )
                )
            else:
                value_match = TIMEOUT_VALUE_RE.fullmatch(raw[timeout_like.end() :].strip())
                seconds = int(value_match.group("value")) if value_match else 0
                if value_match is None or seconds <= 0:
                    diagnostics.append(
                        _error(
                            "verification.timeout.shape",
                            "Timeout must be a positive whole number of seconds.",
                            "Set Timeout to a positive integer.",
                            line=index + 1,
                        )
                    )
                else:
                    pending["timeout"] = seconds
            continue
        expect_like = EXPECT_LIKE_RE.match(raw)
        if expect_like:
            if pending is None or pending["expect"]:
                diagnostics.append(
                    _error(
                        "verification.expect.orphan",
                        "An Expect line must follow exactly one Run line.",
                        "Keep one observable Expect per Run.",
                        line=index + 1,
                    )
                )
            elif not _substantive(raw[expect_like.end() :]):
                diagnostics.append(
                    _error(
                        "verification.expect.placeholder",
                        "Expect contains a placeholder rather than an observable result.",
                        "State the exact observable result or measurable threshold.",
                        line=index + 1,
                    )
                )
            else:
                claimed = _admits_nonzero_exit(raw[expect_like.end() :])
                if claimed is not None:
                    diagnostics.append(
                        _error(
                            "verification.expect.nonzero_exit",
                            f"Run line {pending['line']} expects a nonzero exit ({claimed}); the "
                            "executor fails closed on any nonzero authored Run and has no "
                            "expected-failure mode, so this Expect makes the sealed plan "
                            "unexecutable.",
                            "Every authored Run must exit 0 on a correct implementation. Record the "
                            "pre-change observation as cited evidence in Current State, require exit "
                            "0 here, and express a conditional outcome as an observable output value "
                            "the Run reports while still exiting 0.",
                            line=pending["line"],
                            category="contract_contradiction",
                        )
                    )
                steps.append(
                    VerificationStep(
                        pending["argv"],
                        pending["timeout"] or DEFAULT_VERIFICATION_TIMEOUT_SECONDS,
                        phase,
                        pending["line"],
                    )
                )
                pending["expect"] = True
            continue
        incomplete_like = INCOMPLETE_LIKE_RE.match(raw)
        if incomplete_like:
            declared = raw[incomplete_like.end() :].strip()
            if pending is None or not pending["expect"]:
                diagnostics.append(
                    _error(
                        "verification.incomplete.orphan",
                        "An Incomplete line must follow its Run's Expect.",
                        "Place Incomplete directly after the Expect of the Run whose environmental incomplete outcome it names.",
                        line=index + 1,
                    )
                )
            elif phase != "After implementation":
                diagnostics.append(
                    _error(
                        "verification.incomplete.before",
                        "An Incomplete outcome is accepted only on an After implementation Run.",
                        "Remove it from the baseline Run, or move that check under '### After implementation'.",
                        line=index + 1,
                    )
                )
            elif pending["incomplete"]:
                diagnostics.append(
                    _error(
                        "verification.incomplete.duplicate",
                        "A Run line has more than one Incomplete outcome.",
                        "Keep one Incomplete line per Run.",
                        line=index + 1,
                    )
                )
            elif not _substantive(declared):
                diagnostics.append(
                    _error(
                        "verification.incomplete.placeholder",
                        "Incomplete must name the observable environmental incomplete outcome.",
                        "State the output signature, such as the final record reporting complete false.",
                        line=index + 1,
                    )
                )
            else:
                steps[-1] = dataclasses.replace(steps[-1], incomplete=declared)
                pending["incomplete"] = True
            continue
    finish_pending(nested_line=end)
    return tuple(steps)


def _step_headings(
    lines: list[str],
    *,
    start: int,
    end: int,
    fenced: set[int],
    diagnostics: list[Diagnostic],
) -> list[tuple[int, re.Match[str]]]:
    headings: list[tuple[int, re.Match[str]]] = []
    for index, raw in enumerate(lines[start:end], start=start):
        if index in fenced:
            continue
        h3 = H3_HEADING_RE.fullmatch(raw)
        if not h3:
            continue
        step_match = STEP_HEADING_RE.fullmatch(raw)
        if step_match is None:
            diagnostics.append(
                _error(
                    "step.heading.unsupported",
                    f"Unsupported Implementation subsection {h3.group('name').strip()!r}.",
                    "Name each implementation instruction '### 1. <concrete change>'.",
                    line=index + 1,
                )
            )
            continue
        headings.append((index, step_match))
    return headings


def _parse_step_declarations(
    body_lines: list[str],
    heading_index: int,
    step_number: int,
    fenced: set[int],
    diagnostics: list[Diagnostic],
) -> list[TargetLocation]:
    """Bind each Location with the State line that immediately follows it."""
    locations: list[TargetLocation] = []
    pending: TargetLocation | None = None
    for offset, raw in enumerate(body_lines):
        absolute = heading_index + 1 + offset
        if pending is not None and raw.strip():
            # State must be the next non-empty raw line, fenced code included:
            # an intervening fenced block cannot hide the missing State.
            if absolute not in fenced:
                state_match = STATE_RE.fullmatch(raw)
                if state_match is not None:
                    locations.append(
                        TargetLocation(pending.path, pending.symbol, state_match.group("value"), pending.line)
                    )
                    pending = None
                    continue
                if STATE_LIKE_RE.match(raw):
                    diagnostics.append(
                        _error(
                            "state.unsupported",
                            f"Instruction {step_number} declares a State value that is not 'existing', 'new', or 'deleted'.",
                            "Write exactly **State:** existing, **State:** new, or **State:** deleted after the Location line.",
                            line=absolute + 1,
                        )
                    )
                    pending = None
                    continue
            diagnostics.append(
                _error(
                    "location.state.missing",
                    f"Instruction {step_number} Location must declare its target state on the next non-empty line.",
                    "Add **State:** existing, **State:** new, or **State:** deleted on the line after the Location.",
                    line=absolute + 1,
                )
            )
            pending = None
            # Fall through: the line itself may be the next declaration.
        if absolute in fenced:
            continue
        location_match = LOCATION_RE.match(raw)
        if location_match is not None:
            span = _strict_span(raw[location_match.end() :])
            if span is None:
                diagnostics.append(
                    _error(
                        "location.locator.shape",
                        f"Instruction {step_number} Location must cite exactly one backticked target path with no surrounding text.",
                        "Write **Location:** `path/to/file.py::symbol` (one path per line).",
                        line=absolute + 1,
                    )
                )
                continue
            locator = _location_token(span, absolute + 1, "")
            if locator is None:
                diagnostics.append(
                    _error(
                        "location.locator.shape",
                        f"Instruction {step_number} Location {span!r} has an invalid path; line-range suffixes are not Location syntax.",
                        "Use `path/to/file.py` or `path/to/file.py::symbol`.",
                        line=absolute + 1,
                    )
                )
                continue
            pending = locator
            continue
        if pending is None and STATE_LIKE_RE.match(raw):
            diagnostics.append(
                _error(
                    "state.orphan",
                    f"Instruction {step_number} has a State line that does not follow a Location.",
                    "Write **State:** immediately after the Location it declares.",
                    line=absolute + 1,
                )
            )
    if pending is not None:
        diagnostics.append(
            _error(
                "location.state.missing",
                f"Instruction {step_number} Location must declare its target state on the next non-empty line.",
                "Add **State:** existing, **State:** new, or **State:** deleted on the line after the Location.",
                line=pending.line,
            )
        )
    return locations


def _declared_fence_diagnostics(lines: list[str]) -> list[Diagnostic]:
    """Reject ambiguous declaration structure before global fence masking hides it."""
    diagnostics: list[Diagnostic] = []
    active: tuple[str, int, int, bool] | None = None
    previous = ""
    heading: int | None = None
    for index, raw in enumerate(lines):
        if active is None:
            opener = FENCE_OPEN_RE.match(raw.lstrip())
            if opener is not None:
                fence = opener.group("fence")
                declared = bool(BLOCK_LABEL_RE.match(previous) or WITH_LABEL_RE.match(previous))
                active = (fence[0], len(fence), index, declared)
                heading = None
        else:
            char, length, opening, declared = active
            if re.fullmatch(rf"{re.escape(char)}{{{length},}}[ \t]*", raw.lstrip()):
                active = None
                heading = None
            elif declared:
                ambiguous = False
                if STEP_HEADING_RE.fullmatch(raw):
                    heading = index
                if heading is not None and LOCATION_RE.match(raw):
                    following = _next_nonempty(lines, index, len(lines))
                    ambiguous = following is not None and STATE_RE.fullmatch(lines[following]) is not None
                if BLOCK_LABEL_RE.match(raw) or WITH_LABEL_RE.match(raw):
                    following = _next_nonempty(lines, index, len(lines))
                    nested = FENCE_OPEN_RE.match(lines[following]) if following is not None else None
                    if nested is not None:
                        fence = nested.group("fence")
                        ambiguous |= fence[0] == char and len(fence) >= length
                if ambiguous:
                    diagnostics.append(_error(
                        "block.shape",
                        f"Declared fence on line {opening + 1} contains an instruction or declaration boundary on line {index + 1}; its closer is ambiguous.",
                        "Close the declared block before the next instruction or declaration; keep literal nested fence examples shorter than their outer fence.",
                        line=index + 1,
                    ))
        if raw.strip():
            previous = raw
    return diagnostics


def _fenced_block(lines: list[str], index: int, stop: int) -> tuple[str, int] | None:
    """Return the text of the unindented fence opening at ``index`` and its closer index."""
    opener = FENCE_OPEN_RE.match(lines[index])
    if opener is None:
        return None
    fence = opener.group("fence")
    closer_re = re.compile(rf"{re.escape(fence[0])}{{{len(fence)},}}[ \t]*")
    for closer in range(index + 1, stop):
        if closer_re.fullmatch(lines[closer]):
            return "".join(line + "\n" for line in lines[index + 1 : closer]), closer
    return None


def _next_nonempty(lines: list[str], index: int, stop: int) -> int | None:
    return next((item for item in range(index + 1, stop) if lines[item].strip()), None)


def _parse_step_proof(
    lines: list[str],
    start: int,
    stop: int,
    step_number: int,
    locations: list[TargetLocation],
    fenced: set[int],
    diagnostics: list[Diagnostic],
) -> tuple[tuple[TextBlock, ...], VerificationStep | None, str | None]:
    """Bind a step's Exact/Frozen blocks to its own Locations and parse its Proof run."""
    blocks: list[TextBlock] = []
    proof: VerificationStep | None = None
    red: str | None = None
    states = {location.path: location.state for location in locations}
    consumed: set[int] = set()

    def block_error(code: str, message: str, action: str, index: int) -> None:
        diagnostics.append(_error(code, f"Instruction {step_number}: {message}", action, line=index + 1))

    def fence_after(index: int) -> tuple[str, int] | None:
        found = _next_nonempty(lines, index, stop)
        return _fenced_block(lines, found, stop) if found is not None else None

    for index in range(start, stop):
        if index in fenced or index in consumed:
            continue
        raw = lines[index]
        label = BLOCK_LABEL_RE.match(raw)
        if label is not None:
            kind = label.group("kind").lower()
            span = _strict_span(raw[label.end() :])
            path = span.replace("\\", "/") if span else None
            if path is None or path not in states:
                block_error(
                    "block.location",
                    f"the {kind.title()} label must cite one backticked path declared by a Location of the same instruction.",
                    "Write **Exact:** `path` or **Frozen:** `path` naming one of this instruction's Location paths.",
                    index,
                )
                continue
            if states[path] == "deleted":
                block_error(
                    "block.deleted",
                    f"declared text cannot target the planned-deleted file {path!r}.",
                    "Drop this block; a deleted target takes no Exact or Frozen text.",
                    index,
                )
                continue
            first = fence_after(index)
            if first is None:
                block_error(
                    "block.shape",
                    f"the {kind.title()} label must be followed by one closed, unindented fenced block.",
                    "Put the exact lines in a ``` or ~~~ fence starting at column 0 right after the label.",
                    index,
                )
                continue
            text, closer = first
            old: str | None = None
            with_index = _next_nonempty(lines, closer, stop)
            with_match = WITH_LABEL_RE.match(lines[with_index]) if with_index is not None and with_index not in fenced else None
            if with_index is not None and with_match is not None:
                consumed.add(with_index)
                second = fence_after(with_index)
                if lines[with_index][with_match.end() :].strip() or second is None:
                    block_error(
                        "block.shape",
                        "**With:** must stand alone and be followed by one closed, unindented fenced block.",
                        "Put the replacement lines in a fence starting at column 0 right after **With:**.",
                        with_index,
                    )
                    continue
                old, text = text, second[0]
                if states[path] != "existing":
                    block_error(
                        "block.replace_new",
                        f"a replacement cannot target the planned-new file {path!r}.",
                        "Give a new file's whole content as one fenced block.",
                        index,
                    )
                    continue
                if not old.strip():
                    block_error("block.empty", "the replaced text is empty.", "Quote the whole existing lines being replaced.", index)
                    continue
                if not text.strip():
                    block_error(
                        "block.empty",
                        "the replacement text is empty.",
                        "Express a deletion by keeping an unchanged neighbouring line in both blocks.",
                        index,
                    )
                    continue
            elif not text.strip():
                block_error("block.empty", f"the {kind.title()} block is empty.", "Put the exact planned lines inside the fence.", index)
                continue
            elif states[path] != "new":
                block_error(
                    "block.whole_existing",
                    f"a whole-file block cannot target the existing file {path!r}.",
                    "Use a replacement; to rewrite the whole file, quote its full current content as the replaced text.",
                    index,
                )
                continue
            blocks.append(TextBlock(kind, path, text, index + 1, old))
            continue
        if WITH_LABEL_RE.match(raw):
            block_error(
                "block.shape",
                "**With:** must follow the fenced text an Exact or Frozen label replaces.",
                "Place **With:** directly after the replaced block.",
                index,
            )
            continue
        proof_label = PROOF_LABEL_RE.match(raw)
        if proof_label is None:
            continue
        if proof is not None:
            block_error("proof.duplicate", "more than one Proof run is declared.", "Keep one Proof run per instruction.", index)
            cursor = index
            while (following := _next_nonempty(lines, cursor, stop)) is not None and following not in fenced:
                if not (TIMEOUT_LIKE_RE.match(lines[following]) or RED_LIKE_RE.match(lines[following]) or EXPECT_LIKE_RE.match(lines[following])):
                    break
                consumed.add(following)
                cursor = following
            continue
        span = _strict_span(raw[proof_label.end() :])
        if span is None:
            block_error(
                "proof.shape",
                "the Proof run must hold exactly one backticked command with no surrounding text.",
                "Write **Proof run:** `command` for the check that decides this instruction.",
                index,
            )
            continue
        phase = f"Instruction {step_number}"
        parsed = _parse_verification_command(span, phase=phase, line=index + 1, diagnostics=diagnostics)
        timeout = DEFAULT_VERIFICATION_TIMEOUT_SECONDS
        expect: str | None = None
        seen_timeout = seen_red = False
        cursor = index
        while True:
            following = _next_nonempty(lines, cursor, stop)
            if following is None or following in fenced:
                break
            line_text = lines[following]
            timeout_like = TIMEOUT_LIKE_RE.match(line_text)
            red_like = RED_LIKE_RE.match(line_text)
            expect_like = EXPECT_LIKE_RE.match(line_text)
            if (timeout_like and seen_timeout) or (red_like and seen_red):
                block_error(
                    "proof.duplicate",
                    "a Proof run chain repeats a Timeout or Red line, so the earlier one would be silently overridden.",
                    "Keep at most one Timeout and one Red, each before Expect.",
                    following,
                )
            elif timeout_like:
                seen_timeout = True
                value_match = TIMEOUT_VALUE_RE.fullmatch(line_text[timeout_like.end() :].strip())
                if value_match is None or int(value_match.group("value")) <= 0:
                    block_error(
                        "verification.timeout.shape",
                        "Timeout must be a positive whole number of seconds.",
                        "Set Timeout to a positive integer.",
                        following,
                    )
                else:
                    timeout = int(value_match.group("value"))
            elif red_like:
                seen_red = True
                red = line_text[red_like.end() :].strip()
                if not _substantive(red):
                    block_error(
                        "proof.red.placeholder",
                        "Red must name the defect the regression shows before the change.",
                        "Name the wrong behavior the current source produces, not how its failure surfaces.",
                        following,
                    )
            elif expect_like:
                expect = line_text[expect_like.end() :]
            else:
                break
            consumed.add(following)
            cursor = following
            if expect is not None:
                break
        if expect is None or not _substantive(expect):
            block_error(
                "proof.expect.missing",
                "the Proof run needs an observable Expect after its optional Timeout and Red lines.",
                "Add Expect: with the exact passing result.",
                index,
            )
            continue
        claimed = _admits_nonzero_exit(expect)
        if claimed is not None:
            block_error(
                "verification.expect.nonzero_exit",
                f"the Proof run Expect admits a nonzero exit ({claimed}); a Proof run passes only on exit 0.",
                "State the passing result; name the defect the regression shows on a Red line instead.",
                index,
            )
            continue
        if parsed is not None:
            proof = VerificationStep(parsed[0], timeout, phase, index + 1)
    for index in range(start, stop):
        if index in fenced or index in consumed:
            continue
        stray = RED_LIKE_RE.match(lines[index]) or (
            proof is not None and (EXPECT_LIKE_RE.match(lines[index]) or TIMEOUT_LIKE_RE.match(lines[index]))
        )
        if stray:
            block_error(
                "proof.displaced",
                "a Red, Expect, or Timeout line is not bound to the Proof run chain, so it would be ignored.",
                "Place Timeout, Red, and Expect directly after **Proof run:**, each at most once, before Expect.",
                index,
            )
    if proof is None and any(block.kind == "frozen" for block in blocks):
        block_error(
            "frozen.proof_missing",
            "Frozen proof needs a Proof run in the same instruction.",
            "Add **Proof run:** `command` that runs this instruction's frozen proof.",
            start - 1,
        )
    return tuple(blocks), proof, red


def line_start_offsets(text: str, fragment: str) -> list[int]:
    """Return every offset where ``fragment`` occurs starting at a line boundary."""
    offsets: list[int] = []
    position = text.find(fragment)
    while position >= 0:
        if position == 0 or text[position - 1] == "\n":
            offsets.append(position)
        position = text.find(fragment, position + 1)
    return offsets


def replacement_mismatch(current: str, block: TextBlock) -> str | None:
    """Return why ``current`` does not realize one replacement block, or None.

    The replacement occurs exactly once at a line boundary and the replaced text
    occurs nowhere outside it. The seal proves this predicate holds on the
    faithful result, so it never rejects a correct implementation.
    """
    assert block.old is not None
    placed = len(line_start_offsets(current, block.text))
    if placed != 1:
        return f"the planned replacement occurs {placed} times at a line boundary; it must occur exactly once"
    if len(line_start_offsets(current, block.old)) != len(line_start_offsets(block.text, block.old)):
        return "the replaced text is still present outside the planned replacement"
    return None


UNREADABLE = "\x00unreadable"  # sentinel: present but not UTF-8 text or not a regular file


def block_state(current: str | None, block: TextBlock) -> tuple[str, str | None]:
    """Classify one block against file text: ``exact``, ``unapplied``, or ``diverged``.

    ``current`` is the LF-normalized text, None when the file is absent, or
    UNREADABLE. A replacement is ``unapplied`` only when its replaced text occurs
    once at a line boundary and substituting it realizes the block, so the
    deletion and insert-after-anchor idioms classify correctly.
    """
    if current == UNREADABLE:
        return "diverged", "the file is not readable UTF-8 text"
    if block.old is None:
        if current is None:
            return "unapplied", "the file does not exist yet"
        if current == block.text:
            return "exact", None
        return "diverged", "the file content differs from the planned whole-file block"
    if current is None:
        return "diverged", "the file is absent"
    reason = replacement_mismatch(current, block)
    if reason is None:
        return "exact", None
    offsets = line_start_offsets(current, block.old)
    if len(offsets) == 1:
        applied = current[: offsets[0]] + block.text + current[offsets[0] + len(block.old) :]
        if replacement_mismatch(applied, block) is None:
            return "unapplied", reason
    return "diverged", reason


def _block_sequence_diagnostics(blueprint: Blueprint, view: RepositoryView) -> list[Diagnostic]:
    """Simulate a faithful executor and prove every Construct check point passes.

    For each instruction, Frozen blocks then Exact blocks: every block of the
    phase must be ``unapplied`` at the phase checkpoint (Construct checks a
    phase's blocks together), each replacement anchor must occur once where it
    is applied, and afterwards every block applied so far must be ``exact``.
    These are exactly the states red, green, status, and final verify check.
    """
    states: dict[str, str | None] = {}
    keys: dict[str, str] = {}
    for step in blueprint.steps:
        for block in step.blocks:
            try:
                keys[block.path] = view.path_key(block.path)
            except (OSError, ValueError) as exc:
                return [_error("block.target_unreadable", f"Instruction {step.number}: {block.path!r} cannot be resolved: {exc}.",
                               "Declare a readable repository-contained regular file.", path=block.path, line=block.line)]
    for step in blueprint.steps:
        for block in step.blocks:
            key = keys[block.path]
            if key in states:
                continue
            if block.old is None:
                states[key] = None
                continue
            try:
                states[key] = view.read(block.path).decode("utf-8").replace("\r\n", "\n")
            except (OSError, ValueError):
                return [
                    _error(
                        "block.target_unreadable",
                        f"Instruction {step.number}: {block.path!r} is not readable UTF-8 text, so its declared text can never be proven.",
                        "Drop the exact-text declaration for this file and specify the step instead.",
                        path=block.path,
                        line=block.line,
                    )
                ]
    applied: list[tuple[int, TextBlock]] = []
    for step in blueprint.steps:
        for phase in ("frozen", "exact"):
            blocks = [block for block in step.blocks if block.kind == phase]
            for block in blocks:
                current = states[keys[block.path]]
                if block.old is not None and current is not None:
                    count = len(line_start_offsets(current, block.old))
                    if count != 1:
                        return [
                            _error(
                                "block.anchor",
                                f"Instruction {step.number}: the replaced text occurs {count} times at a line "
                                f"boundary in {block.path!r} before it is applied; it must occur exactly once.",
                                "Quote enough whole, unchanged lines to identify one location.",
                                path=block.path,
                                line=block.line,
                            )
                        ]
                state, reason = block_state(current, block)
                if state != "unapplied":
                    return [
                        _error(
                            "block.unprovable",
                            f"Instruction {step.number} {phase} block: before it is applied the file must be in its "
                            f"unapplied state, but {reason or 'it is already realized'}; Construct could not prove it.",
                            "Widen the replaced and replacement text with unchanged neighbouring lines, or split the change.",
                            path=block.path,
                            line=block.line,
                        )
                    ]
            for block in blocks:
                key = keys[block.path]
                current = states[key]
                if block.old is None:
                    states[key] = block.text
                    continue
                assert current is not None
                offsets = line_start_offsets(current, block.old)
                if len(offsets) != 1:
                    return [
                        _error(
                            "block.anchor",
                            f"Instruction {step.number}: the replaced text occurs {len(offsets)} times at a line "
                            f"boundary in {block.path!r} where it is applied; it must occur exactly once.",
                            "Quote enough whole, unchanged lines to identify one location.",
                            path=block.path,
                            line=block.line,
                        )
                    ]
                states[key] = current[: offsets[0]] + block.text + current[offsets[0] + len(block.old) :]
            applied.extend((step.number, block) for block in blocks)
            for number, block in applied:
                state, reason = block_state(states[keys[block.path]], block)
                if state != "exact":
                    return [
                        _error(
                            "block.consumed",
                            f"Instruction {number}'s block in {block.path!r} is no longer realized after instruction "
                            f"{step.number} applies its {phase} text: {reason}.",
                            "Make later blocks preserve earlier declared text, or merge the edits into one instruction.",
                            path=block.path,
                            line=block.line,
                        )
                    ]
    return []


def _parse_steps(
    lines: list[str],
    *,
    headings: list[tuple[int, re.Match[str]]],
    end: int,
    fenced: set[int],
    diagnostics: list[Diagnostic],
) -> tuple[ImplementationStep, ...]:
    if not headings:
        diagnostics.append(
            _error(
                "step.missing",
                "Implementation must contain at least one ordered instruction.",
                "Add '### 1. <concrete change>'.",
                line=end,
            )
        )
        return ()
    numbers = [int(match.group("number")) for _index, match in headings]
    if numbers != list(range(1, len(headings) + 1)):
        diagnostics.append(
            _error(
                "step.order",
                "Implementation instruction numbers must be unique and contiguous from 1.",
                "Renumber instructions in the order a cold executor should perform them.",
                line=headings[0][0] + 1,
            )
        )
    steps: list[ImplementationStep] = []
    for position, (index, match) in enumerate(headings):
        stop = headings[position + 1][0] if position + 1 < len(headings) else end
        body_lines = [line for line in lines[index + 1 : stop]]
        if not any(line.strip() for line in body_lines):
            diagnostics.append(
                _error(
                    "step.empty",
                    f"Implementation instruction {match.group('number')} is empty.",
                    "State exactly what to change and how.",
                    line=index + 1,
                )
            )
        if not match.group("title"):
            diagnostics.append(
                _error(
                    "step.title",
                    f"Implementation instruction {match.group('number')} has no title.",
                    "Name the concrete change after the number, for example '### 1. Normalize absent names'.",
                    line=index + 1,
                )
            )
        found = _parse_step_declarations(body_lines, index, int(match.group("number")), fenced, diagnostics)
        blocks, proof, red = _parse_step_proof(
            lines, index + 1, stop, int(match.group("number")), found, fenced, diagnostics
        )
        if not found:
            diagnostics.append(
                _error(
                    "location.missing",
                    f"Instruction {match.group('number')} must name at least one concrete Location with its target State.",
                    "Add **Location:** `path/to/file.py::symbol` followed by **State:** existing or **State:** new.",
                    line=index + 1,
                )
            )
        steps.append(
            ImplementationStep(
                int(match.group("number")),
                (match.group("title") or "").strip(),
                index + 1,
                tuple(found),
                blocks,
                proof,
                red,
            )
        )
    return tuple(steps)


def _parse_draft(
    text: str,
    *,
    allow_receipts: bool = False,
) -> tuple[Blueprint | None, list[Diagnostic]]:
    normalized = text.replace("\r\n", "\n")
    lines = normalized.split("\n")
    diagnostics = _declared_fence_diagnostics(lines)
    fenced = _fenced_indexes(lines)
    # The contract-marker family is reserved across the whole document,
    # independent of line structure: \s* already crosses newlines, so a split
    # extra marker cannot hide from the count.
    family_count = len(CONTRACT_FAMILY_RE.findall(normalized))
    versions = re.findall(r"<!--\s*blueprint-contract:\s*(\S+?)\s*-->", normalized, re.IGNORECASE)
    # A draft carries exactly this runtime's marker; a sealed plan may carry any same-major marker.
    wrong_versions = [
        version
        for version in versions
        if (not compatible_version(version, CONTRACT_VERSION) if allow_receipts else version != CONTRACT_VERSION)
    ]
    if family_count != 1 or wrong_versions:
        if wrong_versions:
            message = f"Blueprint contract version {wrong_versions[0]!r} is not supported."
        elif family_count > 1:
            message = "Exactly one current Blueprint contract marker is required; extra contract markers fail closed."
        else:
            message = "Exactly one current Blueprint contract marker is required."
        diagnostics.append(
            _error("contract.unsupported", message, f"Use exactly '{CONTRACT_MARKER}' as the first line.")
        )
    elif (CONTRACT_MARKER_RE.fullmatch(lines[0]) is None) if allow_receipts else (lines[0] != CONTRACT_MARKER):
        diagnostics.append(
            _error(
                "shape.marker",
                "The current contract marker must be the exact first line of the Blueprint.",
                f"Put '{CONTRACT_MARKER}' on line 1.",
            )
        )
    retired = re.findall(r"<!--\s*(plan-contract|plan|blueprint-context)\b[^>]*-->", normalized, re.IGNORECASE)
    if retired:
        diagnostics.append(
            _error(
                "contract.retired",
                f"Retired contract marker is not accepted: {retired[0]}.",
                f"Rewrite the plan under exactly one current '{CONTRACT_MARKER}' marker.",
            )
        )
    receipt_prefixes = list(RECEIPT_PREFIX_RE.finditer(normalized))
    if not allow_receipts and receipt_prefixes:
        diagnostics.append(
            _error(
                "receipt.unexpected",
                "A draft must not contain a receipt-prefixed marker; the blueprint-proof and blueprint-validation prefixes are reserved for generated output.",
                "Remove every generated, fake, malformed, or fenced receipt-prefixed marker and seal the plain draft once.",
            )
        )
    title_line = -1
    title_text = ""
    start_index = 1 if lines and CONTRACT_MARKER_RE.fullmatch(lines[0]) else 0
    for index in range(start_index, len(lines)):
        if lines[index].strip():
            title_line = index
            title_text = lines[index]
            break
    if title_line < 0 or not title_text.startswith("# ") or not title_text[2:].strip():
        diagnostics.append(
            _error(
                "shape.title",
                "The H1 title must follow the contract marker as the next non-empty line.",
                "Write '# <Task>' immediately after the contract marker, separated only by blank lines.",
            )
        )
    names, spans, shape_diagnostics = _section_spans(lines, fenced)
    diagnostics.extend(shape_diagnostics)
    steps: tuple[ImplementationStep, ...] = ()
    verification: tuple[VerificationStep, ...] = ()
    step_headings: list[tuple[int, re.Match[str]]] = []
    implementation_end = len(lines)
    if "Implementation" in spans:
        start, end = spans["Implementation"]
        implementation_end = end
        step_headings = _step_headings(lines, start=start, end=end, fenced=fenced, diagnostics=diagnostics)
        steps = _parse_steps(lines, headings=step_headings, end=end, fenced=fenced, diagnostics=diagnostics)
    if "Verification" in spans:
        start, end = spans["Verification"]
        verification = _parse_verification(lines, start=start, end=end, fenced=fenced, diagnostics=diagnostics)
        after = [step for step in verification if step.phase == "After implementation"]
        if not after:
            diagnostics.append(
                _error(
                    "verification.after.missing",
                    "Verification must include an after-implementation Run with an observable Expect.",
                    "Add '### After implementation' with 'Run: `...`' and 'Expect: ...'.",
                    line=start + 1,
                )
            )
    sources = _collect_sources(lines, spans, fenced, diagnostics)
    locations = tuple(location for step in steps for location in step.locations)
    if not locations and not sources:
        diagnostics.append(
            _error(
                "locator.missing_required",
                "The Blueprint must declare at least one decision-critical source or implementation target.",
                "Cite a current source under Current State or a concrete Location with its State in every instruction.",
            )
        )
    diagnostics.extend(
        _scan_displaced_declarations(lines, spans, fenced, step_headings, implementation_end)
    )
    if diagnostics:
        return None, diagnostics
    return Blueprint(
        title=title_text[2:].strip(),
        text=normalized,
        sections=tuple(names),
        steps=steps,
        verification=verification,
        locations=locations,
        sources=sources,
    ), []


def _scan_displaced_declarations(
    lines: list[str],
    spans: dict[str, tuple[int, int]],
    fenced: set[int],
    step_headings: list[tuple[int, re.Match[str]]],
    implementation_end: int,
) -> list[Diagnostic]:
    """Fail closed on declarations outside their owning surfaces.

    Location and State belong inside numbered Implementation step bodies,
    Source belongs only under Current State, and the retired
    ``**Evidence:**`` / ``**Locator:**`` labels are rejected wherever they
    appear outside fenced code. Ignoring a displaced declaration would let a
    plan bind less mechanical truth than it appears to declare.
    """
    diagnostics: list[Diagnostic] = []
    step_bodies: list[tuple[int, int]] = []
    for position, (index, _match) in enumerate(step_headings):
        stop = step_headings[position + 1][0] if position + 1 < len(step_headings) else implementation_end
        step_bodies.append((index + 1, stop))

    def inside_step(absolute: int) -> bool:
        return any(start <= absolute < stop for start, stop in step_bodies)

    def section_of(absolute: int) -> str:
        for name, (start, end) in spans.items():
            if start <= absolute < end:
                return name
        return ""

    for index, raw in enumerate(lines):
        if index in fenced:
            continue
        if RETIRED_DECLARATION_RE.match(raw):
            label = raw.strip().lstrip("-* ").split("`", 1)[0]
            diagnostics.append(
                _error(
                    "declaration.retired",
                    f"Retired declaration label is not accepted: {label[:48]}",
                    "Use **Source:** under Current State and **Location:** with **State:** inside instructions.",
                    line=index + 1,
                )
            )
            continue
        if RED_LIKE_RE.match(raw) and (section_of(index) == "Verification" or (section_of(index) == "Implementation" and not inside_step(index))):
            diagnostics.append(
                _error(
                    "proof.displaced",
                    "A Red line belongs only in an instruction's Proof run chain; Verification Runs have no red observation.",
                    "Move the Red line under its instruction's **Proof run:** or remove it.",
                    line=index + 1,
                )
            )
            continue
        if INCOMPLETE_LIKE_RE.match(raw) and section_of(index) == "Implementation":
            diagnostics.append(
                _error(
                    "verification.incomplete.displaced",
                    "An Incomplete line belongs only after a Verification Run's Expect; Proof runs have no incomplete outcome.",
                    "Move the Incomplete line under its Verification Run or remove it.",
                    line=index + 1,
                )
            )
            continue
        if (
            NEAR_LABEL_RE.match(raw)
            and section_of(index) in ("Implementation", "Verification")
            and not (
                BLOCK_LABEL_RE.match(raw)
                or WITH_LABEL_RE.match(raw)
                or PROOF_LABEL_RE.match(raw)
                or RED_LIKE_RE.match(raw)
                or INCOMPLETE_LIKE_RE.match(raw)
            )
        ):
            diagnostics.append(
                _error(
                    "declaration.malformed",
                    "A line starting with Exact, Frozen, With, Proof, Red, or Incomplete followed by a colon is a reserved "
                    "declaration but is not spelled exactly, so it would be silently ignored.",
                    "Write **Exact:** `path`, **Frozen:** `path`, **With:**, **Proof run:** `command`, plain Red:, or plain "
                    "Incomplete: exactly, "
                    "or rephrase the line (or put it inside a fence) if it is prose.",
                    line=index + 1,
                )
            )
            continue
        if SOURCE_RE.match(raw) and section_of(index) != "Current State":
            diagnostics.append(
                _error(
                    "source.displaced",
                    "A Source declaration belongs only under Current State.",
                    "Move **Source:** lines into the Current State section.",
                    line=index + 1,
                )
            )
            continue
        if not inside_step(index):
            if LOCATION_RE.match(raw):
                diagnostics.append(
                    _error(
                        "location.displaced",
                        "A Location declaration belongs inside a numbered Implementation instruction.",
                        "Move **Location:** into an ordered '### N.' step with its State line.",
                        line=index + 1,
                    )
                )
            elif BLOCK_LABEL_RE.match(raw) or WITH_LABEL_RE.match(raw):
                diagnostics.append(
                    _error(
                        "block.displaced",
                        "Exact, Frozen, and With labels belong inside the numbered Implementation instruction that writes them.",
                        "Move the block into its ordered '### N.' step next to that step's Location.",
                        line=index + 1,
                    )
                )
            elif PROOF_LABEL_RE.match(raw):
                diagnostics.append(
                    _error(
                        "proof.displaced",
                        "A Proof run belongs inside the numbered Implementation instruction it decides.",
                        "Move **Proof run:** into its '### N.' step; phase-level checks stay Verification Runs.",
                        line=index + 1,
                    )
                )
            elif STATE_LIKE_RE.match(raw):
                diagnostics.append(
                    _error(
                        "state.displaced",
                        "A State declaration belongs only immediately after a Location inside a numbered step.",
                        "Move **State:** next to its Location inside an ordered '### N.' step.",
                        line=index + 1,
                    )
                )
    return diagnostics


def _bind_existing_target(
    view: RepositoryView, locator: TargetLocation, diagnostics: list[Diagnostic]
) -> dict[str, Any] | None:
    """Bind a declared existing target to its exact regular-file bytes.

    The declared path must be repository-contained and a regular file;
    symlinks and directories fail closed, so a typo'd existing path can never
    silently seal as a planned-new target.
    """
    try:
        direct = view.entry_path(locator.path)
    except (ValueError, OSError) as exc:
        diagnostics.append(
            _error(
                "location.target.unsafe",
                f"Declared {locator.state} target {locator.path!r} cannot be resolved: {exc}.",
                "Declare a repository-relative regular file.",
                path=locator.path,
                line=locator.line,
                category="missing_evidence",
            )
        )
        return None
    if direct.is_symlink() or not direct.is_file():
        diagnostics.append(
            _error(
                "location.target.missing",
                f"Declared {locator.state} target {locator.path!r} is not a regular repository file.",
                "Correct the target path; absence is never inferred as planner intent.",
                path=locator.path,
                line=locator.line,
                category="missing_evidence",
            )
        )
        return None
    try:
        data = view.read(locator.path)
    except (OSError, ValueError) as exc:
        diagnostics.append(
            _error(
                "location.target.missing",
                f"Declared {locator.state} target {locator.path!r} cannot be read: {exc}.",
                "Declare a repository-relative regular file.",
                path=locator.path,
                line=locator.line,
                category="missing_evidence",
            )
        )
        return None
    if locator.state == "deleted" and view.declared_path_key(locator.path) != view.path_key(locator.path):
        diagnostics.append(
            _error(
                "location.deleted.link",
                f"Planned-deleted target {locator.path!r} is spelled through a link or alias, so its absence would not prove the file removed.",
                "Cite the deleted file by its canonical repository path, with no linked directory or short-name alias.",
                path=locator.path,
                line=locator.line,
                category="contract_contradiction",
            )
        )
        return None
    view.hash_count += 1
    entry: dict[str, Any] = {"path": locator.path, "state": locator.state, "sha256": _sha256(data)}
    if locator.symbol is not None:
        entry["symbol"] = locator.symbol
    return entry


def _bind_new_target(
    view: RepositoryView, locator: TargetLocation, diagnostics: list[Diagnostic]
) -> dict[str, Any] | None:
    """Bind a planned-new target that must be repository-contained and absent.

    Absence uses directory-entry (lstat) semantics, so a live or broken
    symlink at the declared path counts as occupied and fails closed.
    """
    try:
        view.resolve(locator.path)
        direct = view.entry_path(locator.path)
    except (ValueError, OSError) as exc:
        diagnostics.append(
            _error(
                "location.target.unsafe",
                f"Planned-new target {locator.path!r} cannot be resolved: {exc}.",
                "Declare a repository-relative path that is absent today.",
                path=locator.path,
                line=locator.line,
                category="missing_evidence",
            )
        )
        return None
    if os.path.lexists(direct):
        diagnostics.append(
            _error(
                "location.new.occupied",
                f"Planned-new target {locator.path!r} already exists in the repository.",
                "Correct the target path or declare it **State:** existing.",
                path=locator.path,
                line=locator.line,
                category="contract_contradiction",
            )
        )
        return None
    return {"path": locator.path, "state": "new"}


def _bind_source(
    view: RepositoryView, locator: SourceLocator, diagnostics: list[Diagnostic]
) -> dict[str, Any] | None:
    """Bind a declared decision-critical source to its exact regular-file bytes."""
    try:
        direct = view.entry_path(locator.path)
    except (ValueError, OSError) as exc:
        diagnostics.append(
            _error(
                "source.locator.unsafe",
                f"Declared source {locator.path!r} cannot be resolved: {exc}.",
                "Correct or remove the declared repository-relative source.",
                path=locator.path,
                line=locator.line,
                category="missing_evidence",
            )
        )
        return None
    if direct.is_symlink() or not direct.is_file():
        diagnostics.append(
            _error(
                "source.locator.missing",
                f"Declared source {locator.path!r} is not a regular repository file.",
                "Cite an existing repository-relative regular file.",
                path=locator.path,
                line=locator.line,
                category="missing_evidence",
            )
        )
        return None
    try:
        data = view.read(locator.path)
    except (OSError, ValueError) as exc:
        diagnostics.append(
            _error(
                "source.locator.missing",
                f"Declared source {locator.path!r} cannot be read: {exc}.",
                "Correct or remove the declared repository-relative source.",
                path=locator.path,
                line=locator.line,
                category="missing_evidence",
            )
        )
        return None
    if locator.start is not None:
        if locator.end is not None and locator.end < locator.start:
            diagnostics.append(
                _error(
                    "source.locator.range",
                    f"Declared source {locator.path} has a reversed line range.",
                    "Use an inclusive range whose end is greater than or equal to its start.",
                    path=locator.path,
                    line=locator.line,
                    category="missing_evidence",
                )
            )
            return None
        try:
            line_count = len(data.decode("utf-8").splitlines())
        except UnicodeDecodeError:
            line_count = 0
        if locator.start > line_count or (locator.end is not None and locator.end > line_count):
            diagnostics.append(
                _error(
                    "source.locator.range",
                    f"Declared source {locator.path}:{locator.start} is outside the file.",
                    "Use an existing 1-based line range from the current repository.",
                    path=locator.path,
                    line=locator.line,
                    category="missing_evidence",
                )
            )
            return None
    view.hash_count += 1
    return {"path": locator.path, "sha256": _sha256(data)}


def _resolve_locations(
    blueprint: Blueprint, view: RepositoryView
) -> tuple[list[dict[str, Any]], list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    resolved: list[dict[str, Any]] = []
    for locator in blueprint.locations:
        entry = (
            _bind_new_target(view, locator, diagnostics)
            if locator.state == "new"
            else _bind_existing_target(view, locator, diagnostics)
        )
        if entry is not None:
            resolved.append(entry)
    return resolved, diagnostics


def _resolve_sources(
    blueprint: Blueprint, view: RepositoryView
) -> tuple[list[dict[str, Any]], list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    resolved: list[dict[str, Any]] = []
    for locator in blueprint.sources:
        entry = _bind_source(view, locator, diagnostics)
        if entry is not None:
            resolved.append(entry)
    return resolved, diagnostics


def _proof_binding_diagnostics(binding: Any) -> list[Diagnostic]:
    if not isinstance(binding, dict):
        return [
            _error(
                "proof.binding.shape",
                "Blueprint proof binding must be an object.",
                "Use the exact output from seal_blueprint.py.",
                category="stale_evidence",
            )
        ]
    keys = set(binding)
    if keys not in (
        {"repository_id", "git_head", "request_sha256"},
        {"repository_id", "git_head", "request_sha256", "source_item"},
    ):
        return [
            _error(
                "proof.binding.keys",
                "Blueprint proof binding has missing or unsupported fields.",
                "Use the exact output from seal_blueprint.py.",
                category="stale_evidence",
            )
        ]
    diagnostics: list[Diagnostic] = []
    if not isinstance(binding["repository_id"], str) or not binding["repository_id"]:
        diagnostics.append(
            _error(
                "proof.binding.repository_id",
                "Blueprint proof repository_id must be a non-empty string.",
                "Use the exact output from seal_blueprint.py.",
                category="stale_evidence",
            )
        )
    git_head = binding.get("git_head")
    if git_head is not None and (
        not isinstance(git_head, str) or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", git_head) is None
    ):
        diagnostics.append(
            _error(
                "proof.binding.git_head",
                "Blueprint proof git_head must be null or lowercase 40/64-char hex provenance.",
                "Use the exact output from seal_blueprint.py.",
                category="stale_evidence",
            )
        )
    request_sha256 = binding.get("request_sha256")
    if not isinstance(request_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", request_sha256) is None:
        diagnostics.append(
            _error(
                "proof.binding.request_sha256",
                "Blueprint proof request_sha256 must be lowercase 64-char hex.",
                "Use the exact output from seal_blueprint.py.",
                category="stale_evidence",
            )
        )
    if "source_item" in keys and (not isinstance(binding["source_item"], str) or not binding["source_item"]):
        diagnostics.append(
            _error(
                "proof.binding.source_item",
                "Blueprint proof source_item must be a non-empty diagnosis finding ID.",
                "Use the exact output from seal_blueprint.py.",
                category="stale_evidence",
            )
        )
    return diagnostics


def _proof_location_diagnostics(entry: Any) -> list[Diagnostic]:
    if not isinstance(entry, dict):
        return [
            _error(
                "proof.location.shape",
                "Each proof location must be an object.",
                "Use the exact output from seal_blueprint.py.",
                category="stale_evidence",
            )
        ]
    state = entry.get("state")
    if state in ("existing", "deleted"):
        keys = set(entry)
        if keys not in ({"path", "state", "sha256"}, {"path", "symbol", "state", "sha256"}):
            return [
                _error(
                    "proof.location.keys",
                    "An existing or deleted proof location must declare exactly path, state, sha256, and an optional symbol.",
                    "Use the exact output from seal_blueprint.py.",
                    category="stale_evidence",
                )
            ]
        diagnostics: list[Diagnostic] = []
        if not isinstance(entry["path"], str) or not entry["path"]:
            diagnostics.append(
                _error(
                    "proof.location.path",
                    "A proof location path must be a non-empty string.",
                    "Use the exact output from seal_blueprint.py.",
                    category="stale_evidence",
                )
            )
        if "symbol" in keys and (not isinstance(entry["symbol"], str) or not entry["symbol"]):
            diagnostics.append(
                _error(
                    "proof.location.symbol",
                    "A proof location symbol must be a non-empty string when present.",
                    "Use the exact output from seal_blueprint.py.",
                    category="stale_evidence",
                )
            )
        if not isinstance(entry["sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None:
            diagnostics.append(
                _error(
                    "proof.location.sha256",
                    "An existing or deleted proof location sha256 must be lowercase 64-char hex.",
                    "Use the exact output from seal_blueprint.py.",
                    category="stale_evidence",
                )
            )
        return diagnostics
    if state == "new":
        if set(entry) != {"path", "state"}:
            return [
                _error(
                    "proof.location.keys",
                    "A planned-new proof location must declare exactly path and state.",
                    "Use the exact output from seal_blueprint.py.",
                    category="stale_evidence",
                )
            ]
        if not isinstance(entry["path"], str) or not entry["path"]:
            return [
                _error(
                    "proof.location.path",
                    "A proof location path must be a non-empty string.",
                    "Use the exact output from seal_blueprint.py.",
                    category="stale_evidence",
                )
            ]
        return []
    return [
        _error(
            "proof.location.state",
            f"A proof location state must be exactly 'existing', 'new', or 'deleted'; received {state!r}.",
            "Use the exact output from seal_blueprint.py.",
            category="stale_evidence",
        )
    ]


def _proof_source_diagnostics(entry: Any) -> list[Diagnostic]:
    if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
        return [
            _error(
                "proof.source.shape",
                "Each proof source must declare exactly path and sha256.",
                "Use the exact output from seal_blueprint.py.",
                category="stale_evidence",
            )
        ]
    diagnostics: list[Diagnostic] = []
    if not isinstance(entry["path"], str) or not entry["path"]:
        diagnostics.append(
            _error(
                "proof.source.path",
                "A proof source path must be a non-empty string.",
                "Use the exact output from seal_blueprint.py.",
                category="stale_evidence",
            )
        )
    if not isinstance(entry["sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None:
        diagnostics.append(
            _error(
                "proof.source.sha256",
                "A proof source sha256 must be lowercase 64-char hex.",
                "Use the exact output from seal_blueprint.py.",
                category="stale_evidence",
            )
        )
    return diagnostics


def _proof_schema_diagnostics(proof: Any) -> list[Diagnostic]:
    if not isinstance(proof, dict):
        return [
            _error(
                "proof.shape",
                "Blueprint proof must be an object.",
                "Use the exact output from seal_blueprint.py.",
                category="stale_evidence",
            )
        ]
    if set(proof) != {"version", "binding", "locations", "sources"}:
        return [
            _error(
                "proof.keys",
                "Blueprint proof has missing or unsupported fields.",
                "Use the exact output from seal_blueprint.py.",
                category="stale_evidence",
            )
        ]
    if not compatible_version(proof.get("version"), CONTRACT_VERSION):
        return [
            _error(
                "proof.version",
                f"Blueprint proof version {proof.get('version')!r} is not supported.",
                "Use the exact output from seal_blueprint.py.",
                category="stale_evidence",
            )
        ]
    diagnostics = [*_proof_binding_diagnostics(proof.get("binding"))]
    locations = proof.get("locations")
    if not isinstance(locations, list):
        diagnostics.append(
            _error(
                "proof.locations.shape",
                "Blueprint proof locations must be a list.",
                "Use the exact output from seal_blueprint.py.",
                category="stale_evidence",
            )
        )
    else:
        for entry in locations:
            diagnostics.extend(_proof_location_diagnostics(entry))
    sources = proof.get("sources")
    if not isinstance(sources, list):
        diagnostics.append(
            _error(
                "proof.sources.shape",
                "Blueprint proof sources must be a list.",
                "Use the exact output from seal_blueprint.py.",
                category="stale_evidence",
            )
        )
    else:
        for entry in sources:
            diagnostics.extend(_proof_source_diagnostics(entry))
    return diagnostics


def _request_error(code: str, message: str) -> ValueError:
    error = ValueError(message)
    setattr(
        error,
        "diagnostics",
        (
            Diagnostic(
                code,
                message,
                "Repair or replace the request handoff and rerun the same seal command.",
                category="contract_contradiction",
            ),
        ),
    )
    return error


def detect_request_source(
    request_bytes: bytes,
    handoff_item: str | None = None,
    *,
    repo_root: Path | None = None,
    check_sources: bool = True,
) -> dict[str, Any]:
    """Verify the repository's existing typed handoff envelope."""
    try:
        text = request_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _request_error("request.encoding", "Request files must be valid UTF-8.") from exc
    first = text.partition("\n")[0].rstrip("\r")
    head, footer_separator, final = text.removesuffix("\n").rpartition("\n")
    final = final.rstrip("\r")
    body = head + "\n" if footer_separator else ""
    match = HANDOFF_RECEIPT_RE.fullmatch(final)
    cleaned = _clean_architecture_view(text)
    has_raw = _has_unquoted_architecture_raw(cleaned)
    has_source = _has_unquoted_architecture_source(cleaned)
    provenance = re.findall(r"(?im)^[ \t]*(<!--\s*architecture-source\b[^\n]*)", cleaned)
    if provenance:
        if len(provenance) != 1 or match is not None or handoff_item is not None:
            raise _request_error(
                "handoff.architecture.source",
                "Use exactly one architecture source without another typed handoff or selected item.",
            )
        if has_raw:
            raise _request_error(
                "handoff.architecture.source", "Architecture source must not compete with a raw architecture envelope."
            )
        if re.search(r"(?m)^[ \t]+<!--\s*architecture-source\b", cleaned):
            raise _request_error(
                "handoff.architecture.source", "Architecture source declaration is displaced or malformed."
            )
        if text.startswith(("\n", "\r", "\ufeff", " ", "\t")):
            raise _request_error(
                "handoff.architecture.source", "Architecture source request is displaced or malformed."
            )
        declaration = re.fullmatch(r"<!-- architecture-source: (\{.*\}) -->", provenance[0].rstrip("\r"))
        try:
            record = json.loads(declaration.group(1)) if declaration else None
            if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
                raise ValueError("Architecture source needs exactly path and sha256.")
            if (
                not isinstance(record["path"], str)
                or not Path(record["path"]).is_absolute()
                or Path(record["path"]).name != "architecture.md"
            ):
                raise ValueError("Architecture source path must name an absolute architecture.md.")
            if not isinstance(record["sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None:
                raise ValueError("Architecture source sha256 must bind exact file bytes.")
            if check_sources:
                if repo_root is None:
                    raise ValueError("Architecture source verification requires the repository root.")
                architecture_handoff = import_module("architecture_handoff")
                read_primary = architecture_handoff.read_primary
                verify_handoff = architecture_handoff.verify_handoff

                data = read_primary(Path(record["path"]), repo_root)
                if _sha256(data) != record["sha256"]:
                    raise ValueError("Architecture source digest changed after request resolution.")
                verify_handoff(data, repo_root)
        except (OSError, ValueError) as exc:
            raise _request_error("handoff.architecture.source", str(exc)) from exc
        return {"kind": "architecture", "contract_version": ARCHITECTURE_HANDOFF_VERSION, "item": None}
    if match is None:
        if first.startswith("# Architecture Decision:"):
            raise _request_error(
                "handoff.architecture.receipt", "An architecture decision requires its verified receipt."
            )
        raw_lines = text.split("\n")
        if (
            CANONICAL_HANDOFF_MARKER_RE.match(first)
            or RECEIPT_SHAPED_RE.match(final)
            or any(
                (receipt := HANDOFF_RECEIPT_RE.fullmatch(line.rstrip("\r"))) is not None
                and _sha256("".join(previous + "\n" for previous in raw_lines[:index]).encode("utf-8"))
                == receipt.group("digest")
                for index, line in enumerate(raw_lines)
            )
        ):
            raise _request_error(
                "handoff.receipt.malformed",
                "A typed handoff receipt must be the exact final line; reseal the handoff with its producing skill.",
            )
        if handoff_item is not None:
            raise _request_error("handoff.item.unexpected", "handoff_item is valid only for diagnosis handoffs.")
        if HANDOFF_LIKE_RE.fullmatch(first) or (HANDOFF_LIKE_RE.fullmatch(final) and "sha256:" in final):
            raise _request_error(
                "handoff.marker.unsupported", "The request uses an unknown or unsupported handoff marker."
            )
        if has_raw or has_source:
            raise _request_error(
                "handoff.architecture.receipt",
                "Displaced or malformed architecture must be resealed; it cannot enter as a generic request.",
            )
        return {"kind": "generic", "contract_version": None, "item": None}
    if not footer_separator:
        raise _request_error("handoff.receipt.malformed", "Typed handoff content is missing before its receipt.")
    marker = match.group("marker")
    kind = "issue" if marker == "ticket-scope" else marker
    version = match.group("version")
    expected_version = {
        "diagnosis": DIAGNOSIS_HANDOFF_VERSION,
        "architecture": ARCHITECTURE_HANDOFF_VERSION,
        "issue": TICKET_SCOPE_HANDOFF_VERSION,
    }[kind]
    if not compatible_version(version, expected_version):
        raise _request_error(
            "handoff.version.unsupported",
            f"Unsupported {kind} handoff contract version {version!r}; expected major {expected_version.split('.')[0]}.",
        )
    if _sha256(body.encode("utf-8")) != match.group("digest"):
        raise _request_error("handoff.receipt.stale", "Typed handoff receipt does not match its content.")
    if kind != "diagnosis" and handoff_item is not None:
        raise _request_error("handoff.item.unexpected", "handoff_item is valid only for diagnosis handoffs.")
    selected: str | None = None
    if kind == "architecture" and check_sources:
        try:
            architecture_handoff = import_module("architecture_handoff")
            verify_handoff = architecture_handoff.verify_handoff
            if repo_root is None:
                raise ValueError("Architecture verification requires the repository root.")

            verify_handoff(request_bytes, repo_root, check_sources=True)
        except (OSError, ValueError) as exc:
            raise _request_error("handoff.architecture.invalid", str(exc)) from exc
    elif kind == "diagnosis":
        findings = re.findall(r"^## Finding (?P<id>\S+)\s*$", body, re.MULTILINE)
        if not findings:
            raise _request_error("handoff.diagnosis.empty", "Diagnosis has no accepted findings to plan.")
        if handoff_item is None and len(findings) > 1:
            raise _request_error(
                "handoff.item.required", "Multi-finding diagnoses require one handoff_item finding ID."
            )
        selected = handoff_item or findings[0]
        if selected not in findings:
            raise _request_error("handoff.item.unknown", f"Diagnosis does not contain finding {selected!r}.")
    elif kind == "issue":
        metadata_match = re.search(r"<!-- ticket-scope-metadata -->\s*```json\s*(\{.*?\})\s*```", body, re.DOTALL)
        try:
            metadata = json.loads(metadata_match.group(1)) if metadata_match else {}
        except json.JSONDecodeError as exc:
            raise _request_error("handoff.issue.metadata", "Ticket-scope metadata is malformed.") from exc
        if metadata.get("status") != "plan-ready":
            raise _request_error("handoff.not_actionable", "Ticket-scope status must be plan-ready.")
    return {"kind": kind, "contract_version": version, "item": selected}


def _raise(diagnostics: list[Diagnostic]) -> NoReturn:
    error = ValueError("Blueprint validation failed")
    setattr(error, "diagnostics", tuple(diagnostics))
    raise error


def _deletion_diagnostics(blueprint: Blueprint, view: RepositoryView) -> list[Diagnostic]:
    """A planned deletion is its path's only Location and is never cited as Source."""

    def key(raw: str) -> str | None:
        try:
            return view.declared_path_key(raw)
        except (OSError, ValueError):
            return None  # location/source resolution already reports unsafe paths

    def same_file(first: str, second: str) -> bool:
        try:
            return view.entry_key(first) == view.entry_key(second)
        except (OSError, ValueError):
            return False  # location/source resolution already reports unresolvable paths

    deleted: dict[str, TargetLocation] = {}
    for location in blueprint.locations:
        found = key(location.path) if location.state == "deleted" else None
        if found is not None:
            deleted.setdefault(found, location)
    diagnostics: list[Diagnostic] = []
    for location in blueprint.locations:
        if location.state == "deleted" and location.symbol is not None:
            diagnostics.append(_error(
                "location.deleted.symbol",
                f"Planned-deleted target {location.path!r} names symbol {location.symbol!r}, but a deletion removes the whole file.",
                "Cite the file alone to delete it, or declare it **State:** existing and specify the symbol's removal.",
                path=location.path, line=location.line, category="contract_contradiction",
            ))
        owner = deleted.get(key(location.path) or "")
        if owner is None or owner is location:
            # A link reaches the same file under a different key.
            owner = next((other for other in deleted.values()
                          if other is not location and same_file(location.path, other.path)), owner)
        if owner is not None and location is not owner:
            diagnostics.append(_error(
                "location.deleted.conflict",
                f"Planned-deleted target {owner.path!r} (line {owner.line}) is declared again by the Location on line {location.line}.",
                "Declare a deleted path exactly once, in the instruction that deletes it; edits made before its deletion are discarded.",
                path=location.path, line=location.line, category="contract_contradiction",
            ))

    for source in blueprint.sources:
        owner = deleted.get(key(source.path) or "") or next(
            (location for location in deleted.values() if same_file(source.path, location.path)), None
        )
        if owner is not None:
            diagnostics.append(_error(
                "source.deleted",
                f"Declared source {source.path!r} is deleted by the Location on line {owner.line}, so it cannot remain evidence after its own step.",
                "Remove this Source line: the deleted Location already binds the file's sealed bytes. Cite a surviving file for any fact the plan still relies on.",
                path=source.path, line=source.line, category="contract_contradiction",
            ))
    return diagnostics


def validate_draft(
    text: str, repo_root: Path, *, view: RepositoryView | None = None, **_kwargs: Any
) -> ValidationResult:
    repository = view or RepositoryView(repo_root)
    blueprint, diagnostics = _parse_draft(text)
    if blueprint is None:
        return ValidationResult(None, tuple(diagnostics), repository)
    _locations, location_diagnostics = _resolve_locations(blueprint, repository)
    diagnostics.extend(location_diagnostics)
    _sources, source_diagnostics = _resolve_sources(blueprint, repository)
    diagnostics.extend(source_diagnostics)
    diagnostics.extend(_deletion_diagnostics(blueprint, repository))
    diagnostics.extend(_block_sequence_diagnostics(blueprint, repository))
    return ValidationResult(blueprint if not diagnostics else None, tuple(diagnostics), repository)


def canonical_body(text: str) -> str:
    lines = [
        line
        for line in text.replace("\r\n", "\n").split("\n")
        if PROOF_RE.fullmatch(line) is None and VALIDATION_RE.fullmatch(line) is None
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def canonical_plan(text: str) -> str:
    """Return the author-owned body without generated receipts."""
    return canonical_body(text)


def plan_sha256(text: str) -> str:
    return _sha256(canonical_plan(text).encode("utf-8"))


def _request_binding(view: RepositoryView, request_bytes: bytes, request_source: dict[str, Any]) -> dict[str, Any]:
    repository_id, git_head = view.repository_identity()
    binding = {
        "repository_id": repository_id,
        "git_head": git_head,
        "request_sha256": _sha256(request_bytes),
    }
    if request_source.get("kind") == "diagnosis":
        binding["source_item"] = request_source.get("item")
    return binding


def build_proof(
    blueprint: Blueprint,
    view: RepositoryView,
    request_bytes: bytes,
    request_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    locations, diagnostics = _resolve_locations(blueprint, view)
    sources, source_diagnostics = _resolve_sources(blueprint, view)
    diagnostics.extend(source_diagnostics)
    diagnostics.extend(_deletion_diagnostics(blueprint, view))
    diagnostics.extend(_block_sequence_diagnostics(blueprint, view))
    if diagnostics:
        _raise(diagnostics)
    source = request_source or detect_request_source(request_bytes, repo_root=view.repo_root)
    return {
        "version": CONTRACT_VERSION,
        "binding": _request_binding(view, request_bytes, source),
        "locations": locations,
        "sources": sources,
    }


def _expected_receipts(blueprint: Blueprint, view: RepositoryView) -> tuple[dict[str, Any], list[Diagnostic]]:
    locations, diagnostics = _resolve_locations(blueprint, view)
    sources, source_diagnostics = _resolve_sources(blueprint, view)
    diagnostics.extend(source_diagnostics)
    return {"locations": locations, "sources": sources}, diagnostics


def render_sealed_blueprint(text: str, proof: dict[str, Any]) -> str:
    body = canonical_body(text)
    proof_json = _canonical_json(proof)
    plan_hash = plan_sha256(body)
    proof_hash = _sha256(proof_json.encode("utf-8"))
    lines = body.rstrip("\n").split("\n")
    lines.extend(
        [
            f"<!-- blueprint-proof: {proof_json} -->",
            f"<!-- blueprint-validation: {CONTRACT_VERSION}; plan-sha256: {plan_hash}; proof-sha256: {proof_hash} -->",
        ]
    )
    return "\n".join(lines) + "\n"


def seal_blueprint(
    repo_root: Path,
    request_file: Path,
    draft_file: Path,
    *,
    handoff_item: str | None = None,
) -> SealResult:
    root = repo_root.resolve()
    draft = Path(draft_file)
    if not draft.is_absolute():
        draft = Path.cwd() / draft
    request = Path(request_file)
    if not request.is_absolute():
        request = Path.cwd() / request
    if not draft.is_file():
        raise ValueError("draft_file must be an existing file")
    if draft.name.casefold() in {name.casefold() for name in RETIRED_BLUEPRINT_ARTIFACTS}:
        _raise(
            [
                _error(
                    "artifact.retired",
                    f"Retired Blueprint artifact filename is not accepted: {draft.name}.",
                    "Write the complete plain contract to blueprint.md instead.",
                    category="contract_contradiction",
                )
            ]
        )
    if request.name in RETIRED_HANDOFF_ARTIFACTS:
        error = _request_error(
            "handoff.path.retired", f"Retired handoff artifact filename is not accepted: {request.name}."
        )
        raise error
    if draft.name.casefold() != BLUEPRINT_FILENAME.casefold():
        _raise(
            [
                _error(
                    "artifact.noncanonical",
                    f"Blueprint draft must be named {BLUEPRINT_FILENAME}; received {draft.name}.",
                    "Write the complete plain contract to blueprint.md before sealing.",
                    category="contract_contradiction",
                )
            ]
        )
    canonical_draft = canonical_blueprint_path(root, draft, require_existing=True)
    canonical_sibling_request = canonical_request_path(
        root, canonical_draft.parent / REQUEST_FILENAME, require_existing=True
    )
    supplied_request = canonical_request_path(root, request, require_existing=True)
    if supplied_request != canonical_sibling_request:
        raise _workspace_error(
            "workspace.request.sibling",
            f"Blueprint sealing requires the sibling canonical {REQUEST_FILENAME}: {canonical_sibling_request}",
            f"Use the exact {REQUEST_FILENAME} path returned by workspace preparation.",
        )
    _workspace_task_directory(canonical_draft.parent, require_request=True)
    request_bytes = canonical_sibling_request.read_bytes()
    request_source = detect_request_source(request_bytes, handoff_item, repo_root=root)
    draft_text = canonical_draft.read_bytes().decode("utf-8")
    view = RepositoryView(root)
    blueprint, diagnostics = _parse_draft(draft_text)
    if blueprint is None:
        _raise(list(diagnostics))
    # Proof construction performs the single authoritative mechanical
    # resolution; sealing never resolves the same declarations twice.
    proof = build_proof(blueprint, view, request_bytes, request_source)
    return SealResult(
        render_sealed_blueprint(blueprint.text, proof),
        proof,
        view.counters(),
    )


def sealed_contract_diagnostic(text: str) -> Diagnostic | None:
    """Name an older or unknown contract version before any receipt check runs."""
    first = text.replace("\r\n", "\n").split("\n", 1)[0]
    match = re.fullmatch(r"<!--\s*blueprint-contract:\s*(\S+?)\s*-->", first.strip(), re.IGNORECASE)
    if match is None or compatible_version(match.group(1), CONTRACT_VERSION):
        return None
    return _error(
        "contract.unsupported",
        f"Blueprint contract {match.group(1)} is not supported; this runtime executes only contract major {CONTRACT_VERSION.split('.')[0]}.",
        f"Reseal the plan under contract {CONTRACT_VERSION} from its request.",
        category="contract_contradiction",
    )


def _receipt_pair_diagnostics(text: str) -> list[Diagnostic] | None:
    """Enforce the canonical sealed receipt placement.

    The receipt prefixes are reserved globally, independent of fence state and
    marker well-formedness: a sealed document carries exactly two
    receipt-prefixed lines, the generated proof and then the generated
    validation as its final two lines, with the contract marker on line 1. Any
    authored, displaced, duplicated, malformed, or fenced fake receipt-prefixed
    line fails closed.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    prefix_indexes = [index for index, line in enumerate(lines) if RECEIPT_PREFIX_RE.search(line)]
    if len(lines) < 3 or prefix_indexes != [len(lines) - 2, len(lines) - 1]:
        return [
            _error(
                "receipt.missing" if len(prefix_indexes) < 2 else "receipt.displaced",
                "The sealed document must contain exactly the generated proof and validation receipts as its final two lines.",
                "Use the exact output from seal_blueprint.py without editing, moving, or adding receipt markers; "
                "reseal a plan whose receipts sit below its contract marker.",
                category="stale_evidence",
            )
        ]
    if PROOF_RE.fullmatch(lines[-2]) is None or VALIDATION_RE.fullmatch(lines[-1]) is None:
        return [
            _error(
                "receipt.malformed",
                "The final two receipt-prefixed lines are not the exact generated proof and validation shapes.",
                "Use the exact output from seal_blueprint.py.",
                category="stale_evidence",
            )
        ]
    marker_exact = bool(lines) and CONTRACT_MARKER_RE.fullmatch(lines[0]) is not None
    if not marker_exact:
        return [
            _error(
                "receipt.displaced",
                "The contract marker must be the exact first line.",
                "Use the exact output from seal_blueprint.py.",
                category="stale_evidence",
            )
        ]
    return None


def verify_sealed_blueprint(
    text: str,
    repo_root: Path,
    request_bytes: bytes,
    *,
    handoff_item: str | None = None,
) -> tuple[Blueprint | None, list[Diagnostic], RepositoryView]:
    """Authoritatively verify one sealed Blueprint against its frozen request.

    Request bytes are mandatory and target/source state is always verified:
    there is no call path that accepts a sealed Blueprint while skipping the
    request binding, target/source drift, or planned-new appearance checks.
    Structure-only inspection belongs to ``parse_blueprint``; workspace
    identity extraction belongs to ``_sealed_binding``.
    """
    view = RepositoryView(repo_root)
    retired = sealed_contract_diagnostic(text)
    if retired is not None:
        return (None, [retired], view)
    diagnostics: list[Diagnostic] = []
    proof_matches = list(PROOF_RE.finditer(text))
    validation_matches = list(VALIDATION_RE.finditer(text))
    receipt_pair = _receipt_pair_diagnostics(text)
    if receipt_pair is not None:
        return (None, receipt_pair, view)
    body = canonical_body(text)
    receipt = validation_matches[0]
    try:
        proof = json.loads(proof_matches[0].group("json"))
    except json.JSONDecodeError:
        return (
            None,
            [
                _error(
                    "proof.malformed",
                    "Blueprint proof is not valid JSON.",
                    "Use the exact output from seal_blueprint.py.",
                    category="stale_evidence",
                )
            ],
            view,
        )
    try:
        current_plan = plan_sha256(body)
    except ValueError as exc:
        current_plan = None
        diagnostics.extend(getattr(exc, "diagnostics", ()))
    if (
        current_plan is None
        or receipt.group("plan") != current_plan
        or receipt.group("proof") != _sha256(_canonical_json(proof).encode("utf-8"))
    ):
        diagnostics.append(
            _error(
                "proof.stale",
                "Blueprint plan or proof digest does not match the validation receipt.",
                "Reseal the unchanged Blueprint draft.",
                category="stale_evidence",
            )
        )
    blueprint, parse_diagnostics = _parse_draft(body, allow_receipts=True)
    diagnostics.extend(parse_diagnostics)
    binding = proof.get("binding") if isinstance(proof, dict) else None
    schema_diagnostics = _proof_schema_diagnostics(proof)
    diagnostics.extend(schema_diagnostics)
    request_source: dict[str, Any] | None = None
    sealed_source_item = binding.get("source_item") if isinstance(binding, dict) else None
    try:
        request_source = detect_request_source(
            request_bytes, handoff_item, repo_root=repo_root, check_sources=False
        )
    except ValueError as exc:
        source_diagnostics = tuple(getattr(exc, "diagnostics", ()))
        if (
            handoff_item is None
            and isinstance(sealed_source_item, str)
            and any(item.code == "handoff.item.required" for item in source_diagnostics)
        ):
            try:
                request_source = detect_request_source(
                    request_bytes, sealed_source_item, repo_root=repo_root, check_sources=False
                )
            except ValueError as retry_exc:
                diagnostics.extend(getattr(retry_exc, "diagnostics", ()))
        else:
            diagnostics.extend(source_diagnostics)
    if not schema_diagnostics and isinstance(binding, dict):
        repository_id, _current_head = view.repository_identity()
        if binding.get("repository_id") != repository_id:
            diagnostics.append(
                _error(
                    "binding.repository",
                    "Blueprint is bound to a different repository.",
                    "Re-seal the Blueprint from the authoritative repository.",
                    category="contract_contradiction",
                )
            )
        if request_source is not None:
            source_item = binding.get("source_item")
            if request_source.get("kind") == "diagnosis":
                if source_item != request_source.get("item"):
                    diagnostics.append(
                        _error(
                            "binding.request.source_item",
                            "Blueprint selected diagnosis finding does not match the supplied request selection.",
                            "Use the request and handoff item that were sealed with this Blueprint, or reseal from the plain draft.",
                            category="stale_evidence",
                        )
                    )
            elif "source_item" in binding:
                diagnostics.append(
                    _error(
                        "binding.request.source_item_unexpected",
                        "Blueprint request binding includes a diagnosis finding for a non-diagnosis request.",
                        "Reseal the Blueprint from the authoritative request.",
                        category="contract_contradiction",
                    )
                )
        request_digest = binding.get("request_sha256")
        if request_digest != _sha256(request_bytes):
            diagnostics.append(
                _error(
                    "binding.request.stale",
                    "Blueprint request binding does not match the supplied request.",
                    "Use the request that was sealed with this Blueprint.",
                    category="stale_evidence",
                )
            )
        if blueprint is not None:
            expected, receipt_diagnostics = _expected_receipts(blueprint, view)
            diagnostics.extend(receipt_diagnostics)
            if not receipt_diagnostics:
                if expected["locations"] != proof.get("locations"):
                    diagnostics.append(
                        _error(
                            "proof.locations.stale",
                            "Declared target locations do not match the current repository state.",
                            "Refresh the target state and reseal the Blueprint.",
                            category="stale_evidence",
                        )
                    )
                if expected["sources"] != proof.get("sources"):
                    diagnostics.append(
                        _error(
                            "proof.sources.stale",
                            "Declared source hashes do not match the current repository.",
                            "Refresh the source evidence and reseal the Blueprint.",
                            category="stale_evidence",
                        )
                    )
    if diagnostics:
        return blueprint, diagnostics, view
    if blueprint is None:
        return (
            None,
            [
                _error(
                    "shape.invalid",
                    "Blueprint shape could not be parsed.",
                    "Repair the named mechanical defect and reseal.",
                )
            ],
            view,
        )
    return (
        dataclasses.replace(
            blueprint,
            binding=binding if isinstance(binding, dict) else None,
            receipt={"plan": receipt.group("plan"), "proof": receipt.group("proof")},
            plan_sha256=receipt.group("plan"),
        ),
        [],
        view,
    )


def parse_blueprint(text: str) -> tuple[Blueprint | None, list[Diagnostic]]:
    return _parse_draft(canonical_body(text), allow_receipts=True)

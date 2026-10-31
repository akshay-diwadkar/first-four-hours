"""Read-only architecture receipt and snapshot contract; packaged byte-for-byte."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from _skill_protocol_runtime import compatible_version, compatible_version_pattern
from architecture_contract import BLUEPRINT_WORKSPACE_PARTS, WORKSPACE_DIR, WORKSPACE_PARTS, validate_handoff

BLUEPRINT_WORKSPACE_DIR = "/".join(BLUEPRINT_WORKSPACE_PARTS)

ARCHITECT_VERSION = "1.0.2"
# First Architect version whose no-HEAD Git snapshot skips Git-ignored files.
NO_HEAD_GIT_SCOPE_SINCE = (1, 0, 1)
RECEIPT_RE = re.compile(rf"^<!-- architecture: {compatible_version_pattern(ARCHITECT_VERSION)}; sha256: ([0-9a-f]{{64}}) -->$")
PROOF_RE = re.compile(r"^<!-- architecture-proof: (?P<json>.+) -->$")
LEADING_HANDOFF_RECEIPT_RE = re.compile(
    r"^<!--\s*(?:diagnosis|architecture|optimization|ticket-scope|ticket-handoff|issue-handoff|audit-handoff|design-handoff|optimization-handoff)(?=\s|:|-->|$)",
    re.IGNORECASE,
)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_untracked_path(repo_root: Path, path: Path, untracked: list[list[str]]) -> None:
    try:
        # The repository entry name, rather than its resolved target, owns the
        # snapshot identity.  Resolving here loses children reached through a
        # directory junction or symlink outside the root.
        relative = path.absolute().relative_to(repo_root)
    except ValueError:
        return
    if ".git" in relative.parts:
        return
    rendered = relative.as_posix()
    if path.is_symlink():
        untracked.append(["symlink", rendered, os.readlink(path)])
    elif path.is_file():
        untracked.append(["file", rendered, _sha256_bytes(path.read_bytes())])


def _record_untracked_entry(
    repo_root: Path, raw: str, untracked: list[list[str]], *, git_root: Path
) -> None:
    candidate = git_root / raw.rstrip("/\\")
    if candidate.is_dir() and not candidate.is_symlink():
        for child in sorted(candidate.rglob("*")):
            _record_untracked_path(repo_root, child, untracked)
        return
    _record_untracked_path(repo_root, candidate, untracked)


def _dirty_fingerprint(repo_root: Path, *, git_root: Path | None = None) -> str | None:
    status = _git(repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", ".", f":(exclude){BLUEPRINT_WORKSPACE_DIR}")
    if status.returncode != 0:
        raise ValueError("cannot establish Git status for architecture snapshot: " + status.stderr.strip())
    if not status.stdout:
        return None
    unstaged = subprocess.run(["git", "diff", "--binary"], cwd=repo_root, capture_output=True, check=False)
    staged = subprocess.run(["git", "diff", "--cached", "--binary"], cwd=repo_root, capture_output=True, check=False)
    if unstaged.returncode != 0 or staged.returncode != 0:
        raise ValueError("cannot establish Git diff for architecture snapshot")
    untracked: list[list[str]] = []
    payload = {
        "status": status.stdout,
        "unstaged": _sha256_bytes(unstaged.stdout),
        "staged": _sha256_bytes(staged.stdout),
        "untracked": untracked,
    }
    entries = [entry for entry in status.stdout.split("\0") if entry]
    untracked_raws = [entry[3:] for entry in entries if entry.startswith("?? ")]
    if untracked_raws:
        if git_root is None:
            toplevel = _git(repo_root, "rev-parse", "--show-toplevel")
            if toplevel.returncode != 0 or not toplevel.stdout.strip():
                raise ValueError("cannot establish Git worktree root for untracked snapshot")
            git_root = Path(toplevel.stdout.strip())
        for raw in untracked_raws:
            _record_untracked_entry(repo_root, raw, untracked, git_root=git_root)
    untracked.sort()
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _snapshot_excluded(relative: Path) -> bool:
    return (
        ".git" in relative.parts
        or relative.parts[:2] == BLUEPRINT_WORKSPACE_PARTS
        or len(relative.parts) == 4 and relative.parts[:2] == WORKSPACE_PARTS and relative.parts[3] == "architecture.md"
    )


def _entries_digest(entries: list[tuple[str, str]]) -> str:
    return hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _filesystem_fingerprint(repo_root: Path) -> str:
    entries: list[tuple[str, str]] = []
    for path in sorted(repo_root.rglob("*")):
        relative = path.absolute().relative_to(repo_root)
        if _snapshot_excluded(relative) or not path.is_file():
            continue
        entries.append((relative.as_posix(), _sha256_bytes(path.read_bytes())))
    return _entries_digest(entries)


def _git_scoped_fingerprint(repo_root: Path) -> str:
    # Bytes mode: _git's locale text decoding would corrupt non-ASCII names on Windows.
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", ".", f":(exclude){BLUEPRINT_WORKSPACE_DIR}"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if listed.returncode != 0:
        raise ValueError(
            "cannot establish Git file list for architecture snapshot: "
            + listed.stderr.decode("utf-8", errors="replace").strip()
        )
    entries: dict[str, str] = {}
    for raw in listed.stdout.split(b"\0"):
        if not raw:
            continue
        name = os.fsdecode(raw)
        if name.endswith("/"):
            name = name[:-1]
        relative = Path(name)
        path = repo_root / relative
        if _snapshot_excluded(relative):
            continue
        if path.is_dir() and not path.is_symlink():
            # An untracked nested repository or a submodule: hash its files as the full-tree rule does.
            for child in sorted(path.rglob("*")):
                child_relative = child.relative_to(repo_root)
                if child.is_file() and not _snapshot_excluded(child_relative):
                    entries[child_relative.as_posix()] = _sha256_bytes(child.read_bytes())
        elif path.is_file():
            entries[relative.as_posix()] = _sha256_bytes(path.read_bytes())
    return _entries_digest(sorted(entries.items()))


def _inside_git_worktree(root: Path) -> bool:
    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    return inside.returncode == 0 and inside.stdout.strip() == "true"


def _snapshot(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    _validate_planning_namespace(root)
    metadata = _git(root, "rev-parse", "--is-inside-work-tree", "--git-common-dir", "HEAD", "--show-toplevel")
    metadata_lines = metadata.stdout.strip().splitlines()
    if metadata.returncode == 0 and len(metadata_lines) == 4 and metadata_lines[0].strip() == "true" and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", metadata_lines[2].strip()):
        tracked = _git(root, "ls-files", "-z", "--", BLUEPRINT_WORKSPACE_DIR)
        if tracked.returncode or tracked.stdout:
            raise ValueError("architecture snapshot cannot exclude tracked Blueprint content")
        common, head, top_level = (line.strip() for line in metadata_lines[1:])
        common_path = Path(common)
        if not common_path.is_absolute():
            common_path = root / common_path
        dirty = _dirty_fingerprint(root, git_root=Path(top_level))
        return {
            "kind": "git",
            "scope_version": ARCHITECT_VERSION,
            "project_root": str(root),
            "repository_id": str(common_path.resolve()),
            "revision": head,
            "dirty": dirty is not None,
            "dirty_fingerprint": dirty,
        }
    if _inside_git_worktree(root):
        tracked = _git(root, "ls-files", "-z", "--", BLUEPRINT_WORKSPACE_DIR)
        if tracked.returncode or tracked.stdout:
            raise ValueError("architecture snapshot cannot exclude tracked Blueprint content")
        common = _git(root, "rev-parse", "--git-common-dir").stdout.strip()
        head = _git(root, "rev-parse", "HEAD").stdout.strip()
        if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head) is None:
            return {
                "kind": "filesystem",
                "scope_version": ARCHITECT_VERSION,
                "project_root": str(root),
                "fingerprint": _git_scoped_fingerprint(root),
            }
        common_path = Path(common)
        if not common_path.is_absolute():
            common_path = root / common_path
        dirty = _dirty_fingerprint(root)
        return {
            "kind": "git",
            "scope_version": ARCHITECT_VERSION,
            "project_root": str(root),
            "repository_id": str(common_path.resolve()),
            "revision": head,
            "dirty": dirty is not None,
            "dirty_fingerprint": dirty,
        }
    return {
        "kind": "filesystem",
        "scope_version": ARCHITECT_VERSION,
        "project_root": str(root),
        "fingerprint": _filesystem_fingerprint(root),
    }


def _proof_line(snapshot: dict[str, Any]) -> str:
    return (
        "<!-- architecture-proof: " + json.dumps({"snapshot": snapshot}, sort_keys=True, separators=(",", ":")) + " -->"
    )


def _receipt_free(text: str, repo_root: Path | None = None) -> str:
    head, separator, final = text.removesuffix("\n").rpartition("\n")
    final_line = final.rstrip("\r")
    match = RECEIPT_RE.fullmatch(final_line)
    if match is None:
        first_line = text.partition("\n")[0].rstrip("\r")
        if LEADING_HANDOFF_RECEIPT_RE.match(first_line) or LEADING_HANDOFF_RECEIPT_RE.match(final_line):
            raise ValueError("handoff receipt must be the exact final architecture receipt line")
        return text
    with_proof = head + "\n"
    if not separator or hashlib.sha256(with_proof.encode("utf-8")).hexdigest() != match.group(1):
        raise ValueError("architecture decision receipt does not match content")
    decision_head, proof_separator, proof_line = head.rpartition("\n")
    proof_match = PROOF_RE.fullmatch(proof_line.rstrip("\r"))
    if proof_match is None or not proof_separator:
        raise ValueError("architecture proof is missing or malformed")
    decision = decision_head + "\n"
    try:
        proof = json.loads(proof_match.group("json"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"architecture proof is malformed: {exc}") from exc
    if repo_root is None:
        # Frozen resume: verify the exact outer receipt/proof envelope only.
        # Snapshot version, root, currentness and external sources stay untouched;
        # bound request/plan bytes own further progress.
        if not isinstance(proof, dict) or set(proof) != {"snapshot"} or not isinstance(proof["snapshot"], dict):
            raise ValueError("architecture proof snapshot shape is invalid")
        return decision
    if not isinstance(proof, dict) or set(proof) != {"snapshot"} or not _snapshot_shape(proof["snapshot"]):
        raise ValueError("architecture proof snapshot shape is invalid")
    recorded = {key: item for key, item in proof["snapshot"].items() if key != "scope_version"}
    current = {key: item for key, item in _snapshot(repo_root).items() if key != "scope_version"}
    if recorded != current:
        if (
            recorded.get("kind") == "filesystem"
            and current.get("kind") == "filesystem"
            and tuple(int(part) for part in proof["snapshot"]["scope_version"].split(".")) < NO_HEAD_GIT_SCOPE_SINCE
            and _inside_git_worktree(repo_root.resolve())
        ):
            raise ValueError(
                "architecture proof snapshot does not match the current repository and was sealed before "
                "Architect 1.0.1 limited no-HEAD Git snapshots to tracked and non-ignored untracked files; "
                "reseal the receipt-free decision with Architect"
            )
        raise ValueError("architecture proof snapshot does not match the current repository")
    return decision


def _with_receipt(body: str, repo_root: Path) -> str:
    with_proof = body + _proof_line(_snapshot(repo_root)) + "\n"
    digest = hashlib.sha256(with_proof.encode("utf-8")).hexdigest()
    return f"{with_proof}<!-- architecture: {ARCHITECT_VERSION}; sha256: {digest} -->\n"


def _snapshot_shape(value: object) -> bool:
    if not isinstance(value, dict):
        return False

    def digest(item: object) -> bool:
        return isinstance(item, str) and re.fullmatch(r"[0-9a-f]{64}", item) is not None

    if value.get("kind") == "filesystem":
        return (
            set(value) == {"kind", "scope_version", "project_root", "fingerprint"}
            and compatible_version(value.get("scope_version"), ARCHITECT_VERSION)
            and isinstance(value["project_root"], str)
            and digest(value["fingerprint"])
        )
    if value.get("kind") != "git" or set(value) != {
        "kind",
        "scope_version",
        "project_root",
        "repository_id",
        "revision",
        "dirty",
        "dirty_fingerprint",
    }:
        return False
    return (
        compatible_version(value.get("scope_version"), ARCHITECT_VERSION)
        and all(isinstance(value[key], str) and bool(value[key]) for key in ("project_root", "repository_id"))
        and isinstance(value["revision"], str)
        and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value["revision"]) is not None
        and type(value["dirty"]) is bool
        and (digest(value["dirty_fingerprint"]) if value["dirty"] else value["dirty_fingerprint"] is None)
    )


def _validate_planning_namespace(repo_root: Path) -> None:
    workspace = repo_root.joinpath(*BLUEPRINT_WORKSPACE_PARTS)
    if workspace.is_symlink() or workspace.resolve() != workspace.absolute():
        raise ValueError("architecture snapshot cannot exclude a symlinked Blueprint namespace")
    if not workspace.exists():
        return
    if not workspace.is_dir():
        raise ValueError("architecture snapshot cannot exclude project-owned Blueprint content")
    for task in workspace.iterdir():
        if (
            task.is_symlink()
            or task.resolve() != task.absolute()
            or not task.is_dir()
            or not re.fullmatch(r"[^\W_]+(?:-[^\W_]+)*", task.name.casefold())
        ):
            raise ValueError("architecture snapshot cannot exclude unsafe Blueprint task content")
        if not (task / "request.md").is_file():
            raise ValueError("architecture snapshot cannot exclude a task without request.md")
        for entry in task.iterdir():
            if (
                entry.name not in {"request.md", "blueprint.md"}
                or entry.is_symlink()
                or entry.resolve() != entry.absolute()
                or not entry.is_file()
            ):
                raise ValueError("architecture snapshot cannot exclude project-owned Blueprint task content")


def read_primary(path: Path, repo_root: Path) -> bytes:
    """Read one sealed .first-four-hours/architectures/<slug>/architecture.md; never publish or repair it."""
    required = f"architecture source must be the target repository's {WORKSPACE_DIR}/<slug>/architecture.md, reached without links"
    if not path.is_absolute() or path.name != "architecture.md" or path.is_symlink():
        raise ValueError(required)
    resolved = path.resolve(strict=True)
    try:
        relative = resolved.relative_to(repo_root.resolve()).parts
    except ValueError:
        raise ValueError(required) from None
    if len(relative) != 4 or relative[:2] != WORKSPACE_PARTS or relative != Path(os.path.abspath(path)).parts[-4:]:
        raise ValueError(required)
    if resolved.name != "architecture.md" or not resolved.is_file():
        raise ValueError("architecture source must be a regular architecture.md")
    if any(entry != resolved for entry in resolved.parent.iterdir()):
        raise ValueError("architecture source directory contains other artifacts")
    return resolved.read_bytes()


def verify_handoff(data: bytes, repo_root: Path, *, check_sources: bool = True) -> None:
    """Verify declared truth. Semantic actionability remains Blueprint-owned."""
    text = data.decode("utf-8")
    if not RECEIPT_RE.fullmatch(text.removesuffix("\n").rpartition("\n")[2].rstrip("\r")):
        raise ValueError("architecture input requires an exact supported receipt")
    body = _receipt_free(text, repo_root if check_sources else None)
    if not check_sources:
        return
    parsed, diagnostics = validate_handoff(body, repo_root, require_evidence_hashes=True)
    if diagnostics:
        raise ValueError("architecture evidence/shape invalid: " + "; ".join(item.message for item in diagnostics))

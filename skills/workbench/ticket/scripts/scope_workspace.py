"""Prepare the repository-local ignored .first-four-hours/ticket-scopes/<slug>/ handoff workspace."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ARTIFACT_ROOT = ".first-four-hours"
WORKSPACE_PARTS = (ARTIFACT_ROOT, "ticket-scopes")
WORKSPACE_DIR = "/".join(WORKSPACE_PARTS)
WORKSPACE_RULE = f"/{WORKSPACE_DIR}/"
RESULT_FILENAME = "ticket-scope.md"
GIT_TIMEOUT_SECONDS = 30


class WorkspaceError(Exception):
    """A named workspace defect with its smallest credible repair."""


def scope_slug(inputs: dict[str, Any], work_item: int | str) -> str:
    backend = inputs["backend"]
    locator = inputs["local_store"] if backend == "local" else inputs["repository"]
    raw = f"{backend}-{locator}-{work_item}".strip().casefold()
    readable = re.sub(r"-+", "-", "".join(c if c.isalnum() else "-" for c in raw)).strip("-")
    # Normalizing is many-to-one, so a digest of the exact identity keeps each work item's path distinct.
    # GitHub repository names are case-insensitive; local store paths are compared exactly.
    identity = json.dumps([backend, locator.casefold() if backend == "github" else locator, str(work_item)])
    return f"{readable}-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:12]}"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT_SECONDS, check=False
    )


def _is_link(path: Path) -> bool:
    """Return whether path itself is a symlink or Windows reparse point such as a junction."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    reparse = getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    return stat.S_ISLNK(info.st_mode) or bool(reparse)


def _git_exclude(root: Path) -> Path:
    """Return the worktree-local exclude path."""
    try:
        probe = _git(root, "rev-parse", "--is-inside-work-tree", "--show-toplevel", "--git-path", "info/exclude")
    except FileNotFoundError:
        raise WorkspaceError("repo-root must be a Git worktree; ticket-scope.md binds a Git checkout") from None
    probe_lines = probe.stdout.strip().splitlines()
    if probe.returncode == 0 and len(probe_lines) == 3 and probe_lines[0].strip() == "true":
        # One process answers all three questions in a worktree; anything else replays the separate checks.
        top_text = probe_lines[1].strip()
        if Path(top_text).resolve() != root:
            raise WorkspaceError(f"repo-root must be the Git worktree root (expected {top_text}); pass the top-level directory")
        result = probe
        raw = probe_lines[2].strip()
    else:
        try:
            inside = _git(root, "rev-parse", "--is-inside-work-tree")
        except FileNotFoundError:
            raise WorkspaceError("repo-root must be a Git worktree; ticket-scope.md binds a Git checkout") from None
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            raise WorkspaceError("repo-root must be a Git worktree; ticket-scope.md binds a Git checkout")
        top = _git(root, "rev-parse", "--show-toplevel")
        if top.returncode != 0 or Path(top.stdout.strip()).resolve() != root:
            raise WorkspaceError(f"repo-root must be the Git worktree root (expected {top.stdout.strip()}); pass the top-level directory")
        result = _git(root, "rev-parse", "--git-path", "info/exclude")
        raw = result.stdout.strip()
    if result.returncode != 0 or not raw:
        raise WorkspaceError("Git repository has no resolvable worktree-local info/exclude path; repair Git metadata and retry")
    exclude = Path(raw)
    if not exclude.is_absolute():
        exclude = root / exclude
    resolved_exclude = exclude.resolve(strict=False)
    # Resolving changes the path exactly when the file or a directory on its path is a link.
    through_link = os.path.normcase(str(resolved_exclude)) != os.path.normcase(os.path.abspath(exclude))
    if _is_link(exclude) or through_link or exclude.exists() and not exclude.is_file():
        raise WorkspaceError(
            f"Git exclude path is linked or not a regular file: {exclude}; repair it before sealing"
        )
    exclude = resolved_exclude
    tracked = _git(root, "ls-files", "--", f":(icase){WORKSPACE_DIR}")
    if tracked.returncode != 0:
        raise WorkspaceError(f"cannot establish whether the {WORKSPACE_DIR}/ namespace is tracked; repair Git metadata and retry")
    if tracked.stdout.strip():
        raise WorkspaceError(
            f"the {WORKSPACE_DIR}/ namespace already contains tracked project files; resolve that project conflict before sealing"
        )
    return exclude


def _ensure_ignored(root: Path, exclude: Path, relative: str) -> None:
    def ignored() -> int:
        return _git(root, "check-ignore", "--no-index", "--quiet", "--", relative).returncode

    status = ignored()
    if status == 0:
        return
    if status != 1:
        raise WorkspaceError("cannot query the repository ignore boundary; repair Git ignore metadata and retry")
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    lines = {line.strip() for line in existing.replace("\r\n", "\n").splitlines()}
    if WORKSPACE_RULE not in lines and f"{WORKSPACE_DIR}/" not in lines:
        separator = "" if not existing or existing.endswith(("\n", "\r")) else "\n"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=exclude.parent, delete=False) as temp:
            temp.write(existing + separator + WORKSPACE_RULE + "\n")
        os.replace(temp.name, exclude)
    if ignored() != 0:
        raise WorkspaceError(
            f"the local Git exclude does not cover {relative}; repair the negating ignore rule and retry"
        )


def prepare_workspace(repo_root: Path, slug: str) -> Path:
    root = repo_root.resolve()
    if not root.is_dir():
        raise WorkspaceError(f"repo-root is not an existing directory: {repo_root}")
    exclude = _git_exclude(root)
    relative = f"{WORKSPACE_DIR}/{slug}/{RESULT_FILENAME}"
    for path in (root / ARTIFACT_ROOT, root / WORKSPACE_DIR, root / WORKSPACE_DIR / slug):
        if _is_link(path) or path.exists() and not path.is_dir():
            raise WorkspaceError(f"Ticket workspace entry is not a real directory: {path}; replace it with a directory")
    _ensure_ignored(root, exclude, relative)
    destination = root / relative
    if _is_link(destination) or destination.exists() and not destination.is_file():
        raise WorkspaceError(f"{destination} is not a regular file; remove it before sealing")
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def existing_handoff(repo_root: Path, slug: str) -> Path | None:
    root = repo_root.resolve()
    try:
        inside = _git(root, "rev-parse", "--is-inside-work-tree")
    except FileNotFoundError:
        inside = None
    if inside is None or inside.returncode != 0 or inside.stdout.strip() != "true":
        return None  # not a Git worktree, so no sealed handoff can exist for it
    # Inside a worktree, check the root first, so a subdirectory root fails closed even where no namespace exists.
    _git_exclude(root)
    if not os.path.lexists(root / ARTIFACT_ROOT):
        return None
    for path in (root / ARTIFACT_ROOT, root / WORKSPACE_DIR, root / WORKSPACE_DIR / slug):
        if not os.path.lexists(path):
            return None
        if _is_link(path) or not path.is_dir():
            raise WorkspaceError(f"Ticket workspace entry is not a real directory: {path}; replace it with a directory")
    destination = root / WORKSPACE_DIR / slug / RESULT_FILENAME
    if not os.path.lexists(destination):
        return None
    if _is_link(destination) or not destination.is_file():
        raise WorkspaceError(f"{destination} is not a regular file; remove it before sealing")
    return destination

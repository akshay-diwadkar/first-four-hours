"""Prepare the repository-local ignored .first-four-hours/routes/<slug>/ workspace."""

from __future__ import annotations

import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

ARTIFACT_ROOT = ".first-four-hours"
WORKSPACE_PARTS = (ARTIFACT_ROOT, "routes")
WORKSPACE_DIR = "/".join(WORKSPACE_PARTS)
WORKSPACE_RULE = f"/{WORKSPACE_DIR}/"
RESULT_FILENAME = "route.md"
GIT_TIMEOUT_SECONDS = 30


class WorkspaceError(Exception):
    """A named workspace defect with its smallest credible repair."""


def normalize_slug(name: str) -> str:
    """Normalize one human route name to a safe lower-kebab path segment."""
    normalized = name.strip().casefold()
    slug = re.sub(r"-+", "-", "".join(character if character.isalnum() else "-" for character in normalized)).strip("-")
    if not slug:
        raise WorkspaceError("route slug must contain at least one letter or digit; choose a short descriptive slug")
    return slug


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


def _git_exclude(root: Path) -> Path | None:
    """Return the worktree-local exclude path, or None for a non-Git target."""
    try:
        probe = _git(root, "rev-parse", "--is-inside-work-tree", "--show-toplevel", "--git-path", "info/exclude")
    except FileNotFoundError:
        if os.path.lexists(root / ".git"):
            raise WorkspaceError("git is unavailable for a Git target; install Git and retry") from None
        return None
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
            if os.path.lexists(root / ".git"):
                raise WorkspaceError("git is unavailable for a Git target; install Git and retry") from None
            return None
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return None
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
    namespace = root / WORKSPACE_DIR
    if _is_link(namespace) or namespace.exists() and not namespace.is_dir():
        raise WorkspaceError(f"Router workspace entry is not a real directory: {namespace}; replace it with a directory")
    if namespace.is_dir() and any(namespace.iterdir()):
        raise WorkspaceError(
            f"{WORKSPACE_DIR}/ already holds files Git does not ignore; move them before sealing"
        )
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


def prepare_workspace(repo_root: Path, slug: str) -> tuple[Path, bool]:
    """Create .first-four-hours/routes/<slug>/, ignore it locally for Git targets, and return (output path, git_ignored)."""
    root = repo_root.resolve()
    if not root.is_dir():
        raise WorkspaceError(f"repo-root is not an existing directory: {repo_root}")
    normalized = normalize_slug(slug)
    exclude = _git_exclude(root)
    relative = f"{WORKSPACE_DIR}/{normalized}/{RESULT_FILENAME}"
    for path in (root / ARTIFACT_ROOT, root / WORKSPACE_DIR, root / WORKSPACE_DIR / normalized):
        if _is_link(path) or path.exists() and not path.is_dir():
            raise WorkspaceError(f"Router workspace entry is not a real directory: {path}; replace it with a directory")
    if exclude is not None:
        _ensure_ignored(root, exclude, relative)
    destination = root / relative
    if _is_link(destination) or destination.exists() and not destination.is_file():
        raise WorkspaceError(f"{destination} is not a regular file; remove it before sealing")
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination, exclude is not None

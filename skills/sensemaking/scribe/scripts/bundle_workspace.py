"""Prepare the ignored .first-four-hours/scribes/<slug>/ audit workspace and check where the document bundle lives."""

from __future__ import annotations

import errno
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

from _document_contract import ARTIFACT_ROOT, AUDIT_FILENAME, BUNDLE_FILENAME, WORKSPACE_DIR, WORKSPACE_PARTS

WORKSPACE_RULE = f"/{WORKSPACE_DIR}/"
GIT_TIMEOUT_SECONDS = 30


class WorkspaceError(Exception):
    """A named workspace defect with its smallest credible repair."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def normalize_slug(name: str) -> str:
    """Normalize one human audit name to a safe lower-kebab path segment."""
    normalized = name.strip().casefold()
    slug = re.sub(r"-+", "-", "".join(character if character.isalnum() else "-" for character in normalized)).strip("-")
    if not slug:
        raise WorkspaceError("invalid_slug", "audit slug must contain at least one letter or digit; choose a short descriptive slug")
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


def _slug_failure(path: Path, normalized: str, exc: OSError) -> WorkspaceError | None:
    """Return invalid_slug for a slug-directory failure caused by the slug's name or length, else None."""
    if not isinstance(exc, FileNotFoundError) and exc.errno not in (errno.ENAMETOOLONG, errno.EINVAL):
        return None
    return WorkspaceError(
        "invalid_slug",
        f"cannot use {path} ({exc.strerror or exc}): the slug {normalized} is too long or otherwise "
        "unusable on this system; choose a shorter or different slug",
    )


def _git_metadata(root: Path) -> Path | None:
    """Return the Git metadata path at or above root, or None when the target has no Git metadata."""
    for path in (root, *root.parents):
        if path.name.casefold() == ".git":
            return path
        if os.path.lexists(path / ".git"):
            return path / ".git"
        if (path / "HEAD").is_file() and (path / "objects").is_dir() and (path / "refs").is_dir():
            return path
    return None


def _git_exclude(root: Path) -> Path | None:
    """Return the worktree-local exclude path, or None only for a target with no Git metadata."""
    try:
        probe = _git(root, "rev-parse", "--is-inside-work-tree", "--show-toplevel", "--git-path", "info/exclude")
    except FileNotFoundError:
        metadata = _git_metadata(root)
        if metadata is not None:
            raise WorkspaceError(
                "namespace_unsafe", f"git is unavailable for the Git target at {metadata}; install Git and retry"
            ) from None
        return None
    probe_lines = probe.stdout.strip().splitlines()
    if probe.returncode == 0 and len(probe_lines) == 3 and probe_lines[0].strip() == "true":
        # One process answers all three questions in a worktree; anything else replays the separate checks.
        top_text = probe_lines[1].strip()
        if Path(top_text).resolve() != root:
            raise WorkspaceError(
                "namespace_unsafe",
                f"repo-root must be the Git worktree root (expected {top_text}); pass the top-level directory",
            )
        result = probe
        raw = probe_lines[2].strip()
    else:
        try:
            inside = _git(root, "rev-parse", "--is-inside-work-tree")
        except FileNotFoundError:
            metadata = _git_metadata(root)
            if metadata is not None:
                raise WorkspaceError(
                    "namespace_unsafe", f"git is unavailable for the Git target at {metadata}; install Git and retry"
                ) from None
            return None
        if inside.returncode == 0 and inside.stdout.strip() != "true":
            raise WorkspaceError(
                "namespace_unsafe",
                f"repo-root is Git metadata or a bare repository, not a worktree: {root}; pass the worktree top-level directory",
            )
        if inside.returncode != 0:
            metadata = _git_metadata(root)
            if metadata is not None:
                reason = "; ".join(inside.stderr.strip().splitlines()) or "no diagnostic output"
                raise WorkspaceError(
                    "namespace_unsafe",
                    f"Git metadata exists at {metadata}, but git cannot resolve the repository for {root} ({reason}); "
                    "repair that repository, for example its ownership trust or a corrupt HEAD, or remove the stray metadata, and retry",
                )
            return None
        top = _git(root, "rev-parse", "--show-toplevel")
        if top.returncode != 0 or Path(top.stdout.strip()).resolve() != root:
            raise WorkspaceError(
                "namespace_unsafe",
                f"repo-root must be the Git worktree root (expected {top.stdout.strip()}); pass the top-level directory",
            )
        result = _git(root, "rev-parse", "--git-path", "info/exclude")
        raw = result.stdout.strip()
    if result.returncode != 0 or not raw:
        raise WorkspaceError(
            "namespace_unsafe", "Git repository has no resolvable worktree-local info/exclude path; repair Git metadata and retry"
        )
    exclude = Path(raw)
    if not exclude.is_absolute():
        exclude = root / exclude
    resolved_exclude = exclude.resolve(strict=False)
    # Resolving changes the path exactly when the file or a directory on its path is a link.
    through_link = os.path.normcase(str(resolved_exclude)) != os.path.normcase(os.path.abspath(exclude))
    if _is_link(exclude) or through_link or exclude.exists() and not exclude.is_file():
        raise WorkspaceError(
            "namespace_unsafe", f"Git exclude path is linked or not a regular file: {exclude}; repair it before preparing"
        )
    exclude = resolved_exclude
    tracked = _git(root, "ls-files", "--", f":(icase){WORKSPACE_DIR}")
    if tracked.returncode != 0:
        raise WorkspaceError(
            "namespace_unsafe", f"cannot establish whether the {WORKSPACE_DIR}/ namespace is tracked; repair Git metadata and retry"
        )
    if tracked.stdout.strip():
        raise WorkspaceError(
            "namespace_unsafe",
            f"the {WORKSPACE_DIR}/ namespace already contains tracked project files; resolve that project conflict before preparing",
        )
    return exclude


def _ensure_ignored(root: Path, exclude: Path, relative: str) -> None:
    def ignored() -> int:
        return _git(root, "check-ignore", "--no-index", "--quiet", "--", relative).returncode

    status = ignored()
    if status == 0:
        return
    if status != 1:
        raise WorkspaceError("namespace_unsafe", "cannot query the repository ignore boundary; repair Git ignore metadata and retry")
    existing = exclude.read_bytes() if exclude.exists() else b""
    lines = {line.strip() for line in existing.splitlines()}
    if WORKSPACE_RULE.encode() not in lines and f"{WORKSPACE_DIR}/".encode() not in lines:
        newline = b"\r\n" if b"\r\n" in existing else b"\n"
        if not existing or existing.endswith(b"\n"):
            separator = b""
        elif existing.endswith(b"\r"):
            separator = b"\n"
        else:
            separator = newline
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("wb", dir=exclude.parent, delete=False) as temp:
            temp.write(existing + separator + WORKSPACE_RULE.encode() + newline)
        os.replace(temp.name, exclude)
    if ignored() != 0:
        raise WorkspaceError(
            "namespace_unsafe", f"the local Git exclude does not cover {relative}; repair the negating ignore rule and retry"
        )


def _check_entries(root: Path, normalized: str) -> None:
    """Refuse linked, file, or special namespace entries before any Git ignore query."""
    artifact_root = root / ARTIFACT_ROOT
    namespace = root / WORKSPACE_DIR
    for path in (artifact_root, namespace, namespace / normalized):
        try:
            if _is_link(path) or path.is_file() or (path in (artifact_root, namespace) and path.exists() and not path.is_dir()):
                raise WorkspaceError("namespace_unsafe", f"Scribe workspace entry is not a real directory: {path}; replace it with a directory")
            if path.exists() and not path.is_dir():
                raise WorkspaceError(
                    "invalid_slug", f"{path} is a reserved or special path on this system, not a directory; choose another slug"
                )
        except OSError as exc:
            slug_error = _slug_failure(path, normalized, exc) if path not in (artifact_root, namespace) else None
            if slug_error is None:
                raise
            raise slug_error from exc


def prepare_workspace(repo_root: Path, slug: str) -> tuple[Path, bool]:
    """Create .first-four-hours/scribes/<slug>/, ignore it locally for Git targets, and return (audit report path, git_ignored)."""
    root = repo_root.resolve()
    if not root.is_dir():
        raise WorkspaceError("namespace_unsafe", f"repo-root is not an existing directory: {repo_root}")
    normalized = normalize_slug(slug)
    exclude = _git_exclude(root)
    relative = f"{WORKSPACE_DIR}/{normalized}/{AUDIT_FILENAME}"
    _check_entries(root, normalized)
    destination = root / relative
    if _is_link(destination) or destination.exists() and not destination.is_file():
        raise WorkspaceError("namespace_unsafe", f"{destination} is not a regular file; remove it before preparing")
    if exclude is not None:
        _ensure_ignored(root, exclude, relative)
    (root / WORKSPACE_DIR).mkdir(parents=True, exist_ok=True)
    try:
        destination.parent.mkdir(exist_ok=True)
    except OSError as exc:
        slug_error = _slug_failure(destination.parent, normalized, exc)
        if slug_error is None:
            raise
        raise slug_error from exc
    if _is_link(destination.parent) or not destination.parent.is_dir():
        raise WorkspaceError(
            "invalid_slug",
            f"cannot create {destination.parent}: the slug {normalized} names a reserved or unusable path on this system; "
            "choose another slug",
        )
    if not destination.exists():
        try:
            destination.open("xb").close()
        except OSError as exc:
            slug_error = _slug_failure(destination, normalized, exc)
            if slug_error is None:
                raise
            raise slug_error from exc
        destination.unlink()
    return destination, exclude is not None


def in_namespace(repo_root: Path, path: Path) -> bool:
    """Return whether path lies inside the support namespace of repo_root."""
    try:
        parts = path.resolve().relative_to(repo_root.resolve()).parts
    except ValueError:
        return False
    return tuple(part.casefold() for part in parts[:2]) == WORKSPACE_PARTS


def require_external_bundle(repo_root: Path, bundle: Path) -> Path:
    """Return the resolved bundle path, refusing a bundle inside the target repository."""
    path = bundle.resolve(strict=True)
    if repo_root.resolve() in path.parents:
        raise WorkspaceError(
            "bundle_in_repository",
            f"{BUNDLE_FILENAME} must be outside the target repository: {path}; "
            "write it in a temporary directory outside the repository",
        )
    return path

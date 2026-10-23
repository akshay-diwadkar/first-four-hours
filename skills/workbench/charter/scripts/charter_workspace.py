"""Prepare the repository-local ignored .first-four-hours/charters/<slug>/charter.md workspace."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _diagnostic_contract import normalize_diagnostic  # noqa: E402

ARTIFACT_ROOT = ".first-four-hours"
WORKSPACE_PARTS = (ARTIFACT_ROOT, "charters")
WORKSPACE_DIR = "/".join(WORKSPACE_PARTS)
WORKSPACE_RULE = f"/{WORKSPACE_DIR}/"
RESULT_FILENAME = "charter.md"
GIT_TIMEOUT_SECONDS = 30
RESERVED_NAMES = frozenset({"con", "prn", "aux", "nul", *(f"com{n}" for n in range(1, 10)), *(f"lpt{n}" for n in range(1, 10))})


class WorkspaceError(Exception):
    """A named workspace defect with its smallest credible repair."""

    def __init__(self, code: str, message: str, action: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.action = action


def normalize_slug(raw: str) -> str:
    """Return the safe lower-kebab slug for raw, or refuse it; distinct names never collapse silently."""
    value = raw.strip()
    slug = ""
    if re.fullmatch(r"[A-Za-z0-9 -]+", value):
        slug = re.sub(r"-+", "-", value.lower().replace(" ", "-")).strip("-")
    if not slug or len(slug) > 64 or slug in RESERVED_NAMES:
        raise WorkspaceError(
            "charter.slug_unsafe",
            f"charter slug {raw!r} is not a safe project name: use 1-64 ASCII letters, digits, spaces, and hyphens, "
            "with at least one letter or digit and no reserved device name",
            "choose a different slug with the user; never rewrite it",
        )
    return slug


def scaffold(slug: str) -> str:
    return (
        f"# Charter — {slug}\n\n"
        "## Purpose\n\n"
        "Unagreed.\n\n"
        "## Agreed\n\n"
        "## Unsettled\n\n"
        "## Revisions\n\n"
        "## Authority\n\n"
        "- Owner: this file owns this definition until a publication is verified.\n"
        "- State: settling\n"
    )


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
            raise WorkspaceError(
                "charter.git_unavailable", "git is unavailable for a Git target", "install Git and retry"
            ) from None
        return None
    probe_lines = probe.stdout.strip().splitlines()
    if probe.returncode == 0 and len(probe_lines) == 3 and probe_lines[0].strip() == "true":
        # One process answers all three questions in a worktree; anything else replays the separate checks.
        top_text = probe_lines[1].strip()
        if Path(top_text).resolve() != root:
            raise WorkspaceError(
                "charter.repo_root_invalid",
                f"repo-root must be the Git worktree root (expected {top_text})",
                "pass the top-level directory",
            )
        result = probe
        raw = probe_lines[2].strip()
    else:
        try:
            inside = _git(root, "rev-parse", "--is-inside-work-tree")
        except FileNotFoundError:
            if os.path.lexists(root / ".git"):
                raise WorkspaceError(
                    "charter.git_unavailable", "git is unavailable for a Git target", "install Git and retry"
                ) from None
            return None
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return None
        top = _git(root, "rev-parse", "--show-toplevel")
        if top.returncode != 0 or Path(top.stdout.strip()).resolve() != root:
            raise WorkspaceError(
                "charter.repo_root_invalid",
                f"repo-root must be the Git worktree root (expected {top.stdout.strip()})",
                "pass the top-level directory",
            )
        result = _git(root, "rev-parse", "--git-path", "info/exclude")
        raw = result.stdout.strip()
    if result.returncode != 0 or not raw:
        raise WorkspaceError(
            "charter.git_failed",
            "Git repository has no resolvable worktree-local info/exclude path",
            "repair Git metadata and retry",
        )
    exclude = Path(raw)
    if not exclude.is_absolute():
        exclude = root / exclude
    resolved_exclude = exclude.resolve(strict=False)
    # Resolving changes the path exactly when the file or a directory on its path is a link.
    through_link = os.path.normcase(str(resolved_exclude)) != os.path.normcase(os.path.abspath(exclude))
    if _is_link(exclude) or through_link or exclude.exists() and not exclude.is_file():
        raise WorkspaceError(
            "charter.exclude_unsafe",
            f"Git exclude path is linked or not a regular file: {exclude}",
            "repair the exclude path and retry",
        )
    exclude = resolved_exclude
    tracked = _git(root, "ls-files", "--", f":(icase){WORKSPACE_DIR}")
    if tracked.returncode != 0:
        raise WorkspaceError(
            "charter.git_failed",
            f"cannot establish whether the {WORKSPACE_DIR}/ namespace is tracked",
            "repair Git metadata and retry",
        )
    if tracked.stdout.strip():
        raise WorkspaceError(
            "charter.namespace_tracked",
            f"the {WORKSPACE_DIR}/ namespace already contains tracked project files",
            "resolve that project conflict before preparing a charter",
        )
    return exclude


def _ensure_ignored(root: Path, exclude: Path, relative: str) -> None:
    def ignored() -> int:
        return _git(root, "check-ignore", "--no-index", "--quiet", "--", relative).returncode

    status = ignored()
    if status == 0:
        return
    if status != 1:
        raise WorkspaceError(
            "charter.git_failed", "cannot query the repository ignore boundary", "repair Git ignore metadata and retry"
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
            "charter.ignore_failed",
            f"the local Git exclude does not cover {relative}",
            "repair the negating ignore rule and retry",
        )


def _unsafe(path: Path) -> WorkspaceError:
    return WorkspaceError(
        "charter.workspace_unsafe",
        f"Charter workspace entry is a link or the wrong kind of entry: {path}",
        "replace it with a real directory (or regular file) or remove it",
    )


def _resolve_root(repo_root: Path) -> Path:
    root = repo_root.resolve()
    if not root.is_dir():
        raise WorkspaceError(
            "charter.repo_root_invalid", f"repo-root is not an existing directory: {repo_root}", "pass an existing directory"
        )
    return root


def prepare_workspace(repo_root: Path, slug: str) -> dict[str, object]:
    """Create .first-four-hours/charters/<slug>/charter.md once, ignore it locally for Git targets, never replace it."""
    root = _resolve_root(repo_root)
    normalized = normalize_slug(slug)
    exclude = _git_exclude(root)
    relative = f"{WORKSPACE_DIR}/{normalized}/{RESULT_FILENAME}"
    for path in (root / ARTIFACT_ROOT, root / WORKSPACE_DIR, root / WORKSPACE_DIR / normalized):
        if _is_link(path) or path.exists() and not path.is_dir():
            raise _unsafe(path)
    if exclude is not None:
        _ensure_ignored(root, exclude, relative)
    destination = root / ARTIFACT_ROOT / "charters" / normalized / RESULT_FILENAME
    if _is_link(destination) or destination.exists() and not destination.is_file():
        raise _unsafe(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    status = "resumed"
    if not destination.exists():
        try:
            with open(destination, "x", encoding="utf-8", newline="\n") as handle:
                handle.write(scaffold(normalized))
            status = "created"
        except FileExistsError:
            status = "resumed"
    return {"status": status, "path": str(destination), "slug": normalized, "git_ignored": exclude is not None}


def charter_path(repo_root: Path, slug: str) -> Path:
    """Locate an existing charter without writing anything."""
    root = _resolve_root(repo_root)
    normalized = normalize_slug(slug)
    _git_exclude(root)
    directories = (root / ARTIFACT_ROOT, root / WORKSPACE_DIR, root / WORKSPACE_DIR / normalized)
    destination = directories[2] / RESULT_FILENAME
    for path in directories:
        if not os.path.lexists(path):
            raise _missing()
        if _is_link(path) or not path.is_dir():
            raise _unsafe(path)
    if not os.path.lexists(destination):
        raise _missing()
    if _is_link(destination) or not destination.is_file():
        raise _unsafe(destination)
    return destination


def _missing() -> WorkspaceError:
    return WorkspaceError("charter.missing", "no charter exists for this slug", "run prepare first")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--slug", required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare_workspace(Path(args.repo_root), args.slug)
    except WorkspaceError as exc:
        diagnostic = normalize_diagnostic(
            {"code": exc.code, "message": exc.message, "required_action": exc.action},
            skill="charter",
            phase="prepare",
            artifact="charter",
            path=args.repo_root,
        )
        print(json.dumps([diagnostic], sort_keys=True, separators=(",", ":")))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Small, read-only workspace probes shared by readers and renderers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .types import Workspace


def _run_git(root: Path, args: list[str], timeout: float = 10.0) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def git_root(root: str | Path) -> Path | None:
    root_p = Path(root).resolve()
    code, out = _run_git(root_p, ["rev-parse", "--show-toplevel"])
    if code != 0:
        return None
    value = out.strip()
    return Path(value).resolve() if value else None


def git_root_fast(root: str | Path) -> Path | None:
    """Walk upwards for ``.git`` before paying for a git subprocess."""
    current = Path(root).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def workspace_info(root: str | Path) -> Workspace:
    root_p = Path(root).resolve()
    info = Workspace(root=str(root_p))
    git_dir = git_root_fast(root_p)
    if git_dir is None:
        code, out = _run_git(root_p, ["rev-parse", "--show-toplevel"])
        if code == 0 and out.strip():
            git_dir = Path(out.strip()).resolve()
    if git_dir is None:
        return info

    info.git_root = str(git_dir)
    code, head = _run_git(root_p, ["rev-parse", "--short", "HEAD"])
    if code == 0:
        info.head = head.strip()
    code, branch = _run_git(root_p, ["rev-parse", "--abbrev-ref", "HEAD"])
    if code == 0:
        info.branch = branch.strip() or None
    code, status = _run_git(root_p, ["status", "--porcelain=v1", "-z", "--untracked-files=normal"])
    if code == 0:
        entries = [e for e in status.split("\0") if e]
        info.changed_count = len(entries)
        info.dirty = bool(entries)
    return info


def git_available() -> bool:
    return shutil_which_git() is not None


def shutil_which_git() -> str | None:
    from shutil import which

    return which("git")


def path_is_within(root: Path, path: Path) -> bool:
    try:
        return os.path.commonpath([os.path.normcase(str(root)), os.path.normcase(str(path))]) == os.path.normcase(str(root))
    except ValueError:
        return False

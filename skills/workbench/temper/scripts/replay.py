"""Copy a repository, run selections in the copy, and apply mutants there only."""

from __future__ import annotations

import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType
from typing import Any

TAIL_LIMIT = 300


class ReplayError(Exception):
    """A named replay defect with its smallest credible repair."""


def _contains(outer: Path, inner: Path) -> bool:
    return outer == inner or outer in inner.parents


def _clear_readonly(function: Callable[[str], object], path: str, _info: object) -> None:
    os.chmod(path, stat.S_IWRITE)
    function(path)


class RepositoryCopy:
    """Context manager returning a throwaway copy of the repository outside it."""

    def __init__(self, repo_root: Path, copy_git: bool, copy_exclude: list[str]) -> None:
        self.repo_root = repo_root
        self.copy_git = copy_git
        self.copy_exclude = set(copy_exclude)
        self.temp: Path | None = None

    def __enter__(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="temper-"))
        self.temp = temp
        try:
            real_temp = temp.resolve()
            root = self.repo_root.resolve()
            if _contains(root, real_temp) or _contains(real_temp, root):
                raise ReplayError(
                    f"the temporary folder {real_temp} and the repository {root} contain each other; "
                    "point TMPDIR, TEMP, or TMP at a folder outside the repository"
                )
            git = root / ".git"
            if self.copy_git and (git.is_symlink() or not git.is_dir()):
                raise ReplayError("copy_git is set but .git is not a real directory (a worktree or submodule?); set copy_git to false")
            excluded = self.copy_exclude
            copy_git = self.copy_git

            def ignore(directory: str, names: list[str]) -> set[str]:
                skipped: set[str] = set()
                base = Path(directory)
                for name in names:
                    if name == "__pycache__":
                        skipped.add(name)
                        continue
                    relative = (base / name).relative_to(root).as_posix() if _contains(root, base) else name
                    if relative == ".git" and not copy_git:
                        skipped.add(name)
                    elif relative in excluded:
                        skipped.add(name)
                return skipped

            shutil.copytree(root, temp / "repo", symlinks=True, ignore=ignore)
        except BaseException:
            shutil.rmtree(temp, onerror=_clear_readonly, ignore_errors=True)
            raise
        return temp / "repo"

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        temp = self.temp
        if temp is None:
            return
        try:
            shutil.rmtree(temp, onerror=_clear_readonly)
        except OSError as error:
            if exc_type is None:
                raise ReplayError(f"could not remove the temporary copy {temp}; delete it by hand") from error
        if exc_type is None and temp.exists():
            raise ReplayError(f"could not remove the temporary copy {temp}; delete it by hand")


def _tail(output: str) -> str:
    lines = [line for line in output.splitlines() if line.strip()]
    return lines[-1][:TAIL_LIMIT] if lines else ""


def run_selection(copy_root: Path, name: str, selection: dict[str, Any]) -> tuple[str, float, str]:
    """Run one selection in the copy and return (status, seconds, tail)."""
    argv = selection["argv"]
    options: dict[str, Any] = {}
    if sys.platform == "win32":
        options["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        options["start_new_session"] = True
    start = time.monotonic()
    try:
        process = subprocess.Popen(
            argv,
            cwd=copy_root,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            **options,
        )
    except OSError as error:
        raise ReplayError(f"selection `{name}` could not launch {argv[0]!r}: {error}; fix its argv") from error
    status = "passed"
    try:
        output, _ = process.communicate(timeout=selection["timeout_seconds"])
        if process.returncode != 0:
            status = "failed"
    except subprocess.TimeoutExpired:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False)
        else:
            getattr(os, "killpg")(process.pid, getattr(signal, "SIGKILL"))
        output, _ = process.communicate()
        status = "timeout"
    return status, time.monotonic() - start, _tail(output or "")


@contextmanager
def mutated(copy_root: Path, mutant: dict[str, Any]) -> Iterator[None]:
    """Apply one mutant to the copy and restore the original bytes on exit."""
    path = copy_root / mutant["path"]
    if path.is_symlink() or not path.is_file() or not _contains(copy_root.resolve(), path.resolve()):
        raise ReplayError(f"mutant path {mutant['path']} must be a regular file inside the copy, not a link")
    original = path.read_bytes()
    text = original.decode("utf-8")
    if text.count(mutant["old"]) != 1:
        raise ReplayError(f"the mutant's old text is missing or repeated in {mutant['path']}; make it occur exactly once")
    previous = path.stat().st_mtime_ns

    def stamp(before: int) -> None:
        moment = max(time.time_ns(), before + 2_000_000_000)
        os.utime(path, ns=(moment, moment))

    os.chmod(path, path.stat().st_mode | stat.S_IWRITE | stat.S_IREAD)
    path.write_bytes(text.replace(mutant["old"], mutant["new"], 1).encode("utf-8"))
    stamp(previous)
    try:
        yield
    finally:
        mid = path.stat().st_mtime_ns
        path.write_bytes(original)
        stamp(mid)


def outcome(status: str) -> str:
    return "survived" if status == "passed" else "killed"

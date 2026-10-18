"""Immutable Git seed copies for provider-free behavior tests."""
from __future__ import annotations
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def seed_git(repo: Path, files: dict[str, str] | None = None, *, remote: str | None = None) -> str:
    repo.mkdir(parents=True, exist_ok=True)
    for name, value in (files or {}).items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
    inputs = {p.relative_to(repo).as_posix(): p.read_bytes() for p in repo.rglob("*")
              if p.is_file() and ".git" not in p.parts}
    digest = hashlib.sha256(repr(sorted(inputs.items())).encode() + str(remote).encode()).hexdigest()
    parent = Path(os.environ.get("PYTEST_DEBUG_TEMPROOT", tempfile.gettempdir())) / "git-seeds"
    seed = parent / digest
    if not seed.exists():
        seed.mkdir(parents=True)
        for name, data in inputs.items():
            path = seed / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        def git(*args: str) -> str:
            result = subprocess.run(["git", *args], cwd=seed, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        git("init", "-q", "-b", "main")
        # Fixture identity is local setup; real commits below read these values.
        with (seed / ".git" / "config").open("a", encoding="utf-8") as config:
            config.write("\n[user]\n\temail = tests@example.invalid\n\tname = Tests\n")
        if remote:
            git("remote", "add", "origin", remote)
        git("add", ".")
        git("commit", "-qm", "fixture")
        (seed / "head.txt").write_text(git("rev-parse", "HEAD"), encoding="utf-8")
    shutil.copytree(seed / ".git", repo / ".git")
    return (seed / "head.txt").read_text(encoding="utf-8")

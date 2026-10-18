"""Targeted, observable repository reads for skill runtimes.

``RepositoryView`` deliberately has no enumeration API.  Callers must supply
the evidence paths they intend to inspect; this makes runtime work independent
of unrelated repository size and makes accidental discovery straightforward to
detect in tests.
"""

from __future__ import annotations

import ast
import hashlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


class RepositoryPathError(ValueError):
    """Raised when an evidence path is not a file inside the repository."""


@dataclass
class RepositoryView:
    """Cache narrowly requested repository data and record observable work."""

    root: Path
    _bytes: dict[Path, bytes] = field(default_factory=dict, init=False)
    _text: dict[Path, str] = field(default_factory=dict, init=False)
    _lines: dict[Path, tuple[str, ...]] = field(default_factory=dict, init=False)
    _hashes: dict[Path, str] = field(default_factory=dict, init=False)
    _trees: dict[Path, ast.AST] = field(default_factory=dict, init=False)
    _counts: Counter[str] = field(default_factory=Counter, init=False)

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        if not self.root.is_dir():
            raise RepositoryPathError(f"repository root does not exist: {self.root}")

    def resolve(self, relative_path: str | Path) -> Path:
        """Resolve one repo-relative evidence path, rejecting escapes and dirs."""
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise RepositoryPathError("evidence paths must be repository-relative")
        resolved = (self.root / candidate).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise RepositoryPathError(f"evidence path escapes repository: {relative_path}") from exc
        if not resolved.is_file():
            raise RepositoryPathError(f"evidence file does not exist: {relative_path}")
        return resolved

    def _path(self, relative_path: str | Path) -> Path:
        return self.resolve(relative_path)

    def read_bytes(self, relative_path: str | Path) -> bytes:
        path = self._path(relative_path)
        if path not in self._bytes:
            data = path.read_bytes()
            self._bytes[path] = data
            self._counts["files_opened"] += 1
            self._counts["bytes_read"] += len(data)
        return self._bytes[path]

    def read_text(self, relative_path: str | Path) -> str:
        path = self._path(relative_path)
        if path not in self._text:
            self._text[path] = self.read_bytes(path.relative_to(self.root)).decode("utf-8")
        return self._text[path]

    def lines(self, relative_path: str | Path) -> tuple[str, ...]:
        path = self._path(relative_path)
        if path not in self._lines:
            self._lines[path] = tuple(self.read_text(path.relative_to(self.root)).splitlines())
        return self._lines[path]

    def sha256(self, relative_path: str | Path) -> str:
        path = self._path(relative_path)
        if path not in self._hashes:
            self._hashes[path] = hashlib.sha256(self.read_bytes(path.relative_to(self.root))).hexdigest()
            self._counts["files_hashed"] += 1
        return self._hashes[path]

    def python_tree(self, relative_path: str | Path) -> ast.AST:
        path = self._path(relative_path)
        if path not in self._trees:
            self._trees[path] = ast.parse(self.read_text(path.relative_to(self.root)), filename=str(path))
            self._counts["files_parsed"] += 1
        return self._trees[path]

    @property
    def operation_counts(self) -> dict[str, int]:
        """Return stable counters, including zero-valued discovery counters."""
        names = (
            "files_opened", "bytes_read", "files_hashed", "files_parsed",
            "git_subprocesses", "runtime_subprocesses", "semantic_validations",
            "seal_attempts", "generated_artifact_tokens", "repository_wide_scans",
        )
        return {name: self._counts[name] for name in names}

    def count(self, name: str, amount: int = 1) -> None:
        """Allow a caller to record an explicit, non-discovery operation."""
        self._counts[name] += amount

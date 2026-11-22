"""Content-addressed artifact store and read handles.

Artifacts hold full command output or diffs that did not fit the inline budget.
Handles reference a file range together with the file hash so stale reads are
detectable without server state.
"""

from __future__ import annotations

import json
import os
import re
import stat
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, unquote

from .safety import SafetyError, atomic_write_bytes, sha256_bytes


class ArtifactStore:
    def __init__(
        self,
        root: str | Path | None = None,
        *,
        ttl_s: int = 3600,
        max_bytes: int = 200 * 1024 * 1024,
    ) -> None:
        env_root = os.environ.get("BATCH_OPS_ARTIFACT_DIR")
        if not root and not env_root and sys.platform != "win32":
            euid = os.geteuid()
            self.root = Path(tempfile.gettempdir()) / f"batch_ops-{euid}"
            created = True
            try:
                os.mkdir(self.root, 0o700)
            except FileExistsError:
                created = False
            if created:
                os.chmod(self.root, 0o700)
            st = os.lstat(self.root)
            problems = []
            if not stat.S_ISDIR(st.st_mode):
                problems.append("is not a real directory (it may be a link)")
            if st.st_uid != euid:
                problems.append("is not owned by the current user")
            if stat.S_IMODE(st.st_mode) != 0o700:
                problems.append("does not have mode 700")
            if problems:
                raise SafetyError(
                    f"artifact folder {self.root} {' and '.join(problems)}; "
                    "set BATCH_OPS_ARTIFACT_DIR to use another directory"
                )
        else:
            self.root = Path(root or env_root or (Path(tempfile.gettempdir()) / "batch_ops")).expanduser()
            self.root.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(self.root, 0o700)
            except OSError:
                pass
        self.ttl_s = max(60, int(ttl_s))
        self.max_bytes = max(1024 * 1024, int(max_bytes))
        self._last_cleanup = 0.0

    # -- storage ---------------------------------------------------------
    def put(self, data: bytes | str, suffix: str = ".txt") -> str:
        raw = data.encode("utf-8", errors="replace") if isinstance(data, str) else data
        if not suffix.startswith("."):
            suffix = "." + suffix
        digest = sha256_bytes(raw)
        name = f"{digest[:16]}{suffix}"
        path = self.root / name
        if not path.exists():
            atomic_write_bytes(path, raw)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        return f"artifact:{name}"

    def name(self, ref: str) -> str:
        value = ref.strip()
        if value.startswith("artifact:"):
            value = value[len("artifact:") :]
        if not value or "/" in value or "\\" in value or value in (".", ".."):
            raise ValueError(f"invalid artifact reference: {ref}")
        return value

    def path(self, ref: str) -> Path:
        return self.root / self.name(ref)

    def get(self, ref: str) -> bytes:
        return self.path(ref).read_bytes()

    def get_text(self, ref: str) -> str:
        return self.get(ref).decode("utf-8", errors="replace")

    # -- aliases ---------------------------------------------------------
    # A label names a stored artifact for one call root.  Each alias is its own small record
    # (written atomically) so several server processes sharing this folder never lose each
    # other's writes or see another root's result.
    @staticmethod
    def is_alias(name: str) -> bool:
        return re.fullmatch(r"[A-Za-z0-9_-]{1,64}(\.stderr)?", name) is not None

    @classmethod
    def is_label(cls, name: str) -> bool:
        """A name a caller may label a result with (the `.stderr` form is bound only by the runner)."""
        return cls.is_alias(name) and not name.endswith(".stderr")

    def _alias_path(self, root: str | Path, name: str) -> Path:
        digest = sha256_bytes(f"{root}\0{name}".encode("utf-8", errors="replace"))
        return self.root / f"{digest[:24]}.alias.json"

    def bind(self, root: str | Path, name: str, data: bytes | str, suffix: str, source: str) -> None:
        if not self.is_alias(name):
            raise ValueError(f"invalid alias name: {name}")
        target = self.name(self.put(data, suffix))
        try:
            os.utime(self.root / target)  # the target lives as long as the alias
        except OSError:
            pass
        record = {"name": name, "root": str(root), "target": target, "source": source, "created": time.time()}
        atomic_write_bytes(self._alias_path(root, name), json.dumps(record).encode("utf-8"), mode=0o600)

    def unbind(self, root: str | Path, name: str) -> None:
        if not self.is_alias(name):
            return
        try:
            self._alias_path(root, name).unlink()
        except OSError:
            pass

    def resolve(self, root: str | Path, name: str) -> dict[str, object] | None:
        if not self.is_alias(name):
            return None
        try:
            record = json.loads(self._alias_path(root, name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(record, dict) or record.get("name") != name or record.get("root") != str(root):
            return None
        return record

    # -- cleanup ---------------------------------------------------------
    def cleanup(self, *, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._last_cleanup < 600:
            return
        self._last_cleanup = now
        entries: list[tuple[float, int, Path]] = []
        try:
            for p in self.root.iterdir():
                if not p.is_file():
                    continue
                try:
                    st = p.stat()
                except OSError:
                    continue
                entries.append((st.st_mtime, st.st_size, p))
        except OSError:
            return

        for mtime, _, p in entries:
            if now - mtime > self.ttl_s:
                try:
                    p.unlink()
                except OSError:
                    pass

        entries = [e for e in entries if e[2].exists()]
        total = sum(size for _, size, _ in entries)
        if total > self.max_bytes:
            for _, size, p in sorted(entries, key=lambda e: e[0]):
                if total <= self.max_bytes:
                    break
                try:
                    p.unlink()
                    total -= size
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Read handles
# ---------------------------------------------------------------------------
def make_read_handle(path: str, sha: str, start: int | None, end: int | None) -> str:
    quoted = quote(path, safe="/")  # only ":" and "%" need escaping for the handle format
    rng = f"{start}-{end}" if start is not None and end is not None else "full"
    return f"read:{quoted}:{sha[:16]}:{rng}"  # 64-bit prefix: enough to detect change, fewer tokens


def since_sha(value: str) -> str | None:
    """The lowercase sha prefix in a `since` value (a sha of 8+ hex characters or a read handle)."""
    value = value.strip()
    if value.startswith("read:"):
        try:
            value = str(parse_read_handle(value)["sha"])
        except ValueError:
            return None
    value = value.lower()
    return value if len(value) >= 8 and re.fullmatch(r"[0-9a-f]+", value) else None


def parse_read_handle(handle: str) -> dict[str, object]:
    if not handle.startswith("read:"):
        raise ValueError(f"not a read handle: {handle}")
    parts = handle.split(":")
    if len(parts) == 5 and parts[3] == "full":  # "<full handle>:N-M" narrows the full read to N-M
        parts = [*parts[:3], parts[4]]
    if len(parts) != 4:
        raise ValueError(f"malformed read handle: {handle}")
    _, quoted, sha, rng = parts
    path = unquote(quoted)
    if rng == "full":
        start = end = None
    else:
        if "-" not in rng:
            raise ValueError(f"malformed read handle range: {handle}")
        s, e = rng.split("-", 1)
        start, end = int(s), int(e)
    return {"path": path, "sha": sha, "start": start, "end": end}

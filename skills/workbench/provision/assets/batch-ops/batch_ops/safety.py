"""Filesystem, text, encoding and path-safety helpers.

Everything here is language-agnostic: bytes, encodings, line endings and paths.
No file is written outside the caller-provided root unless explicitly allowed.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


class SafetyError(ValueError):
    """A path, encoding or edit would violate a safety rule."""


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def resolve_path(
    root: str | Path,
    path: str | Path,
    *,
    allow_outside: bool = False,
    must_exist: bool = False,
) -> Path:
    """Resolve *path* against *root* and enforce workspace containment.

    Symlinks are followed; a symlink inside the root that points outside is
    rejected unless ``allow_outside`` is true.
    """
    root_p = Path(root).expanduser().resolve()
    raw = Path(path).expanduser()
    candidate = raw.resolve() if raw.is_absolute() else (root_p / raw).resolve()

    if not allow_outside:
        root_key = os.path.normcase(str(root_p))
        cand_key = os.path.normcase(str(candidate))
        try:
            common = os.path.commonpath([root_key, cand_key])
        except ValueError as exc:  # different drives on Windows
            raise SafetyError(f"path escapes the workspace: {path}") from exc
        if common != root_key:
            raise SafetyError(f"path escapes the workspace: {path}")

    if must_exist and not candidate.exists():
        raise FileNotFoundError(str(path))
    return candidate


def relative_display(root: str | Path, path: str | Path) -> str:
    """Return a stable, forward-slash relative path for reports."""
    root_p = Path(root).resolve()
    p = Path(path).resolve()
    try:
        rel = p.relative_to(root_p)
        return rel.as_posix()
    except ValueError:
        return p.as_posix()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8", errors="replace"))


def format_bytes(n: int | None) -> str:
    if n is None:
        return "?"
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f}KB"
    return f"{n / (1024 * 1024):.1f}MB"


def estimate_tokens(text: str | bytes) -> int:
    raw = text.encode("utf-8", errors="replace") if isinstance(text, str) else text
    return max(1, len(raw) // 4)


# ---------------------------------------------------------------------------
# Encoding and line endings
# ---------------------------------------------------------------------------
@dataclass
class TextInfo:
    text: str
    encoding: str
    eol: str | None
    mixed_eol: bool
    binary: bool
    lossy: bool
    bytes_total: int
    eol_counts: dict[str, int] = field(default_factory=dict)


def detect_eol(text: str) -> tuple[str | None, bool, dict[str, int]]:
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    cr = text.count("\r") - crlf
    counts = {"crlf": crlf, "lf": lf, "cr": cr}
    kinds = [k for k, v in counts.items() if v > 0]
    if not kinds:
        return None, False, counts
    if len(kinds) == 1:
        return {"crlf": "\r\n", "lf": "\n", "cr": "\r"}[kinds[0]], False, counts
    dominant = max(counts, key=lambda k: counts[k])
    return {"crlf": "\r\n", "lf": "\n", "cr": "\r"}[dominant], True, counts


def to_eol(text: str, eol: str | None) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if eol is None or eol == "\n":
        return normalized
    return normalized.replace("\n", eol)


def decode_bytes(data: bytes, encoding: str | None = None) -> TextInfo:
    """Decode bytes with BOM detection and an explicit lossy flag.

    UTF-8 BOM and UTF-16 BOM are handled automatically.  Other encodings must
    be requested explicitly.  Invalid UTF-8 is decoded with replacement and
    marked lossy so edits can refuse it.
    """
    if encoding:
        try:
            text = data.decode(encoding, errors="strict")
            lossy = False
        except (UnicodeDecodeError, LookupError):
            text = data.decode(encoding, errors="replace") if _valid_codec(encoding) else data.decode("utf-8", errors="replace")
            lossy = True
        binary = False
        eol, mixed, counts = detect_eol(text)
        return TextInfo(text, encoding, eol, mixed, binary, lossy, len(data), counts)

    if data.startswith(b"\xef\xbb\xbf"):
        return _decode_known(data, "utf-8-sig")
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return _decode_known(data, "utf-16")

    binary = b"\x00" in data[:8192]
    if binary:
        return TextInfo("", "utf-8", None, False, True, False, len(data), {})

    try:
        text = data.decode("utf-8", errors="strict")
        lossy = False
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
        lossy = True
    eol, mixed, counts = detect_eol(text)
    return TextInfo(text, "utf-8", eol, mixed, False, lossy, len(data), counts)


def _valid_codec(encoding: str) -> bool:
    try:
        "".encode(encoding)
        return True
    except LookupError:
        return False


def _decode_known(data: bytes, encoding: str) -> TextInfo:
    try:
        text = data.decode(encoding, errors="strict")
        lossy = False
    except UnicodeDecodeError:
        text = data.decode(encoding, errors="replace")
        lossy = True
    eol, mixed, counts = detect_eol(text)
    binary = b"\x00" in data[:8192] and not encoding.startswith("utf-16")
    return TextInfo(text, encoding, eol, mixed, binary, lossy, len(data), counts)


def encode_text(text: str, encoding: str) -> bytes:
    try:
        return text.encode(encoding)
    except (UnicodeEncodeError, LookupError) as exc:
        raise SafetyError(f"cannot encode text as {encoding}: {exc}") from exc


def read_text_file(path: str | Path, encoding: str | None = None) -> TextInfo:
    data = Path(path).read_bytes()
    return decode_bytes(data, encoding)


# ---------------------------------------------------------------------------
# Line helpers
# ---------------------------------------------------------------------------
def parse_range(value: str | None) -> list[tuple[int, int]]:
    """Parse ``10-20``, ``10``, ``-20`` or ``10-20,30-40`` into 1-based ranges."""
    if not value:
        return []
    out: list[tuple[int, int]] = []
    for chunk in str(value).split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" not in chunk:
            n = int(chunk)
            if n < 1:
                raise SafetyError(f"line numbers are 1-based: {chunk}")
            out.append((n, n))
            continue
        start_s, end_s = chunk.split("-", 1)
        start = int(start_s) if start_s.strip() else 1
        end = int(end_s) if end_s.strip() else 2**31 - 1
        if start < 1 or end < 1:
            raise SafetyError(f"line numbers are 1-based: {chunk}")
        if end < start:
            raise SafetyError(f"invalid range (end before start): {chunk}")
        out.append((start, end))
    return out


def select_lines(lines: list[str], ranges: list[tuple[int, int]]) -> list[tuple[int, str]]:
    """Return (original_line_number, text) pairs for the requested ranges."""
    if not ranges:
        return [(i, line) for i, line in enumerate(lines, start=1)]
    selected: list[tuple[int, str]] = []
    seen: set[int] = set()
    for start, end in ranges:
        for idx in range(max(1, start), min(len(lines), end) + 1):
            if idx not in seen:
                seen.add(idx)
                selected.append((idx, lines[idx - 1]))
    return selected


# ---------------------------------------------------------------------------
# Literal search with line-ending flexibility
# ---------------------------------------------------------------------------
@dataclass
class MatchSpan:
    start: int
    end: int
    line: int
    text: str


def literal_pattern(search: str) -> re.Pattern[str]:
    if not search or not search.strip():
        raise SafetyError("search text must not be empty or whitespace-only")
    normalized = search.replace("\r\n", "\n").replace("\r", "\n")
    parts = normalized.split("\n")
    return re.compile(r"\r?\n".join(re.escape(part) for part in parts), re.MULTILINE)


def find_matches(text: str, search: str, *, ignore_case: bool = False) -> list[MatchSpan]:
    pattern = literal_pattern(search)
    flags = re.MULTILINE
    if ignore_case:
        flags |= re.IGNORECASE
    rx = re.compile(pattern.pattern, flags)
    matches: list[MatchSpan] = []
    for m in rx.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        matches.append(MatchSpan(m.start(), m.end(), line, m.group(0)))
    return matches


def apply_replacement(text: str, match: MatchSpan, replacement: str, fallback_eol: str | None) -> str:
    matched = text[match.start : match.end]
    if "\r\n" in matched:
        eol = "\r\n"
    elif "\n" in matched:
        eol = "\n"
    elif "\r" in matched:
        eol = "\r"
    else:
        eol = fallback_eol or "\n"
    return to_eol(replacement, eol)


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------
def truncate_text(
    text: str,
    cap_bytes: int,
    *,
    style: str = "head_tail",
) -> tuple[str, bool, int]:
    """Truncate to *cap_bytes* UTF-8 bytes and say so explicitly.

    ``head_tail`` keeps both ends (best for logs); ``head`` keeps the beginning
    (best for source); ``tail`` keeps the end (best for summaries).
    """
    raw = text.encode("utf-8", errors="replace")
    total = len(raw)
    cap = max(64, int(cap_bytes))
    if total <= cap:
        return text, False, total

    if style == "tail":
        tail = raw[-cap:].decode("utf-8", errors="ignore")
        return f"[... {total - len(tail.encode('utf-8'))} bytes omitted ...]\n{tail}", True, total
    if style == "head":
        head = raw[:cap].decode("utf-8", errors="ignore")
        omitted = total - len(head.encode("utf-8"))
        return f"{head}\n[... {omitted} bytes omitted ...]", True, total

    half = cap // 2
    head = raw[:half].decode("utf-8", errors="ignore")
    tail = raw[-half:].decode("utf-8", errors="ignore")
    omitted = total - len(head.encode("utf-8")) - len(tail.encode("utf-8"))
    return f"{head}\n[... {omitted} bytes omitted (head+tail) ...]\n{tail}", True, total


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------
def atomic_write_bytes(path: str | Path, data: bytes, *, mode: int | None = None) -> None:
    """Write bytes to a temp file in the same directory, then replace."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        if mode is not None:
            try:
                os.chmod(tmp, mode)
            except OSError:
                pass
        os.replace(tmp, target)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def file_mode(path: str | Path) -> int | None:
    try:
        return stat.S_IMODE(Path(path).stat().st_mode)
    except OSError:
        return None


def iter_text_lines(text: str) -> Iterable[str]:
    return text.splitlines()

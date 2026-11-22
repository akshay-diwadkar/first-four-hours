"""Bounded, concurrent command execution.

Commands are independent: a failed, timed-out or unparsable command never stops
the rest of the batch.  Each command receives its own cwd, environment, stdin,
shell and timeout.  On timeout the whole process tree is killed and whatever was
produced before the timeout is still returned.
"""

from __future__ import annotations

import asyncio
import functools
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import ArtifactStore
from .budget import BudgetTracker, body_budget, tier, water_fill
from .safety import SafetyError, decode_bytes, format_bytes, relative_display, resolve_path, truncate_text
from .slices import _filter_failures, apply_slices
from .types import RunRequest, RunResult

CAPTURE_LIMIT = 16 * 1024 * 1024  # per stream, in memory
SUCCESS_TAIL = 15  # lines kept from the end of a long passing output (summaries live there)
SUCCESS_TRIM_BYTES = 4 * 1024  # passing outputs larger than this are trimmed to their tail
_ARTIFACT_SLOT = "@@STDOUT_ARTIFACT@@"  # filled with the artifact reference once it is saved
DEFAULT_PARALLEL = 4
FAIL_FRAME_BYTES = 8 * 1024  # a failing stream larger than this keeps its failure windows and tail
FOLD_MIN = 3  # this many identical lines in a row fold into one line and a count
RUN_MAX = 10  # a longer run of one punctuation or symbol character is cut to this length
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")
_LONG_RUN = re.compile(r"([^\w\s])\1{%d,}" % RUN_MAX)


@dataclass
class _Captured:
    data: bytearray
    total: int
    dropped: int


async def _read_stream(stream: asyncio.StreamReader | None, capture: _Captured) -> None:
    if stream is None:
        return
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            break
        capture.total += len(chunk)
        room = CAPTURE_LIMIT - len(capture.data)
        if room > 0:
            capture.data.extend(chunk[:room])
            if len(chunk) > room:
                capture.dropped += len(chunk) - room
        else:
            capture.dropped += len(chunk)


@functools.lru_cache(maxsize=1)
def _git_bash() -> str | None:
    """Git for Windows' bash.exe, found through ``git --exec-path``; None elsewhere or on any failure."""
    if os.name != "nt":
        return None
    try:
        proc = subprocess.run(
            ["git", "--exec-path"], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5,
        )
        if proc.returncode != 0:
            return None
        candidate = Path(proc.stdout.strip()).parents[2] / "bin" / "bash.exe"
        return str(candidate) if candidate.is_file() else None
    except Exception:
        return None


@functools.lru_cache(maxsize=1)
def _auto_bash() -> str | None:
    """First bash.exe on PATH outside %SystemRoot% (that one is the WSL launcher), else Git Bash."""
    system_root = os.path.normcase(os.environ.get("SystemRoot") or "")
    for entry in (os.environ.get("PATH") or "").split(os.pathsep):
        entry = entry.strip().strip('"')
        if not entry:
            continue
        if system_root and os.path.normcase(entry).startswith(system_root):
            continue
        candidate = Path(entry) / "bash.exe"
        if candidate.is_file():
            return str(candidate)
    return _git_bash()


def _resolve_shell(req: RunRequest, root: Path) -> tuple[list[str], str]:
    """Return (argv prefix, shell name) for a string command."""
    shell = req.shell or "auto"
    if req.argv is not None:
        return [], "direct"

    if shell == "direct":
        raise SafetyError("shell='direct' requires argv, not cmd")

    if shell == "auto":
        if os.name != "nt":
            shell = "sh"
        else:
            bash = _auto_bash()
            if bash:
                return [bash, "-c"], "bash"
            exe = shutil.which("pwsh") or shutil.which("powershell")
            if not exe:
                raise SafetyError('no bash or PowerShell found; pass "shell": "cmd"')
            return [exe, "-NoProfile", "-NonInteractive", "-Command"], "powershell"

    if shell in ("bash", "sh"):
        exe = shutil.which(shell)
        if not exe and shell == "bash" and os.name == "nt":
            exe = _git_bash()
        if not exe:
            hint = '; pass "shell": "powershell", or "argv"' if os.name == "nt" else ""
            raise SafetyError(f"{shell} is not available on PATH{hint}")
        if shell == "bash":
            return [exe, "-c"], "bash"
        return [exe, "-c"], "sh"

    if shell == "cmd":
        if os.name != "nt":
            raise SafetyError("shell='cmd' is only available on Windows")
        exe = os.environ.get("ComSpec") or shutil.which("cmd") or "cmd.exe"
        return [exe, "/d", "/s", "/c"], "cmd"

    if shell == "powershell":
        exe = shutil.which("pwsh") or shutil.which("powershell")
        if not exe:
            raise SafetyError("PowerShell is not available on PATH")
        return [exe, "-NoProfile", "-NonInteractive", "-Command"], "powershell"

    raise SafetyError(f"unknown shell: {shell}")


def _build_process_args(req: RunRequest, root: Path) -> tuple[list[str], str]:
    if req.argv is not None:
        return [str(a) for a in req.argv], "direct"
    if req.cmd is None:
        raise SafetyError("command has neither cmd nor argv")
    prefix, shell_name = _resolve_shell(req, root)
    return [*prefix, req.cmd], shell_name


def _normalize_output(text: str) -> str:
    """Terminal escape sequences removed and line endings made "\\n"; nothing visible is lost."""
    return _ANSI.sub("", text).replace("\r\n", "\n")


def _condense(text: str) -> tuple[str, bool]:
    """Output as a terminal would leave it, made shorter: a line rewritten in place with "\\r"
    keeps its last state, identical lines in a row fold into one and a count, and long runs of
    one punctuation or symbol character are cut.  True when anything was dropped."""
    changed = False
    rows: list[str] = []
    for line in text.split("\n"):
        if "\r" in line:
            states = [s for s in line.split("\r") if s]
            changed = changed or len(states) > 1
            line = states[-1] if states else ""
        short = _LONG_RUN.sub(lambda m: m.group(1) * RUN_MAX, line)
        changed = changed or short != line
        rows.append(short)
    out: list[str] = []
    i = 0
    while i < len(rows):
        j = i
        while j + 1 < len(rows) and rows[j + 1] == rows[i]:
            j += 1
        out.append(rows[i])
        if rows[i].strip() and j - i + 1 >= FOLD_MIN:
            out.append(f"[... repeated {j - i} more times]")
            changed = True
        else:
            out.extend(rows[i + 1:j + 1])
        i = j + 1
    return "\n".join(out), changed


async def _kill_tree(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    if sys.platform == "win32":
        try:
            killer = await asyncio.create_subprocess_exec(
                "taskkill", "/T", "/F", "/PID", str(process.pid),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(killer.wait(), timeout=5)
            except asyncio.TimeoutError:
                killer.kill()
        except (OSError, subprocess.SubprocessError):
            pass
        if process.returncode is None:
            try:
                process.kill()
            except (ProcessLookupError, OSError):
                pass
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                process.kill()
            except (ProcessLookupError, OSError):
                pass

    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except asyncio.TimeoutError:
        pass


@dataclass
class _Executed:
    """A finished command before the batch budget is applied to its output."""

    req: RunRequest
    result: RunResult
    stdout: str = ""
    stderr: str = ""
    stdout_raw: bytes = b""
    stderr_raw: bytes = b""
    trimmed: bool = False  # long passing output already cut to head and tail
    stdout_changed: bool = False  # condensed or sliced: the raw stream is kept as an artifact
    stderr_changed: bool = False
    note: str = ""  # what condensing or slicing dropped; the artifact names are added later
    trim_text: str = ""  # the stdout text the trim counted
    raw_stdout_ref: str | None = None


def _blank(req: RunRequest, status: str, message: str) -> _Executed:
    return _Executed(req, RunResult(
        id=f"run{req.index}", label=req.label, status=status,
        cmd_display=req.display or (req.cmd or " ".join(req.argv or [])),
        message=message, shell=req.shell,
    ))


async def _run_one(req: RunRequest, *, root: Path, deadline: float) -> _Executed:
    result = RunResult(
        id=f"run{req.index}",
        label=req.label,
        cmd_display=req.display or (req.cmd or " ".join(req.argv or [])),
        shell=req.shell,
        cwd=relative_display(root, root),
    )
    done = _Executed(req, result)

    try:
        cwd = resolve_path(root, req.cwd or ".", must_exist=True)
        if not cwd.is_dir():
            raise SafetyError(f"cwd is not a directory: {req.cwd or '.'}")
        process_args, shell_name = _build_process_args(req, root)
        result.shell = shell_name
        result.cwd = relative_display(root, cwd)
    except Exception as exc:
        result.status = "error"
        result.message = str(exc)
        return done

    env = os.environ.copy()
    env.update(req.env)

    stdout_cap = _Captured(bytearray(), 0, 0)
    stderr_cap = _Captured(bytearray(), 0, 0)
    started = time.monotonic()
    process: asyncio.subprocess.Process | None = None
    timed_out = False

    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    try:
        stdio: dict[str, Any] = dict(
            cwd=str(cwd),
            env=env,
            stdin=asyncio.subprocess.PIPE if req.stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT if req.merge_streams else asyncio.subprocess.PIPE,
            **kwargs,
        )
        if shell_name == "cmd":
            # An argv list is re-quoted with list2cmdline, which escapes inner quotes as \" and
            # cmd.exe passes those through literally (python -c "print(1)" then prints nothing).
            # The shell path hands cmd.exe the command line verbatim as ComSpec /c "<cmd>".
            process = await asyncio.create_subprocess_shell(process_args[-1], **stdio)
        else:
            process = await asyncio.create_subprocess_exec(*process_args, **stdio)

        readers = [asyncio.create_task(_read_stream(process.stdout, stdout_cap))]
        if not req.merge_streams:
            readers.append(asyncio.create_task(_read_stream(process.stderr, stderr_cap)))

        if req.stdin is not None and process.stdin is not None:
            try:
                process.stdin.write(req.stdin.encode("utf-8", errors="replace"))
                await asyncio.wait_for(process.stdin.drain(), timeout=5)
                process.stdin.close()
            except (BrokenPipeError, ConnectionResetError, OSError, asyncio.TimeoutError):
                pass

        remaining = max(0.05, deadline - time.monotonic())
        timeout = min(req.timeout, remaining)
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            timed_out = True
            await _kill_tree(process)

        try:
            await asyncio.wait_for(asyncio.gather(*readers, return_exceptions=True), timeout=5)
        except asyncio.TimeoutError:
            for task in readers:
                task.cancel()
            await asyncio.gather(*readers, return_exceptions=True)

        result.exit_code = process.returncode
        result.timed_out = timed_out
        result.elapsed_ms = int((time.monotonic() - started) * 1000)
        result.bytes_total = stdout_cap.total + stderr_cap.total

        if timed_out:
            result.status = "timeout"
            result.message = f"timed out after {timeout:.1f}s; partial output kept"
        elif process.returncode in req.ok_exit:
            result.status = "ok"
            if req.merge_streams and stdout_cap.data:
                result.message = "stderr merged into stdout"
        else:
            result.status = "error"  # the header shows the exit code

    except FileNotFoundError as exc:
        result.status = "error"
        result.message = f"cannot start command: {exc}"
        result.elapsed_ms = int((time.monotonic() - started) * 1000)
        return done
    except asyncio.CancelledError:
        if process is not None:
            await _kill_tree(process)
        raise
    except Exception as exc:
        result.status = "error"
        result.message = f"runner failure: {exc}"
        result.elapsed_ms = int((time.monotonic() - started) * 1000)
        if process is not None:
            await _kill_tree(process)
        return done

    stdout_text, stdout_nul = _decode_output(bytes(stdout_cap.data))
    stderr_text, stderr_nul = _decode_output(bytes(stderr_cap.data))
    stdout_text = _normalize_output(stdout_text)
    stderr_text = _normalize_output(stderr_text)
    stdout_visible = stdout_text.encode("utf-8") if stdout_nul else None
    stderr_visible = stderr_text.encode("utf-8") if stderr_nul else None
    if stdout_nul or stderr_nul:
        note = "NUL bytes shown as \\0"
        result.message = f"{result.message}; {note}" if result.message else note

    notes: list[str] = []
    if req.slices:
        before_out, before_err = stdout_text, stderr_text
        stdout_text, errors = apply_slices(stdout_text, req.slices)
        result.slice_errors.extend(f"stdout {e}" for e in errors)
        if not req.merge_streams:
            stderr_text, errors = apply_slices(stderr_text, req.slices)
            result.slice_errors.extend(f"stderr {e}" for e in errors)
        done.stdout_changed = done.stdout_changed or stdout_text != before_out
        done.stderr_changed = done.stderr_changed or stderr_text != before_err
        if not stdout_text and not stderr_text and (stdout_cap.data or stderr_cap.data):
            notes.append(
                f"slices kept none of "
                f"{format_bytes(len(stdout_cap.data) + len(stderr_cap.data))} of output"
            )
        elif stdout_text != before_out or stderr_text != before_err:
            total = len(before_out.splitlines()) + len(before_err.splitlines())
            notes.append(f"sliced from {total} line(s)")
    else:
        stdout_text, done.stdout_changed = _condense(stdout_text)
        stderr_text, done.stderr_changed = _condense(stderr_text)
        if done.stdout_changed or done.stderr_changed:
            notes.append("output condensed (overwritten, repeated, or long divider lines)")
    if not req.slices and result.status != "ok":
        # A long failure keeps its failure windows and the summary at its end.
        for stream in ("stdout", "stderr"):
            text = stdout_text if stream == "stdout" else stderr_text
            if _blen(text) <= FAIL_FRAME_BYTES:
                continue
            framed = "\n".join(_filter_failures(text.splitlines(), None)) + "\n"
            if stream == "stdout":
                stdout_text, done.stdout_changed = framed, True
            else:
                stderr_text, done.stderr_changed = framed, True
            notes.append(f"{stream} framed to failure windows and its last lines")
    done.note = "; ".join(notes)

    # A passing command's long output is rarely read in full: keep its head and tail.
    # Failures keep everything (failure-first), and explicit slices always win.
    if not req.slices and result.status == "ok" and _blen(stdout_text) > SUCCESS_TRIM_BYTES:
        out_lines = stdout_text.splitlines()
        if len(out_lines) > SUCCESS_TAIL:
            omitted = len(out_lines) - SUCCESS_TAIL
            done.trim_text = stdout_text
            stdout_text = "\n".join(
                [f"[... {omitted} earlier lines of passing output omitted: \"{_ARTIFACT_SLOT}:1-{omitted}\"]"]
                + out_lines[-SUCCESS_TAIL:]
            ) + "\n"
            done.trimmed = True

    if stdout_cap.dropped or stderr_cap.dropped:
        note = f"output capture capped at {format_bytes(CAPTURE_LIMIT)} per stream"
        result.message = f"{result.message}; {note}" if result.message else note

    done.stdout, done.stderr = stdout_text, stderr_text
    done.stdout_raw = stdout_visible if stdout_visible is not None else bytes(stdout_cap.data)
    done.stderr_raw = stderr_visible if stderr_visible is not None else bytes(stderr_cap.data)
    return done


def _decode_output(data: bytes) -> tuple[str, bool]:
    """Decode command output; a NUL byte anywhere shows as the two characters \\0."""
    if data.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")) or b"\x00" not in data:
        return decode_bytes(data).text, False
    return data.decode("utf-8", errors="replace").replace("\x00", "\\0"), True


def _name_trimmed_artifact(done: _Executed, artifacts: ArtifactStore) -> None:
    """Save a trimmed passing stream and put its name in the trim hint, so the hint is a
    spec to paste.  Runs before the budget is shared, so the sizes include the real name."""
    if done.trimmed:
        done.result.stdout_artifact = artifacts.put(done.trim_text, ".stdout.txt")
        done.stdout = done.stdout.replace(_ARTIFACT_SLOT, done.result.stdout_artifact, 1)
        if done.stdout_raw and done.stdout_raw != done.trim_text.encode("utf-8"):
            done.raw_stdout_ref = artifacts.put(done.stdout_raw, ".stdout.txt")


def _blen(text: str) -> int:
    return len(text.encode("utf-8", errors="replace"))


_PY_REF = re.compile(r'File "([^"]+)", line (\d+)')
_REF_PATH = r"""(?:[A-Za-z]:)?[^\s:"'()<>\[\]{}|,;=]+"""
_REF = re.compile(r"""(?<![^\s:"'()<>\[\]{}|,;=])(""" + _REF_PATH + r")(?:\((\d+)(?:,\d+)?\)|:(\d+)(?!\d))")
REF_SCAN_MAX = 200  # matches scanned per command
SOURCE_REFS = 3  # references per command that get a window
SOURCE_CONTEXT = 3  # lines above and below a cited line
SOURCE_MAX_FILE = 1024 * 1024
SOURCE_LINE_CLIP = 200


def _find_refs(text: str) -> list[tuple[str, int]]:
    """(path, line) references in output order; a Python traceback line uses only its File form."""
    found: list[tuple[str, int]] = []
    for line in text.split("\n"):
        matches = [(m.group(1), int(m.group(2))) for m in _PY_REF.finditer(line)]
        if not matches:
            matches = [(m.group(1), int(m.group(2) or m.group(3))) for m in _REF.finditer(line)]
        for path, number in matches:
            if path.startswith(("//", "\\\\")) or "://" in path or number == 0:
                continue
            found.append((path, number))
            if len(found) >= REF_SCAN_MAX:
                return found
    return found


def _locate_file(root: Path, cwd: str, path: str) -> Path | None:
    """The existing regular file a reference names inside the root, else None."""
    if Path(path).is_absolute():
        options = [path]
    else:
        options = [str(Path(cwd or ".") / path), path]
    for option in options:
        try:
            candidate = resolve_path(root, option)
            if candidate.is_file():
                return candidate
        except (SafetyError, OSError):
            continue
    return None


def _read_source_lines(file: Path) -> list[str] | None:
    try:
        if file.stat().st_size > SOURCE_MAX_FILE:
            return None
        info = decode_bytes(file.read_bytes())
    except OSError:
        return None
    if info.binary:
        return None
    rows = info.text.replace("\r\n", "\n").split("\n")
    if rows and rows[-1] == "":
        rows.pop()
    return rows


def _ignored_paths(root: Path, paths: list[str]) -> set[str]:
    if not paths:
        return set()
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "-z", "--stdin"],
            input="\0".join(paths).encode("utf-8", "surrogateescape"),
            capture_output=True, timeout=10,
        )
        if proc.returncode not in (0, 1):
            return set()
        return {p for p in proc.stdout.decode("utf-8", "surrogateescape").split("\0") if p}
    except Exception:  # noqa: BLE001 - locating must never lose a command's result
        return set()


def _render_windows(picked: list[tuple[str, int]], files: dict[str, list[str]]) -> str:
    blocks: list[tuple[int, str, int, int, set[int]]] = []  # first ref index, path, start, end, cited
    for rel in dict.fromkeys(path for path, _ in picked):
        total = len(files[rel])
        spans = sorted(
            (max(1, n - SOURCE_CONTEXT), min(total, n + SOURCE_CONTEXT), n, i)
            for i, (path, n) in enumerate(picked) if path == rel
        )
        merged: list[list] = []
        for start, end, n, i in spans:
            if merged and start <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], end)
                merged[-1][2].add(n)
                merged[-1][3] = min(merged[-1][3], i)
            else:
                merged.append([start, end, {n}, i])
        blocks.extend((m[3], rel, m[0], m[1], m[2]) for m in merged)
    out: list[str] = []
    for _, rel, start, end, cited in sorted(blocks, key=lambda b: b[0]):
        out.append(f"{rel}:{start}-{end}")
        width = len(str(end))
        for n in range(start, end + 1):
            text = files[rel][n - 1][:SOURCE_LINE_CLIP]
            out.append(f"{'>' if n in cited else ' '} {n:>{width}}  {text}")
    return "\n".join(out)


def _attach_sources(executed: list[_Executed], root: Path) -> None:
    """Set ``result.source`` on failed and timed-out commands: the lines around the first
    references their shown output makes to non-ignored text files inside the root."""
    cache: dict[Path, list[str] | None] = {}
    per_command: dict[int, list[tuple[Path, str, int]]] = {}
    for pos, done in enumerate(executed):
        if done.result.status not in ("error", "timeout"):
            continue
        try:
            cands: list[tuple[Path, str, int]] = []
            for path, number in _find_refs(done.stdout + "\n" + done.stderr):
                file = _locate_file(root, done.req.cwd or ".", path)
                if file is None:
                    continue
                rel = file.relative_to(root).as_posix()
                if ".git" in rel.split("/"):
                    continue
                if file not in cache:
                    cache[file] = _read_source_lines(file)
                rows = cache[file]
                if rows is None or number > len(rows):
                    continue
                cands.append((file, rel, number))
            per_command[pos] = cands
        except Exception:
            continue
    ignored = _ignored_paths(root, sorted({rel for cands in per_command.values() for _, rel, _ in cands}))
    for pos, cands in per_command.items():
        try:
            picked: list[tuple[str, int]] = []
            files: dict[str, list[str]] = {}
            for file, rel, number in cands:
                if rel in ignored or (rel, number) in picked:
                    continue
                picked.append((rel, number))
                files[rel] = cache[file] or []
                if len(picked) >= SOURCE_REFS:
                    break
            if picked:
                executed[pos].result.source = _render_windows(picked, files)
        except Exception:
            executed[pos].result.source = ""


def _stream_cap(req: RunRequest, max_output: int) -> int:
    """A command's own inline cap per stream (its max_bytes, split when streams are separate)."""
    per_command = max(256, min(max_output, max(256, req.max_bytes)))
    return per_command if req.merge_streams else max(256, per_command // 2)


def _need(done: _Executed, max_output: int) -> int:
    cap = _stream_cap(done.req, max_output)
    return min(_blen(done.stdout), cap) + min(_blen(done.stderr), cap) + _blen(done.result.source)


def _finalize(done: _Executed, share: int, artifacts: ArtifactStore, max_output: int) -> RunResult:
    """Cut each stream to the command's share of the batch budget and keep full streams as artifacts."""
    result = done.result
    cap = _stream_cap(done.req, max_output)
    source_dropped = False
    need = [min(_blen(done.stdout), cap), min(_blen(done.stderr), cap)]
    if result.source:
        source_len = _blen(result.source)
        if sum(need) + source_len > share and source_len > share // 3:
            result.source = ""
            source_dropped = True
        else:
            share -= source_len
    out_cap, err_cap = (cap, cap) if sum(need) <= share else water_fill(need, [0, 0], share, floor=128)

    def cut(text: str, limit: int) -> tuple[str, bool]:
        if _blen(text) <= limit:
            return text, False
        kept, _, _ = truncate_text(text, limit, style="head_tail")
        return kept, True

    stdout_text, stdout_cut = cut(done.stdout, out_cap)
    stderr_text, stderr_cut = cut(done.stderr, err_cap)
    result.budget_cut = stdout_cut or stderr_cut
    stdout_cut = stdout_cut or done.trimmed or done.stdout_changed
    stderr_cut = stderr_cut or done.stderr_changed

    if stdout_cut and done.stdout_raw and not result.stdout_artifact:
        result.stdout_artifact = artifacts.put(done.stdout_raw, ".stdout.txt")
    if stderr_cut and done.stderr_raw:
        result.stderr_artifact = artifacts.put(done.stderr_raw, ".stderr.txt")

    result.stdout = stdout_text
    result.stderr = stderr_text
    result.truncated = stdout_cut or stderr_cut
    result.bytes_shown = _blen(stdout_text) + _blen(stderr_text) + _blen(result.source)
    if result.budget_cut and not result.message:
        ref = result.stdout_artifact or result.stderr_artifact
        result.message = f"output cut to fit; full stream: \"{ref}\"" if ref else "output cut to fit"
    stdout_ref = done.raw_stdout_ref or (result.stdout_artifact if done.stdout_changed else None)
    stderr_ref = result.stderr_artifact if done.stderr_changed else None
    named = (result.message or "") + result.stdout
    refs = [ref for ref in (stdout_ref, stderr_ref) if ref and ref not in named]
    raw_part = "raw: " + ", ".join(f'"{ref}"' for ref in refs) if refs else ""
    if done.note:
        note = done.note + ("; " + raw_part if raw_part else "")
        result.message = f"{result.message}; {note}" if result.message else note
    elif raw_part:
        result.message = f"{result.message}; {raw_part}" if result.message else raw_part
    if source_dropped:
        note = "source lines dropped to fit"
        result.message = f"{result.message}; {note}" if result.message else note
    return result


async def run_commands(
    requests: list[RunRequest],
    *,
    root: str | Path,
    tracker: BudgetTracker,
    artifacts: ArtifactStore,
    parallel: int = DEFAULT_PARALLEL,
    fail_fast: bool = False,
    dry_run: bool = False,
    max_output: int = 64 * 1024,
    locate: bool = False,
    bind_labels: bool = False,
) -> list[RunResult]:
    """Run all requests concurrently, bounded by *parallel* and the deadline.

    Output is kept whole until every command has finished; the batch budget is then
    shared with ``water_fill``, failed and timed-out commands first, so short outputs
    never reserve room they do not use.
    """
    root_p = Path(root).resolve()
    if dry_run:
        dry_results: list[RunResult] = []
        for req in requests:
            res = RunResult(
                id=f"run{req.index}",
                label=req.label,
                cmd_display=req.display or (req.cmd or " ".join(req.argv or [])),
                shell=req.shell,
                cwd=relative_display(root_p, root_p),
            )
            try:
                cmd_cwd = resolve_path(root_p, req.cwd or ".", must_exist=True)
                if not cmd_cwd.is_dir():
                    raise SafetyError(f"cwd is not a directory: {req.cwd or '.'}")
                _, shell_name = _build_process_args(req, root_p)
                res.shell = shell_name
                res.cwd = relative_display(root_p, cmd_cwd)
                if req.slices:
                    _, slice_errs = apply_slices("", req.slices)
                    res.slice_errors.extend(slice_errs)
                res.status = "ok"
                res.message = "dry run: command validated, not executed"
            except Exception as exc:
                res.status = "error"
                res.message = str(exc)
            dry_results.append(res)
        return dry_results

    deadline = time.monotonic() + max(1.0, tracker.budget.time_s)
    semaphore = asyncio.Semaphore(max(1, min(int(parallel), 16)))

    async def guarded(req: RunRequest) -> _Executed:
        if deadline - time.monotonic() <= 0:
            return _blank(req, "skipped", "batch deadline reached before start")
        async with semaphore:
            return await _run_one(req, root=root_p, deadline=deadline)

    if not fail_fast:
        executed = list(await asyncio.gather(*(guarded(req) for req in requests)))
    else:
        tasks = {asyncio.create_task(guarded(req)): req for req in requests}
        finished: dict[int, _Executed] = {}
        try:
            pending = set(tasks)
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                failed = False
                for task in done:
                    req = tasks[task]
                    try:
                        outcome = task.result()
                    except Exception as exc:  # defensive
                        outcome = _blank(req, "error", f"runner failure: {exc}")
                    finished[req.index] = outcome
                    if outcome.result.status in ("error", "timeout"):
                        failed = True
                if failed:
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    for req in tasks.values():
                        if req.index not in finished:
                            finished[req.index] = _blank(
                                req, "skipped", "skipped after an earlier failure (fail_fast)")
                    break
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        executed = [finished.get(req.index) or _blank(req, "skipped", "not run") for req in requests]

    if locate:
        _attach_sources(executed, root_p)
    for item in executed:
        _name_trimmed_artifact(item, artifacts)
    shares = water_fill(
        [_need(done, max_output) for done in executed],
        [0 if done.result.status in ("error", "timeout") else 1 + tier(done.req.priority) for done in executed],
        body_budget(tracker.budget.bytes, len(executed)),
    )
    results = [_finalize(done, share, artifacts, max_output) for done, share in zip(executed, shares)]
    tracker.used_bytes = sum(result.bytes_shown for result in results)
    if bind_labels:
        _bind_labels(executed, root_p, artifacts)
    return results


def _bind_labels(executed: list[_Executed], root: Path, artifacts: ArtifactStore) -> None:
    """Keep each labelled command's full stdout (and stderr) under its label, in request order.

    A command that started rebinds the label, so an old result is never served for a new run; one
    that never started removes it.  A failed bind never changes the report."""
    for done in executed:
        label = done.req.label
        if not artifacts.is_label(label):
            continue
        stderr_label = f"{label}.stderr"
        try:
            result = done.result
            if result.exit_code is None and not result.timed_out:
                artifacts.unbind(root, label)
                artifacts.unbind(root, stderr_label)
                continue
            source = done.req.cmd if done.req.cmd is not None else " ".join(done.req.argv or [])
            artifacts.bind(root, label, done.stdout_raw, ".stdout.txt", source)
            if done.stderr_raw and not done.req.merge_streams:
                artifacts.bind(root, stderr_label, done.stderr_raw, ".stderr.txt", source)
            else:
                artifacts.unbind(root, stderr_label)
        except Exception:
            artifacts.unbind(root, label)
            artifacts.unbind(root, stderr_label)


def run_commands_sync(requests: list[RunRequest], **kwargs: object) -> list[RunResult]:
    return asyncio.run(run_commands(requests, **kwargs))  # type: ignore[arg-type]


def verify_result_ok(result: RunResult) -> bool:
    return result.status == "ok" and result.exit_code == 0


def make_verify_run(req, index: int = 0) -> RunRequest:  # noqa: ANN001 - avoids cycle
    return RunRequest(
        index=index,
        cmd=req.cmd,
        argv=req.argv,
        label=req.label,
        cwd=req.cwd,
        timeout=req.timeout,
        env=req.env,
        shell=req.shell,
        slices=list(req.slices),
        priority="must",
        max_bytes=32 * 1024,
    )

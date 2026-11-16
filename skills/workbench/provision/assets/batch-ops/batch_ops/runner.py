"""Bounded, concurrent command execution.

Commands are independent: a failed, timed-out or unparsable command never stops
the rest of the batch.  Each command receives its own cwd, environment, stdin,
shell and timeout.  On timeout the whole process tree is killed and whatever was
produced before the timeout is still returned.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .artifacts import ArtifactStore
from .budget import BudgetTracker, body_budget, tier, water_fill
from .safety import SafetyError, decode_bytes, format_bytes, relative_display, resolve_path, truncate_text
from .slices import apply_slices
from .types import RunRequest, RunResult

CAPTURE_LIMIT = 16 * 1024 * 1024  # per stream, in memory
SUCCESS_HEAD = 20  # lines kept from the start of a long passing output
SUCCESS_TAIL = 60  # lines kept from its end (summaries live there)
_ARTIFACT_SLOT = "@@STDOUT_ARTIFACT@@"  # filled with the artifact reference once it is saved
DEFAULT_PARALLEL = 4


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


def _resolve_shell(req: RunRequest, root: Path) -> tuple[list[str], str]:
    """Return (argv prefix, shell name) for a string command."""
    shell = req.shell or "auto"
    if req.argv is not None:
        return [], "direct"

    if shell == "direct":
        raise SafetyError("shell='direct' requires argv, not cmd")

    if shell == "auto":
        shell = "cmd" if os.name == "nt" else "sh"

    if shell in ("bash", "sh"):
        exe = shutil.which(shell)
        if not exe:
            raise SafetyError(f"{shell} is not available on PATH")
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
    return text.replace("\r\n", "\n").replace("\r", "\n")


async def _kill_tree(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    if os.name == "nt":
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
        except (OSError, asyncio.SubprocessError):
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

    kwargs: dict[str, object] = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    try:
        stdio = dict(
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
        elif process.returncode == 0:
            result.status = "ok"
            if req.merge_streams and stdout_cap.data:
                result.message = "stderr merged into stdout"
        else:
            result.status = "error"
            result.message = f"exit code {process.returncode}"

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

    stdout_text = _normalize_output(decode_bytes(bytes(stdout_cap.data)).text)
    stderr_text = _normalize_output(decode_bytes(bytes(stderr_cap.data)).text)

    if req.slices:
        stdout_text, errors = apply_slices(stdout_text, req.slices)
        result.slice_errors.extend(f"stdout {e}" for e in errors)
        if not req.merge_streams:
            stderr_text, errors = apply_slices(stderr_text, req.slices)
            result.slice_errors.extend(f"stderr {e}" for e in errors)

    # A passing command's long output is rarely read in full: keep its head and tail.
    # Failures keep everything (failure-first), and explicit slices always win.
    if not req.slices and result.status == "ok":
        out_lines = stdout_text.splitlines()
        if len(out_lines) > SUCCESS_HEAD + SUCCESS_TAIL + 40:
            omitted = len(out_lines) - SUCCESS_HEAD - SUCCESS_TAIL
            stdout_text = "\n".join(
                out_lines[:SUCCESS_HEAD]
                + [f"[... {omitted} lines of passing output omitted; read them with batch_read "
                   f"\"{_ARTIFACT_SLOT}:{SUCCESS_HEAD + 1}-{SUCCESS_HEAD + omitted}\" ...]"]
                + out_lines[-SUCCESS_TAIL:]
            ) + "\n"
            done.trimmed = True

    if stdout_cap.dropped or stderr_cap.dropped:
        note = f"output capture capped at {format_bytes(CAPTURE_LIMIT)} per stream"
        result.message = f"{result.message}; {note}" if result.message else note

    done.stdout, done.stderr = stdout_text, stderr_text
    done.stdout_raw, done.stderr_raw = bytes(stdout_cap.data), bytes(stderr_cap.data)
    return done


def _name_trimmed_artifact(done: _Executed, artifacts: ArtifactStore) -> None:
    """Save a trimmed passing stream and put its name in the trim hint, so the hint is a
    spec to paste.  Runs before the budget is shared, so the sizes include the real name."""
    if done.trimmed and done.stdout_raw:
        done.result.stdout_artifact = artifacts.put(done.stdout_raw, ".stdout.txt")
        done.stdout = done.stdout.replace(_ARTIFACT_SLOT, done.result.stdout_artifact, 1)


def _blen(text: str) -> int:
    return len(text.encode("utf-8", errors="replace"))


def _stream_cap(req: RunRequest, max_output: int) -> int:
    """A command's own inline cap per stream (its max_bytes, split when streams are separate)."""
    per_command = max(256, min(max_output, max(256, req.max_bytes)))
    return per_command if req.merge_streams else max(256, per_command // 2)


def _need(done: _Executed, max_output: int) -> int:
    cap = _stream_cap(done.req, max_output)
    return min(_blen(done.stdout), cap) + min(_blen(done.stderr), cap)


def _finalize(done: _Executed, share: int, artifacts: ArtifactStore, max_output: int) -> RunResult:
    """Cut each stream to the command's share of the batch budget and keep full streams as artifacts."""
    result = done.result
    cap = _stream_cap(done.req, max_output)
    need = [min(_blen(done.stdout), cap), min(_blen(done.stderr), cap)]
    out_cap, err_cap = (cap, cap) if sum(need) <= share else water_fill(need, [0, 0], share, floor=128)

    def cut(text: str, limit: int) -> tuple[str, bool]:
        if _blen(text) <= limit:
            return text, False
        kept, _, _ = truncate_text(text, limit, style="head_tail")
        return kept, True

    stdout_text, stdout_cut = cut(done.stdout, out_cap)
    stderr_text, stderr_cut = cut(done.stderr, err_cap)
    stdout_cut = stdout_cut or done.trimmed

    if stdout_cut and done.stdout_raw and not result.stdout_artifact:
        result.stdout_artifact = artifacts.put(done.stdout_raw, ".stdout.txt")
    if stderr_cut and done.stderr_raw:
        result.stderr_artifact = artifacts.put(done.stderr_raw, ".stderr.txt")

    result.stdout = stdout_text
    result.stderr = stderr_text
    result.truncated = stdout_cut or stderr_cut
    result.bytes_shown = _blen(stdout_text) + _blen(stderr_text)
    if result.truncated and not result.message:
        ref = result.stdout_artifact or result.stderr_artifact
        result.message = f"output cut to fit; full stream: batch_read \"{ref}\"" if ref else "output cut to fit"
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

    for done in executed:
        _name_trimmed_artifact(done, artifacts)
    shares = water_fill(
        [_need(done, max_output) for done in executed],
        [0 if done.result.status in ("error", "timeout") else 1 + tier(done.req.priority) for done in executed],
        body_budget(tracker.budget.bytes, len(executed)),
    )
    results = [_finalize(done, share, artifacts, max_output) for done, share in zip(executed, shares)]
    tracker.used_bytes = sum(result.bytes_shown for result in results)
    return results


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
        priority="must",
        max_bytes=32 * 1024,
    )

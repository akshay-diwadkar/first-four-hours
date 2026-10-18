#!/usr/bin/env python3
"""Bound public validation commands and contain their process trees."""

from __future__ import annotations

import ctypes
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, BinaryIO

# One deadline per command; reserve cleanup/reporting before starting work.
# Exhaustion is incomplete verification, never evidence of correct behavior.
PUBLIC_BUDGET_SECONDS = 120.0
WORK_BUDGET_SECONDS = 110.0
CLEANUP_BUDGET_SECONDS = 6.0
REPORT_BUDGET_SECONDS = 4.0
# Advisory only. Reported as `slow` so a regression in routine cost is visible
# without failing a run whose tests all passed.
ROUTINE_TARGET_SECONDS = 80.0
MAX_STREAM_BYTES = 16 * 1024 * 1024
TAIL_BYTES = 64 * 1024


class VerificationLock:
    """Permit one command at a time without storing a spent-time allowance."""

    def __init__(self, root: Path):
        self.directory = root / ".scratch"
        self.lock: BinaryIO | None = None

    def open(self) -> None:
        self.directory.mkdir(exist_ok=True)
        path = self.directory / "verification-budget.lock"
        if self.directory.is_symlink() or path.is_symlink():
            raise RuntimeError("unsafe_verification_lock")
        self.lock = path.open("a+b")
        self.lock.seek(0, os.SEEK_END)
        if self.lock.tell() == 0:
            self.lock.write(b"0")
            self.lock.flush()
        self.lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                getattr(fcntl, "flock")(self.lock.fileno(), getattr(fcntl, "LOCK_EX") | getattr(fcntl, "LOCK_NB"))
        except OSError as exc:
            self.close()
            raise RuntimeError("verification_already_running") from exc

    def close(self) -> None:
        if self.lock is not None:
            self.lock.close()
            self.lock = None


class OutputLimitError(RuntimeError):
    """A child exceeded the bounded capture size."""


def run_capture(
    argv: list[str], *, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[bytes]:
    """Capture a child to disk, enforcing a finite limit without pipe deadlock."""
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=stdout_file, stderr=stderr_file)
        while process.poll() is None:
            if os.fstat(stdout_file.fileno()).st_size > MAX_STREAM_BYTES or os.fstat(stderr_file.fileno()).st_size > MAX_STREAM_BYTES:
                process.kill()
                process.wait()
                raise OutputLimitError(f"child output exceeded {MAX_STREAM_BYTES} bytes per stream")
            try:
                process.wait(timeout=0.05)
            except subprocess.TimeoutExpired:
                pass
        if os.fstat(stdout_file.fileno()).st_size > MAX_STREAM_BYTES or os.fstat(stderr_file.fileno()).st_size > MAX_STREAM_BYTES:
            raise OutputLimitError(f"child output exceeded {MAX_STREAM_BYTES} bytes per stream")
        stdout_file.seek(0)
        stderr_file.seek(0)
        return subprocess.CompletedProcess(argv, process.returncode, stdout_file.read(), stderr_file.read())


_BOOTSTRAP = r'''
import json, runpy, sys
from pathlib import Path
script = Path(sys.argv[1])
arguments = json.loads(sys.argv[2])
sys.path.insert(0, sys.argv[3])
sys.path.insert(0, str(script.parent))
from validation_budget import OutputLimitError
sys.argv = [str(script), *arguments]
if sys.stdin.buffer.read(1) != b"1":
    raise SystemExit(3)
try:
    namespace = runpy.run_path(str(script), run_name="_bounded_worker")
    result = namespace["main"]()
    raise SystemExit(0 if result is None else int(result))
except OutputLimitError as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(4)
'''


def _windows_job(process: subprocess.Popen[bytes]) -> tuple[Any, Any]:
    """Assign the blocked worker to a kill-on-close Windows Job Object."""
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL

    class BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class ExtendedLimit(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BasicLimit), ("IoInfo", IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
    limits = ExtendedLimit()
    limits.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        kernel.CloseHandle(job)
        raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")
    handle = kernel.OpenProcess(0x0100 | 0x0001, False, process.pid)  # SET_QUOTA | TERMINATE
    if not handle:
        kernel.CloseHandle(job)
        raise OSError(ctypes.get_last_error(), "OpenProcess failed")
    if not kernel.AssignProcessToJobObject(job, handle):
        error = ctypes.get_last_error()
        kernel.CloseHandle(handle)
        kernel.CloseHandle(job)
        raise OSError(error, "AssignProcessToJobObject failed")
    kernel.CloseHandle(handle)
    return kernel, job


def _job_active(kernel: Any, job: Any) -> int:
    from ctypes import wintypes

    class BasicAccounting(ctypes.Structure):
        _fields_ = [("TotalUserTime", ctypes.c_longlong), ("TotalKernelTime", ctypes.c_longlong), ("ThisPeriodTotalUserTime", ctypes.c_longlong), ("ThisPeriodTotalKernelTime", ctypes.c_longlong), ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD), ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD)]

    kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
    kernel.QueryInformationJobObject.restype = wintypes.BOOL
    accounting = BasicAccounting()
    if not kernel.QueryInformationJobObject(job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None):
        raise OSError(ctypes.get_last_error(), "QueryInformationJobObject failed")
    return int(accounting.ActiveProcesses)


def _tail(path: Any) -> bytes:
    path.flush()
    size = os.fstat(path.fileno()).st_size
    path.seek(max(0, size - TAIL_BYTES))
    return path.read(TAIL_BYTES)


def _deadline_due(now: float, deadline: float) -> bool:
    """Use an inclusive deadline so equality never counts as success."""
    return now >= deadline


def _cleanup_deadline(started_at: float, now: float) -> float:
    return min(started_at + PUBLIC_BUDGET_SECONDS, now + CLEANUP_BUDGET_SECONDS)


def _posix_kill_group(pid: int) -> None:
    getattr(os, "killpg")(pid, getattr(signal, "SIGKILL"))


def _posix_group_exists(pid: int) -> None:
    getattr(os, "killpg")(pid, 0)


def _write_record(record: dict[str, Any], started_at: float, stdout_tail: str = "", stderr_tail: str = "", *, deadline: float | None = None) -> bool:
    if deadline is not None and time.monotonic() >= deadline:
        return False
    prefix = stdout_tail
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    stdout_payload = (prefix + json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n").encode()
    stderr_payload = stderr_tail.encode()
    if stderr_payload and not stderr_tail.endswith("\n"):
        stderr_payload += b"\n"
    done = threading.Event()
    emitted = [False]

    def emit() -> None:
        try:
            if stderr_payload:
                sys.stderr.buffer.write(stderr_payload)
                sys.stderr.buffer.flush()
            sys.stdout.buffer.write(stdout_payload)
            sys.stdout.buffer.flush()
            emitted[0] = True
        except (OSError, ValueError, AttributeError):
            emitted[0] = False
        finally:
            done.set()

    threading.Thread(target=emit, daemon=True).start()
    # This is a flush allowance for the record, not a share of the work budget.
    # Deriving it from started_at made it go negative as soon as a legitimate run
    # exceeded the old deadline, and the record was silently never written.
    done.wait(min(REPORT_BUDGET_SECONDS, max(0.0, deadline - time.monotonic())) if deadline is not None else REPORT_BUDGET_SECONDS)
    return done.is_set() and emitted[0]


def _terminate(process: subprocess.Popen[bytes], started_at: float, kernel: Any = None, job: Any = None, *, public_deadline: float | None = None) -> bool:
    deadline = _cleanup_deadline(started_at, time.monotonic())
    if public_deadline is not None:
        deadline = min(deadline, public_deadline - REPORT_BUDGET_SECONDS)
    try:
        if os.name == "nt":
            from ctypes import wintypes

            if job is None:
                # The release byte is written only after containment succeeds, so
                # the blocked bootstrap cannot have created descendants here.
                process.terminate()
                process.wait(timeout=max(0.01, deadline - time.monotonic()))
                return True
            kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
            kernel.TerminateJobObject.restype = wintypes.BOOL
            if not kernel.TerminateJobObject(job, 1):
                return False
            while job and time.monotonic() < deadline:
                if _job_active(kernel, job) == 0:
                    break
                time.sleep(0.02)
            if job and _job_active(kernel, job) != 0:
                return False
        else:
            try:
                _posix_kill_group(process.pid)
            except ProcessLookupError:
                pass
            while time.monotonic() < deadline:
                process.poll()
                try:
                    _posix_group_exists(process.pid)
                except ProcessLookupError:
                    break
                time.sleep(0.02)
            else:
                return False
        process.wait(timeout=max(0.01, deadline - time.monotonic()))
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        if job:
            kernel.CloseHandle(job)


def bounded_main(script: Path, argv: list[str], root: Path, *, started_at: float,
                 manifest: Path | None = None, expect_cases: bool = False) -> int:
    """Run one public validation CLI inside a bounded, contained worker."""
    root = root.resolve()
    identity = {"repo_root": str(root), "manifest": str(manifest.resolve()) if manifest is not None else None}
    if os.environ.get("SKILLS_VALIDATION_ACTIVE"):
        print(json.dumps({**identity, "event": "validation-budget", "status": "failed", "valid": False, "elapsed_seconds": 0, "budget_seconds": 60, "worker_exit": 2, "reason": "nested_validation_unsupported", "complete": True}, separators=(",", ":")))
        return 2
    lock = VerificationLock(root)
    try:
        lock.open()
    except (OSError, RuntimeError) as exc:
        lock.close()
        print(json.dumps({**identity, "event": "validation-budget", "status": "incomplete", "valid": False,
                          "complete": False, "reason": str(exc), "budget_seconds": PUBLIC_BUDGET_SECONDS,
                          "unverified": argv}, separators=(",", ":")))
        return 3
    public_deadline = started_at + PUBLIC_BUDGET_SECONDS
    progress = tempfile.NamedTemporaryFile(prefix="verification-cases-", suffix=".jsonl", delete=False)
    progress_path = Path(progress.name)
    progress.close()
    environment = os.environ.copy()
    environment["SKILLS_VALIDATION_ACTIVE"] = "1"
    environment["SKILLS_CASE_REPORT"] = str(progress_path)
    process: subprocess.Popen[bytes] | None = None
    kernel = job = None
    outcome = "incomplete"
    reason = "containment_setup"
    worker_exit: int | None = None
    cleanup_ok = False
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
            process = subprocess.Popen([sys.executable, "-c", _BOOTSTRAP, str(script.resolve()), json.dumps(argv), str(Path(__file__).resolve().parent)], cwd=root, env=environment, stdin=subprocess.PIPE, stdout=stdout_file, stderr=stderr_file, start_new_session=os.name != "nt", creationflags=flags)
            if os.name == "nt":
                kernel, job = _windows_job(process)
            if process.stdin is None:
                raise OSError("worker release gate unavailable")
            process.stdin.write(b"1")
            process.stdin.close()
            work_deadline = started_at + WORK_BUDGET_SECONDS
            while not _deadline_due(time.monotonic(), work_deadline):
                if os.fstat(stdout_file.fileno()).st_size > MAX_STREAM_BYTES or os.fstat(stderr_file.fileno()).st_size > MAX_STREAM_BYTES:
                    outcome, reason = "output_limit", "worker_output_limit"
                    break
                worker_exit = process.poll()
                if worker_exit is not None:
                    outcome, reason = "finished", "worker_exit"
                    break
                try:
                    process.wait(timeout=0.05)
                except subprocess.TimeoutExpired:
                    pass
            else:
                outcome, reason = "budget_exceeded", "work_deadline"
            cleanup_ok = _terminate(process, started_at, kernel, job, public_deadline=public_deadline)
            job = None  # _terminate closes it.
            stdout_exceeds_replay = os.fstat(stdout_file.fileno()).st_size > TAIL_BYTES
            if not cleanup_ok:
                outcome, reason = "incomplete", "cleanup_unconfirmed"
            elif stdout_exceeds_replay and outcome != "output_limit":
                outcome, reason = "output_limit", "stdout_replay_limit"
            elif outcome == "budget_exceeded":
                pass
            elif outcome == "output_limit":
                pass
            elif worker_exit == 4:
                outcome, reason = "output_limit", "child_output_limit"
            elif worker_exit == 3:
                outcome, reason = "incomplete", "worker_incomplete"
            elif worker_exit == 2:
                outcome, reason = "failed", "selection_or_usage_error"
            elif worker_exit == 0:
                outcome, reason = "passed", "worker_succeeded"
            else:
                outcome, reason = "failed", "worker_failed"
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            reason = f"containment_setup:{type(exc).__name__}"
            if process is not None:
                cleanup_ok = _terminate(process, started_at, kernel, job, public_deadline=public_deadline)
                job = None
            outcome = "incomplete"
        except BaseException as exc:
            reason = f"supervisor_error:{type(exc).__name__}"
            if process is not None:
                cleanup_ok = _terminate(process, started_at, kernel, job, public_deadline=public_deadline)
                job = None
            outcome = "incomplete"
        stdout_tail = _tail(stdout_file).decode("utf-8", errors="replace") if os.fstat(stdout_file.fileno()).st_size <= TAIL_BYTES else ""
        stderr_tail = _tail(stderr_file).decode("utf-8", errors="replace")
    collected: set[str] = set()
    completed: set[str] = set()
    called: set[str] = set()
    failed: set[str] = set()
    try:
        for line in progress_path.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError("case report record must be an object")
            if item.get("event") == "collection":
                if not isinstance(item.get("nodes"), list) or any(not isinstance(node, str) for node in item["nodes"]):
                    raise ValueError("case collection nodes must be strings")
                collected.update(item["nodes"])
            elif item.get("event") == "case":
                if not isinstance(item.get("nodeid"), str) or item.get("phase") not in {"setup", "call", "teardown"} or item.get("outcome") not in {"passed", "failed", "skipped"}:
                    raise ValueError("case report shape is invalid")
                if item["phase"] == "call" and item["outcome"] != "skipped":
                    called.add(item["nodeid"])
                if item["phase"] == "teardown" and item["nodeid"] in called:
                    completed.add(item["nodeid"])
                if item["outcome"] == "failed":
                    failed.add(item["nodeid"])
            else:
                raise ValueError("unknown case report event")
    except (OSError, ValueError, KeyError, TypeError):
        outcome, reason = "incomplete", "case_accounting_unconfirmed"
        cleanup_ok = False
    finally:
        try:
            progress_path.unlink(missing_ok=True)
        except OSError:
            outcome, reason = "incomplete", "case_report_cleanup_unconfirmed"
            cleanup_ok = False
    if outcome == "passed" and failed:
        outcome, reason = "failed", "cases_failed"
    if outcome == "passed" and (collected - completed or expect_cases and not collected):
        outcome, reason = "incomplete", "cases_unverified"
    elapsed = max(0.0, time.monotonic() - started_at)
    if elapsed + REPORT_BUDGET_SECONDS >= PUBLIC_BUDGET_SECONDS:
        outcome, reason = "incomplete", "report_deadline"
    complete = outcome in {"passed", "failed"} and not collected - completed
    record = {**identity, "event": "validation-budget", "status": outcome, "valid": outcome == "passed", "elapsed_seconds": elapsed, "budget_seconds": PUBLIC_BUDGET_SECONDS, "worker_exit": worker_exit, "complete": complete, "reason": reason, "advisory_target_seconds": ROUTINE_TARGET_SECONDS, "slow": elapsed > ROUTINE_TARGET_SECONDS, "failed_cases": sorted(failed)}
    if collected - completed:
        record["unverified_cases"] = sorted(collected - completed)
    if not complete:
        record["unverified"] = argv
    exit_code = 0 if outcome == "passed" else 1 if outcome == "failed" and worker_exit != 2 else 2 if outcome == "failed" else 3
    if not _write_record(record, started_at, stdout_tail, stderr_tail, deadline=public_deadline):
        lock.close()
        os._exit(3)
    lock.close()
    return exit_code

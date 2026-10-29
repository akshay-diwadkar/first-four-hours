"""Run authored Verification Runs and instruction proofs exactly, in authored order.

Stateless Construct runner: validates the sealed Blueprint (full establishment
at phase `before`, authority checks otherwise), executes exactly the requested
authored commands with timeout, process-tree cleanup, and a mutation guard that
binds the Git index and all worktree content, including ignored entries (bytes,
size, mode, kind), and returns each command's full output. Phase `after` first
proves every Exact/Frozen block. `prove` observes one instruction's declared red
or its bounded green attempts, then names the next in-run action; `status` derives
resume progress from the sealed plan and current worktree. A repair-only `reverify` selection
reruns one authored after-implementation Run and every later entry. `apply` writes one
instruction's declared Exact/Frozen text into its Location files, or nothing. It writes no
artifact and persists no state.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

import blueprint_runtime
from _diagnostic_contract import normalize_diagnostic

BLUEPRINT_CONTRACT_VERSION = blueprint_runtime.CONTRACT_VERSION
BASELINE_PHASE = "Before implementation"
FINAL_PHASE = "After implementation"
STEP_ATTEMPT_LIMIT = blueprint_runtime.STEP_ATTEMPT_LIMIT
DIFF_LIMIT_CHARS = 20000


class ConstructError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        category: str = "contract_contradiction",
        owner: str = "construct",
        evidence: Sequence[str] = (),
        result: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
        valid_repairs: Sequence[str] | None = None,
        next_command: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.category = category
        self.owner = owner
        self.evidence = tuple(evidence) or (message,)
        self.result = result
        self.details = details
        self.valid_repairs = tuple(valid_repairs) if valid_repairs else None
        self.next_command = next_command
        self.path = "blueprint.md"

    def _required_action(self) -> str:
        if self.owner == "blueprint":
            return "Return the contradiction to Blueprint, obtain a fresh sealed Blueprint, and start a new Construct run."
        if self.valid_repairs:
            return self.valid_repairs[0]
        if self.category == "unsafe_state":
            return "Preserve unrelated work and resume only from a trusted repository state or explicit authority."
        return "Repair the named local contract defect and retry the same Construct action."

    def diagnostic(self, *, phase: str = "verify") -> dict[str, Any]:
        action = self._required_action()
        return normalize_diagnostic(
            {
                "code": self.code,
                "category": self.category,
                "severity": "error",
                "message": self.message,
                "path": self.path,
                "required_action": action,
                "valid_repairs": list(self.valid_repairs or (action,)),
                "supporting_evidence": list(self.evidence),
                "next_command": self.next_command,
                "details": {"owner": self.owner, **(self.details or {})},
            },
            skill="construct",
            phase=phase,
            artifact=self.path,
            path=self.path,
        )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _write_utf8(text: str) -> None:
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(text.encode("utf-8"))
        sys.stdout.flush()
        return
    sys.stdout.write(text)


def _emit_error(error: ConstructError) -> int:
    payload: dict[str, Any] = {"diagnostics": [error.diagnostic(phase="verify")]}
    if error.result is not None:
        payload["result"] = error.result
    _write_utf8(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 3


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    except OSError as exc:
        raise ConstructError("workspace.git_failed", str(exc), category="unsafe_state") from exc


def _checked_git_bytes(root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)
    except OSError as exc:
        raise ConstructError("workspace.git_failed", str(exc), category="unsafe_state") from exc
    if result.returncode != 0:
        raise ConstructError("workspace.git_failed", "cannot observe Git " + " ".join(args) + ": " + result.stderr.decode("utf-8", errors="replace"), category="unsafe_state")
    return result.stdout


def _git_head(root: Path) -> str | None:
    result = _git(root, "rev-parse", "HEAD")
    return result.stdout.strip() if result.returncode == 0 else None


def _git_index_sha256(root: Path) -> str:
    return _sha256(_checked_git_bytes(root, "diff", "--cached", "--binary", "--no-ext-diff"))


def _git_dirty_entries(root: Path) -> dict[str, str]:
    raw = _checked_git_bytes(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    chunks, entries, index = raw.split(b"\0"), {}, 0
    while index < len(chunks):
        chunk = chunks[index]
        if not chunk:
            index += 1
            continue
        text = chunk.decode("utf-8", errors="surrogateescape")
        status, path = text[:2], text[3:].replace("\\", "/")
        entries[path] = status
        if "R" in status or "C" in status:
            index += 1
            if index < len(chunks) and chunks[index]:
                entries[chunks[index].decode("utf-8", errors="surrogateescape").replace("\\", "/")] = status
        index += 1
    return entries


def _entry_identity(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {"kind": "absent", "sha256": None, "size": None, "mode": None}
    mode = stat.S_IMODE(metadata.st_mode)
    if stat.S_ISLNK(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode) and getattr(metadata, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        value = os.readlink(path)
        data = os.fsencode(value)
        return {"kind": "symlink", "sha256": _sha256(data), "size": len(data), "mode": mode}
    if stat.S_ISDIR(metadata.st_mode):
        return {"kind": "directory", "sha256": None, "size": None, "mode": mode}
    if not stat.S_ISREG(metadata.st_mode):
        raise OSError(f"cannot fingerprint non-regular worktree entry: {relative}")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"kind": "file", "sha256": digest, "size": metadata.st_size, "mode": mode}


def _worktree_fingerprint(root: Path) -> dict[str, dict[str, Any]]:
    """Observe ignored content too, without traversing Git metadata or links."""
    entries: dict[str, dict[str, Any]] = {}

    def failed(error: OSError) -> None:
        raise error

    try:
        for current, directories, files in os.walk(root, followlinks=False, onerror=failed):
            for name in directories[:] + files:
                if name.casefold() == ".git":
                    if name in directories:
                        directories.remove(name)
                    continue
                relative = (Path(current) / name).relative_to(root).as_posix()
                identity = _entry_identity(root, relative)
                if identity["kind"] == "absent":
                    raise OSError(f"worktree entry disappeared during observation: {relative}")
                entries[relative] = identity
                if name in directories and identity["kind"] != "directory":
                    directories.remove(name)
    except OSError as exc:
        raise ConstructError("workspace.snapshot_unavailable", str(exc), category="unsafe_state") from exc
    return entries


def _workspace_observation(root: Path) -> dict[str, Any]:
    entries = _git_dirty_entries(root)
    try:
        dirty = [{"path": path, "status": entries[path], **_entry_identity(root, path)} for path in sorted(entries)]
    except OSError as exc:
        raise ConstructError("workspace.snapshot_unavailable", str(exc), category="unsafe_state") from exc
    return {
        "git_head": _git_head(root),
        "worktree_sha256": _sha256(_canonical_json(_worktree_fingerprint(root)).encode("utf-8", errors="surrogateescape")),
        "dirty": dirty,
    }


def _bounded_tail(value: str) -> dict[str, Any]:
    lines = value.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    selected = lines[-4:]
    text = "\n".join(selected)
    truncated = len(lines) > 4 or len(text) > 800
    if len(text) > 800:
        text = text[:390] + "\n…\n" + text[-390:]
    return {"tail": text, "truncated": truncated}


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            if process.poll() is None:
                process.kill()
    else:
        kill_process_group = getattr(os, "killpg", None)
        if kill_process_group is None:
            if process.poll() is None:
                process.terminate()
        else:
            try:
                kill_process_group(process.pid, 15)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        if kill_process_group is not None:
            try:
                kill_process_group(process.pid, 9)
            except ProcessLookupError:
                pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()


def _timeout_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


def _drain_terminated_process(process: subprocess.Popen[str]) -> tuple[str, str]:
    try:
        return process.communicate(timeout=2)
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = _timeout_text(exc.output), _timeout_text(exc.stderr)
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        return stdout, stderr


def _execute_exact_step(step: blueprint_runtime.VerificationStep, repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.monotonic()
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    try:
        process = subprocess.Popen(
            list(step.argv),
            cwd=repo_root,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=os.name != "nt",
            creationflags=creationflags,
        )
    except OSError as exc:
        elapsed_ms = max(0, int((time.monotonic() - started) * 1000))
        step_value = step.to_dict()
        stderr = f"cannot launch verification step: {exc}"
        receipt = {
            "step": step_value,
            "returncode": 127,
            "passed": False,
            "elapsed_ms": elapsed_ms,
            "stdout_sha256": _sha256(b""),
            "stderr_sha256": _sha256(stderr.encode()),
        }
        summary = {
            "step": step_value,
            "returncode": 127,
            "passed": False,
            "timed_out": False,
            "launch_error": True,
            "elapsed_ms": elapsed_ms,
            "stdout": _bounded_tail(""),
            "stderr": _bounded_tail(stderr),
            "stdout_full": "",
            "stderr_full": stderr,
        }
        return receipt, summary
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=step.timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_tree(process)
        stdout, stderr = _drain_terminated_process(process)
    elapsed_ms = max(0, int((time.monotonic() - started) * 1000))
    step_value = step.to_dict()
    passed = process.returncode == 0 and not timed_out
    receipt = {
        "step": step_value,
        "returncode": process.returncode if process.returncode is not None else -9,
        "passed": passed,
        "elapsed_ms": elapsed_ms,
        "stdout_sha256": _sha256(stdout.encode()),
        "stderr_sha256": _sha256(stderr.encode()),
    }
    summary = {
        "step": step_value,
        "returncode": receipt["returncode"],
        "passed": passed,
        "timed_out": timed_out,
        "launch_error": False,
        "elapsed_ms": elapsed_ms,
        "stdout": _bounded_tail(stdout),
        "stderr": _bounded_tail(stderr),
        "stdout_full": stdout,
        "stderr_full": stderr,
    }
    return receipt, summary


def _stdout_json(value: str) -> Any:
    """Parse stdout as one JSON document, or as JSON-object lines, else None."""
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    records: list[Any] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(record, dict):
            return None
        records.append(record)
    return records


def _result_entry(summary: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "step": summary["step"],
        "returncode": summary["returncode"],
        "timed_out": summary["timed_out"],
        "launch_error": summary["launch_error"],
        "passed": summary["passed"],
        "elapsed_ms": summary["elapsed_ms"],
        "stdout": summary["stdout_full"],
        "stderr": summary["stderr_full"],
    }
    parsed = _stdout_json(summary["stdout_full"])
    if parsed is not None:
        entry["stdout_json"] = parsed
    return entry


def _notices(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Surface records a check itself declared slow; they never change pass/fail."""
    notices = []
    for result in results:
        parsed = result.get("stdout_json")
        records = parsed if isinstance(parsed, list) else [parsed]
        for record in records:
            if isinstance(record, dict) and record.get("slow") is True:
                notices.append({"line": result["step"]["line"], "slow": True, "record": record})
    return notices


def _positive_int(value: str, name: str = "from_line") -> int:
    try:
        number = int(str(value).strip(), 10)
    except ValueError:
        raise ConstructError(
            "verification.selection_invalid",
            f"{name} must be a positive integer, got {value!r}",
        ) from None
    if number <= 0:
        raise ConstructError(
            "verification.selection_invalid",
            f"{name} must be a positive integer, got {value!r}",
        )
    return number


def _selected_steps(steps: list[blueprint_runtime.VerificationStep], from_line: int | None) -> list[blueprint_runtime.VerificationStep]:
    if from_line is None:
        return steps
    start = next((i for i, step in enumerate(steps) if step.line == from_line), None)
    if start is None:
        available = [step.line for step in steps]
        raise ConstructError(
            "verification.selection_invalid",
            f"from_line {from_line} does not match an authored {FINAL_PHASE} Run line",
            evidence=(f"available {FINAL_PHASE} Run lines: {json.dumps(available)}",),
        )
    return steps[start:]


def _cli_command(root: Path, blueprint: Path, inputs: Sequence[str], command: str) -> dict[str, Any]:
    argv = [sys.executable, str(Path(__file__).with_name("cli.py")), "--repo-root", str(root)]
    for value in (f"blueprint_file={blueprint}", *inputs):
        argv.extend(["--input", value])
    return {"argv": [*argv, "--format", "json", command], "cwd": str(root)}


def _reverify_next_command(root: Path, blueprint: Path, step_line: int) -> dict[str, Any]:
    return _cli_command(root, blueprint, [f"from_line={step_line}"], "reverify")


def _prove_command(root: Path, blueprint: Path, number: int, check: str, attempt: int) -> dict[str, Any]:
    return _cli_command(root, blueprint, [f"instruction={number}", f"check={check}", f"attempt={attempt}"], "prove")


def _apply_command(root: Path, blueprint: Path, number: int, blocks: str | None) -> dict[str, Any]:
    inputs = [f"instruction={number}"] + ([f"blocks={blocks}"] if blocks is not None else [])
    return _cli_command(root, blueprint, inputs, "apply")


def _apply_first(
    root: Path,
    blueprint: Path,
    step: blueprint_runtime.ImplementationStep,
    found: Sequence[dict[str, Any]],
    then: dict[str, Any],
    *,
    red_pending: bool = False,
) -> dict[str, Any]:
    """Route an instruction's unapplied declared text through apply before ``then``.

    Diverged text needs a repair apply refuses, so it keeps ``then``; a pending red keeps Exact text waiting.
    """
    if any(item["state"] == "diverged" for item in found):
        return then
    unapplied = {item["kind"] for item in found if item["state"] == "unapplied"}
    if "frozen" in unapplied:
        return _apply_command(root, blueprint, step.number, "frozen" if step.red is not None else None)
    if "exact" in unapplied and not red_pending:
        return _apply_command(root, blueprint, step.number, "exact" if step.red is not None else None)
    return then


def _first_command(
    root: Path, blueprint: Path, step: blueprint_runtime.ImplementationStep, attempt: int, found: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    """Resume a pending instruction: apply its unapplied declared text, then prove it."""
    unapplied = {item["line"] for item in found if item["state"] == "unapplied"}
    red_pending = (step.red is not None
                   and all(block.line in unapplied for block in step.blocks if block.kind == "exact")
                   and all(location.line in unapplied for location in step.locations if location.state == "deleted"))
    then = _prove_command(root, blueprint, step.number, "red" if red_pending else "green", attempt)
    return _apply_first(root, blueprint, step, found, then, red_pending=red_pending)


def _after_command(root: Path, blueprint: Path) -> dict[str, Any]:
    return _cli_command(root, blueprint, ["phase=after"], "verify")


def _forward_action(root: Path, path: Path, blueprint: blueprint_runtime.Blueprint, number: int) -> dict[str, Any]:
    judge = f"Confirm instruction {number} realizes its sealed behavior and preservation rules, and judge its declared Expect before continuing."
    if number == len(blueprint.steps):
        return {
            "next_instruction": None,
            "required_action": judge + " Then run the returned verify after command.",
            "next_command": _after_command(root, path),
        }
    following = blueprint.steps[number]
    kinds = {block.kind for block in following.blocks}
    if following.red is not None:
        frozen = f"Run apply with instruction={following.number} and blocks=frozen. " if "frozen" in kinds else ""
        exact = "Run apply with blocks=exact. " if "exact" in kinds else ""
        action = (
            f"{frozen}Run prove with instruction={following.number}, check=red, and its caller-held next unused "
            f"attempt. Confirm the declared Red defect. {exact}Implement the rest, then run prove with "
            f"instruction={following.number}, check=green, and its caller-held next unused attempt."
        )
    else:
        applying = f"Run apply with instruction={following.number}. " if kinds else ""
        action = (
            f"{applying}Implement the rest, then run prove with instruction={following.number}, check=green, "
            "and its caller-held next unused attempt."
        )
    return {
        "next_instruction": following.number,
        "required_action": f"{judge} Next: instruction {following.number}, {following.title}. {action} Stop if its attempt history is unavailable or exhausted.",
        "next_command": None,
    }


def _worktree_text(root: Path, relative: str) -> str | None:
    text = _file_text(root, relative)
    return None if text == blueprint_runtime.UNREADABLE else text


def _file_text(root: Path, relative: str) -> str | None:
    """LF-normalized text, None when absent, or the runtime's UNREADABLE sentinel."""
    path = root / relative
    if not os.path.lexists(path):
        return None
    try:
        if path.is_symlink() or not path.is_file():
            return blueprint_runtime.UNREADABLE
        return path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError):
        return blueprint_runtime.UNREADABLE


def _closest_diff(expected: str, current: str, path: str) -> str:
    """Diff the expected lines against the most similar same-length window of the file."""
    wanted = expected.splitlines(keepends=True)
    lines = current.splitlines(keepends=True)
    size = max(1, len(wanted))
    best, best_ratio = lines[:size], -1.0
    for start in range(max(1, len(lines) - size + 1)):
        window = lines[start : start + size]
        ratio = difflib.SequenceMatcher(None, wanted, window).ratio()
        if ratio > best_ratio:
            best, best_ratio = window, ratio
    diff = "".join(difflib.unified_diff(wanted, best, f"planned {path}", f"current {path}"))
    return diff[:DIFF_LIMIT_CHARS]


def _block_mismatch(
    current: str | None, block: blueprint_runtime.TextBlock, state: str, reason: str | None,
    prerequisites: Sequence[int] = (),
) -> dict[str, Any] | None:
    """Describe a classified block against actual, never projected, file text."""
    if state == "exact":
        return None
    found: dict[str, Any] = {"path": block.path, "kind": block.kind, "line": block.line, "state": state, "reason": reason}
    if prerequisites:
        found["prerequisites"] = list(prerequisites)
    if current is None or current == blueprint_runtime.UNREADABLE:
        return {**found, "diff": ""}
    if block.old is None:
        diff = "".join(
            difflib.unified_diff(
                block.text.splitlines(keepends=True), current.splitlines(keepends=True), f"planned {block.path}", f"current {block.path}"
            )
        )
        return {**found, "diff": diff[:DIFF_LIMIT_CHARS]}
    # An unapplied replacement is best shown against its anchor; a diverged one against its planned text.
    expected = block.old if state == "unapplied" else block.text
    return {**found, "diff": _closest_diff(expected, current, block.path)}


def _states(found: Sequence[dict[str, Any]]) -> set[str]:
    return {item["state"] for item in found}


def _assess_blocks(
    root: Path, blueprint: blueprint_runtime.Blueprint, view: blueprint_runtime.RepositoryView,
) -> dict[int, dict[str, Any]]:
    """Use safe virtual replay to explain pending dependencies, never to prove progress."""
    keys: dict[str, str] = {}
    actual: dict[str, str | None] = {}
    for step in blueprint.steps:
        for block in step.blocks:
            try:
                if view.entry_path(block.path).is_symlink():
                    raise ValueError("declared file became a symlink")
                key = view.path_key(block.path)
            except (OSError, ValueError):
                key = view.declared_path_key(block.path)
                actual[key] = blueprint_runtime.UNREADABLE
            keys[block.path] = key
            if key not in actual:
                actual[key] = _file_text(root, block.path)
    projected = actual.copy()
    pending: dict[str, set[int]] = {key: set() for key in actual}
    diverged: set[str] = set()
    found: dict[int, dict[str, Any]] = {}
    for step in blueprint.steps:
        for phase in ("frozen", "exact"):
            blocks = [block for block in step.blocks if block.kind == phase]
            # Every block in a phase is assessed before any of that phase is projected.
            for block in blocks:
                key = keys[block.path]
                state, reason = blueprint_runtime.block_state(actual[key], block)
                prerequisites: list[int] = []
                if state == "diverged" and key not in diverged and pending[key]:
                    virtual_state, _ = blueprint_runtime.block_state(projected[key], block)
                    if virtual_state == "unapplied":
                        state = "unapplied"
                        prerequisites = sorted(pending[key])
                        reason = "pending earlier declared text from instructions " + ", ".join(map(str, prerequisites))
                if state == "diverged":
                    diverged.add(key)
                mismatch = _block_mismatch(actual[key], block, state, reason, prerequisites)
                if mismatch is not None:
                    found[block.line] = mismatch
            for block in blocks:
                key = keys[block.path]
                if key in diverged or block.line not in found:
                    continue
                current = projected[key]
                state, _ = blueprint_runtime.block_state(current, block)
                if state != "unapplied":
                    continue
                if block.old is None:
                    applied = block.text
                else:
                    assert current is not None
                    offsets = blueprint_runtime.line_start_offsets(current, block.old)
                    assert len(offsets) == 1
                    applied = current[:offsets[0]] + block.text + current[offsets[0] + len(block.old):]
                if blueprint_runtime.block_state(applied, block)[0] == "exact":
                    projected[key] = applied
                    pending[key].add(step.number)
    return found


def _mismatches(assessment: dict[int, dict[str, Any]], blocks: Sequence[blueprint_runtime.TextBlock]) -> list[dict[str, Any]]:
    return [assessment[block.line] for block in blocks if block.line in assessment]


def _deletion_mismatches(
    view: blueprint_runtime.RepositoryView, steps: Sequence[blueprint_runtime.ImplementationStep]
) -> list[dict[str, Any]]:
    """A planned deletion is realized only when its path is absent (directory-entry semantics)."""
    found: list[dict[str, Any]] = []
    for step in steps:
        for location in step.locations:
            if location.state == "deleted" and os.path.lexists(view.entry_path(location.path)):
                found.append({"path": location.path, "kind": "deleted", "line": location.line, "state": "unapplied",
                              "reason": "the planned deletion is not carried out; the path still exists", "diff": ""})
    return found


def _carried_out_deletions(view: blueprint_runtime.RepositoryView, blueprint: blueprint_runtime.Blueprint) -> set[str]:
    """Declared keys of planned deletions already carried out; a present path is never covered."""
    return {view.declared_path_key(location.path) for step in blueprint.steps for location in step.locations
            if location.state == "deleted" and not os.path.lexists(view.entry_path(location.path))}


def _mismatch_evidence(found: Sequence[dict[str, Any]]) -> list[str]:
    return [f"{item['path']} (Blueprint line {item['line']}, {item['state']}): {item['reason']}\n{item['diff']}" for item in found]


def _outcome(summary: dict[str, Any]) -> str:
    """The single reading of a Run: passed, failed, or unavailable (could not launch)."""
    if summary["launch_error"]:
        return "unavailable"
    return "passed" if summary["passed"] else "failed"


def _step_diff(root: Path, step: blueprint_runtime.ImplementationStep) -> str:
    paths = sorted({location.path for location in step.locations})
    parts = [_git(root, "diff", "--no-ext-diff", "--", *paths).stdout]
    dirty = _git_dirty_entries(root)
    for relative in (path for path in paths if dirty.get(path) == "??"):
        parts.append(f"untracked {relative}:\n{_worktree_text(root, relative) or ''}")
    return "".join(parts)[:DIFF_LIMIT_CHARS]


def _authority_blueprint(
    text: str, root: Path, request_bytes: bytes, view: blueprint_runtime.RepositoryView | None = None
) -> blueprint_runtime.Blueprint:
    """Check seal authority and sources that no authored target may legitimately change."""
    proof_matches = list(blueprint_runtime.PROOF_RE.finditer(text))
    validation_matches = list(blueprint_runtime.VALIDATION_RE.finditer(text))
    if len(proof_matches) != 1 or len(validation_matches) != 1:
        raise ConstructError(
            "blueprint.receipt_missing",
            "selected Blueprint lost its exact seal receipt",
            owner="blueprint",
            category="stale_evidence",
        )
    try:
        proof = json.loads(proof_matches[0].group("json"))
    except json.JSONDecodeError as exc:
        raise ConstructError(
            "blueprint.proof_malformed",
            "selected Blueprint proof receipt is not valid JSON",
            owner="blueprint",
            category="stale_evidence",
        ) from exc
    try:
        current_plan = blueprint_runtime.plan_sha256(text)
    except ValueError as exc:
        raise ConstructError(
            "blueprint.invalid",
            f"sealed Blueprint planning body is invalid: {exc}",
            owner="blueprint",
        ) from exc
    proof_sha256 = _sha256(_canonical_json(proof).encode("utf-8"))
    if validation_matches[0].group("plan") != current_plan or validation_matches[0].group("proof") != proof_sha256:
        raise ConstructError(
            "blueprint.receipt_stale",
            "selected Blueprint plan or proof digest changed after sealing",
            owner="blueprint",
            category="stale_evidence",
        )
    binding = proof.get("binding")
    repository = view or blueprint_runtime.RepositoryView(root)
    repository_id, _head = repository.repository_identity()
    if not isinstance(binding, dict) or binding.get("repository_id") != repository_id:
        raise ConstructError(
            "blueprint.invalid",
            "sealed Blueprint is bound to a different repository",
            owner="blueprint",
        )
    if binding.get("request_sha256") != _sha256(request_bytes):
        raise ConstructError(
            "request.changed",
            "sealed sibling request.md changed after sealing",
            owner="blueprint",
            category="stale_evidence",
        )
    blueprint, diagnostics = blueprint_runtime.parse_blueprint(blueprint_runtime.canonical_body(text))
    if diagnostics or blueprint is None:
        raise ConstructError(
            "blueprint.invalid",
            "invalid Blueprint body: " + "; ".join(str(item) for item in diagnostics),
            owner="blueprint",
        )
    target_keys = {repository.declared_path_key(location.path) for location in blueprint.locations}
    stale = []
    for entry in proof["sources"]:
        data = _regular_bytes(repository, entry["path"])
        if data is None or (repository.declared_path_key(entry["path"]) not in target_keys
                            and _sha256(data) != entry["sha256"]):
            stale.append(entry["path"])
    if stale:
        raise ConstructError(
            "blueprint.invalid", "sealed source-only evidence changed: " + ", ".join(stale),
            owner="blueprint", category="stale_evidence", details={"paths": stale}, evidence=stale,
        )
    return blueprint


def _load(repo_root: Path, blueprint_path: Path) -> tuple[Path, Path, str, bytes, blueprint_runtime.RepositoryView]:
    root = repo_root.resolve()
    try:
        view = blueprint_runtime.RepositoryView(root)
        view.repository_identity()
    except (OSError, ValueError) as exc:
        raise ConstructError("workspace.git_failed", str(exc), category="unsafe_state") from exc
    if not view.inside_worktree:
        raise ConstructError(
            "workspace.git_required",
            "Construct executes only inside a Git worktree; seal the Blueprint in the target repository and run Construct there",
            category="unsafe_state",
        )
    try:
        path = blueprint_runtime.canonical_blueprint_path(root, blueprint_path.resolve(), require_existing=True)
    except (OSError, ValueError) as exc:
        raise ConstructError(
            "blueprint.location_invalid",
            "Construct requires the exact .first-four-hours/blueprints/<task>/blueprint.md path",
            owner="blueprint",
            evidence=(str(exc),),
        ) from exc
    try:
        request = blueprint_runtime.canonical_request_path(
            root, path.parent / blueprint_runtime.REQUEST_FILENAME, require_existing=True
        )
    except (OSError, ValueError) as exc:
        raise ConstructError(
            "request.location_invalid",
            "Construct requires the canonical request.md sibling of the selected Blueprint",
            owner="blueprint",
            evidence=(str(exc),),
        ) from exc
    try:
        text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
        request_bytes = request.read_bytes()
    except (OSError, UnicodeDecodeError) as exc:
        raise ConstructError(
            "blueprint.invalid",
            f"selected Blueprint cannot be read: {exc}",
            owner="blueprint",
        ) from exc
    retired = blueprint_runtime.sealed_contract_diagnostic(text)
    if retired is not None:
        raise ConstructError("contract.unsupported", retired.message, owner="blueprint")
    return root, path, text, request_bytes, view


def _run_guarded(
    root: Path, step: blueprint_runtime.VerificationStep, results: list[dict[str, Any]], phase: str
) -> dict[str, Any]:
    """Execute one authored command under the timeout and mutation guard; append its full result."""
    index_before = _git_index_sha256(root)
    content_before = _worktree_fingerprint(root)
    _receipt, summary = _execute_exact_step(step, root)
    results.append(_result_entry(summary))
    partial = {"verification": {"phase": phase, "results": results, "notices": _notices(results)}}
    if summary["timed_out"]:
        raise ConstructError(
            "verification.timeout_cleanup_uncertain",
            "authored verification step timed out; descendant cleanup cannot be proven, so execution cannot safely continue",
            category="unsafe_state",
            evidence=[json.dumps(summary["step"], sort_keys=True)],
            result=partial,
        )
    try:
        index_after = _git_index_sha256(root)
        _git_dirty_entries(root)
        content_after = _worktree_fingerprint(root)
    except ConstructError as exc:
        results[-1]["passed"] = False
        exc.result = partial
        raise
    if index_before != index_after or content_before != content_after:
        results[-1]["passed"] = False
        changed_paths = sorted(path for path in content_before.keys() | content_after.keys() if content_before.get(path) != content_after.get(path))
        raise ConstructError(
            "verification.mutated_workspace",
            "authored verification changed the repository, Git index, or worktree content; verification commands must be pure observations",
            category="unsafe_state",
            evidence=[json.dumps(summary["step"], sort_keys=True)],
            result=partial,
            details={"changed_paths": changed_paths, "index_changed": index_before != index_after},
            valid_repairs=(
                "Stop as safety-contradiction and preserve unrelated work, including the changed paths. Outside this run, "
                "the caller establishes a trusted state with explicit authority, then takes this authored command, "
                "changed_paths, and index_changed to a Blueprint amendment; never rerun this sealed plan unchanged.",
            ),
        )
    return summary


_STALE_CODES = {"proof.locations.stale", "location.new.occupied", "proof.sources.stale", "location.target.missing"}


def _regular_bytes(view: blueprint_runtime.RepositoryView, relative: str) -> bytes | None:
    try:
        direct = view.entry_path(relative)
        view.resolve(relative)
        if direct.is_symlink() or not direct.is_file():
            return None
        return direct.read_bytes()
    except (OSError, ValueError):
        return None


def _entry_changed(view: blueprint_runtime.RepositoryView, entry: dict[str, Any]) -> bool:
    """Retain seal-time containment and regular-entry checks when comparing receipts."""
    try:
        direct = view.entry_path(entry["path"])
        view.resolve(entry["path"])
        if entry.get("state") == "new":
            return os.path.lexists(direct)
        data = _regular_bytes(view, entry["path"])
        return data is None or _sha256(data) != entry.get("sha256")
    except (OSError, ValueError):
        return True


def _drifted_paths(root: Path, text: str) -> list[str]:
    """Recompute which sealed Location/Source paths differ from the receipt's recorded state."""
    match = blueprint_runtime.PROOF_RE.search(text)
    try:
        proof = json.loads(match.group("json")) if match else {}
    except json.JSONDecodeError:
        return []
    view = blueprint_runtime.RepositoryView(root)
    drifted: list[str] = []
    for entry in [*proof.get("locations", []), *proof.get("sources", [])]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            continue
        if _entry_changed(view, entry):
            drifted.append(entry["path"])
    return sorted(set(drifted))


def run_verification(
    repo_root: Path, blueprint_path: Path, phase: str, from_line: int | None = None
) -> dict[str, Any]:
    if from_line is not None and phase != "after":
        raise ConstructError(
            "verification.selection_invalid",
            "from_line is accepted only for the after-implementation phase; the baseline always drains every authored entry",
        )
    root, path, text, request_bytes, view = _load(repo_root, blueprint_path)
    if phase == "before":
        blueprint, diagnostics, _view = blueprint_runtime.verify_sealed_blueprint(text, root, request_bytes)
        if diagnostics or blueprint is None:
            message = "invalid sealed Blueprint: " + "; ".join(str(item) for item in diagnostics)
            evidence: list[str] = []
            if any(getattr(item, "code", None) in _STALE_CODES for item in diagnostics):
                drifted = _drifted_paths(root, text)
                evidence = [
                    "drifted planned paths: " + (", ".join(drifted) or "none recomputed"),
                ]
                covered = {view.declared_path_key(block.path) for step in blueprint.steps for block in step.blocks} if blueprint else set()
                covered |= _carried_out_deletions(view, blueprint) if blueprint else set()
                if drifted and all(view.declared_path_key(relative) in covered for relative in drifted):
                    evidence.append("verify before checks the sealed baseline; if you are resuming work this plan already applied, run status instead")
                else:
                    evidence.append("source-only drift requires a fresh plan; changed targets without declared text require caller reconciliation before in-session proof")
                message += "; " + evidence[-1]
            raise ConstructError("blueprint.invalid", message, owner="blueprint", evidence=evidence)
        if blueprint.binding is None or blueprint.receipt is None or blueprint.plan_sha256 is None:
            raise ConstructError(
                "blueprint.invalid",
                "sealed Blueprint lost its binding or receipt identity",
                owner="blueprint",
            )
    else:
        blueprint = _authority_blueprint(text, root, request_bytes, view)
        assessment = _assess_blocks(root, blueprint, view)
        found = _mismatches(assessment, [block for step in blueprint.steps for block in step.blocks]) + _deletion_mismatches(view, blueprint.steps)
        unapplied_lines = {item["line"] for item in found if item["state"] == "unapplied"}
        unapplied = sorted({step.number for step in blueprint.steps
                            if any(line in unapplied_lines for line in [*(block.line for block in step.blocks), *(location.line for location in step.locations)])})
        if found and _states(found) == {"unapplied"}:
            raise ConstructError(
                "verification.instruction_unapplied",
                "declared text of instructions " + ", ".join(str(number) for number in unapplied) + " is not applied yet",
                evidence=_mismatch_evidence(found),
                details={"mismatches": found, "instructions": unapplied},
                valid_repairs=("Apply and prove the named instructions; run status to resume at the first one.",),
                next_command=_cli_command(root, path, [], "status"),
            )
        if any(item["state"] == "diverged" for item in found):
            raise ConstructError(
                "blueprint.exact_mismatch",
                "the final files do not realize the sealed Exact/Frozen text or deletions: " + ", ".join(item["path"] for item in found),
                owner="blueprint",
                evidence=_mismatch_evidence(found),
                details={"mismatches": found, "instructions": unapplied},
            )
    authored_phase = BASELINE_PHASE if phase == "before" else FINAL_PHASE
    steps = [step for step in blueprint.verification if step.phase == authored_phase]
    steps = _selected_steps(steps, from_line)
    results: list[dict[str, Any]] = []
    for step in steps:
        summary = _run_guarded(root, step, results, phase)
        partial = {"verification": {"phase": phase, "results": results, "notices": _notices(results)}}
        outcome = _outcome(summary)
        if outcome == "unavailable":
            raise ConstructError(
                "verification.proof_unavailable",
                f"authored {authored_phase} Run could not launch; its proof is unavailable, not failed",
                category="missing_evidence",
                evidence=[summary["stderr_full"]],
                result=partial,
                valid_repairs=("Report verification as incomplete with this evidence; do not rewrite the Run or substitute an interpreter.",),
            )
        if outcome == "failed":
            evidence = [
                json.dumps(summary["step"], sort_keys=True),
                f"returncode: {summary['returncode']}",
                f"stdout tail: {summary['stdout']['tail']}",
                f"stderr tail: {summary['stderr']['tail']}",
            ]
            details = {
                "step": summary["step"],
                "returncode": summary["returncode"],
                "timed_out": summary["timed_out"],
                "stdout": summary["stdout_full"],
                "stderr": summary["stderr_full"],
            }
            incomplete = summary["step"].get("incomplete")
            if incomplete is not None:
                details["incomplete"] = incomplete
            error = ConstructError(
                "verification.step_failed",
                f"authored {authored_phase} Run failed: " + _canonical_json(summary["step"]),
                evidence=evidence,
                result=partial,
                details=details,
            )
            if authored_phase == FINAL_PHASE:
                error.next_command = _reverify_next_command(root, path, summary["step"]["line"])
                error.valid_repairs = (
                    "Repair the settled local bytes and run the returned reverify command.",
                    "Run reverify from an earlier authored Run line when the repair invalidated earlier evidence.",
                    "Stop with plan-contradiction evidence when the repair requires a new semantic decision.",
                )
            if incomplete is not None:
                details["reverify_command"] = error.next_command
                error.next_command = None
                error.valid_repairs = (
                    "If the output shows the declared incomplete outcome and no failure it does not explain, report "
                    "verification incomplete with this output as evidence: never passed, not a plan contradiction, and "
                    "never rerun unchanged.",
                    "Otherwise the failure is real: repair the settled local bytes and run details.reverify_command, "
                    "or stop with plan-contradiction evidence.",
                )
            raise error
    return {
        "verification": {
            "phase": phase,
            "results": results,
            "notices": _notices(results),
            "workspace": _workspace_observation(root),
        }
    }


def _instruction(blueprint: blueprint_runtime.Blueprint, number: int) -> blueprint_runtime.ImplementationStep:
    if not 1 <= number <= len(blueprint.steps):
        raise ConstructError(
            "verification.selection_invalid",
            f"instruction {number} does not exist; the Blueprint has instructions 1-{len(blueprint.steps)}",
        )
    return blueprint.steps[number - 1]


def _validate_attempt(attempt: int) -> None:
    if not 1 <= attempt <= STEP_ATTEMPT_LIMIT:
        raise ConstructError(
            "step.attempt_invalid",
            f"attempt {attempt} is outside the fixed range 1-{STEP_ATTEMPT_LIMIT}; never restart an exhausted attempt budget",
            valid_repairs=("Stop this Construct run and report the last failing output and diff to the caller.",),
        )


def prove(repo_root: Path, blueprint_path: Path, number: int, check: str, attempt: int) -> dict[str, Any]:
    """Observe one instruction's declared red, or one caller-numbered green attempt."""
    if check not in ("red", "green"):
        raise ConstructError("verification.selection_invalid", f"check must be red or green, got {check!r}")
    _validate_attempt(attempt)
    root, path, text, request_bytes, view = _load(repo_root, blueprint_path)
    blueprint = _authority_blueprint(text, root, request_bytes, view)
    step = _instruction(blueprint, number)
    assessment = _assess_blocks(root, blueprint, view)
    earlier = _mismatches(assessment, [block for item in blueprint.steps[: number - 1] for block in item.blocks]) + _deletion_mismatches(view, blueprint.steps[: number - 1])
    if earlier:
        raise ConstructError(
            "step.earlier_unproven",
            f"text of an instruction before {number} does not match the sealed plan",
            evidence=_mismatch_evidence(earlier),
            details={"mismatches": earlier},
            valid_repairs=(
                "Prove earlier instructions first; run status to find the first unsatisfied one.",
                "If those instructions were already proven in this run and a later edit changed them, stop with plan-contradiction evidence.",
            ),
            next_command=_cli_command(root, path, [], "status"),
        )
    frozen = [block for block in step.blocks if block.kind == "frozen"]
    results: list[dict[str, Any]] = []
    proof: dict[str, Any] = {"instruction": number, "check": check, "notices": []}
    if check == "red":
        if step.red is None or step.proof is None:
            raise ConstructError(
                "step.red_undeclared",
                f"instruction {number} declares no Red regression; existing proof needs no artificial failure",
                valid_repairs=(f"Implement instruction {number} and run its green check.",),
                next_command=_apply_first(
                    root, path, step, _mismatches(assessment, step.blocks), _prove_command(root, path, number, "green", attempt)
                ),
            )
        exact = [block for block in step.blocks if block.kind == "exact"]
        applied = [block.path for block in exact if (observed := assessment.get(block.line)) is None or observed["state"] != "unapplied"]
        applied += [location.path for location in step.locations
                    if location.state == "deleted" and not os.path.lexists(view.entry_path(location.path))]
        if applied:
            raise ConstructError(
                "step.red_after_implementation",
                f"instruction {number} implementation has already started in {', '.join(applied)}; its red observation is unrecoverable",
                valid_repairs=("Do not revert work to replay red; report the unrecoverable red observation as a gap and run the green check.",),
                next_command=_apply_first(
                    root, path, step, _mismatches(assessment, step.blocks), _prove_command(root, path, number, "green", attempt)
                ),
            )
        found = _mismatches(assessment, frozen)
        if found:
            raise ConstructError(
                "step.frozen_mismatch",
                f"instruction {number} Frozen proof is not yet written verbatim",
                evidence=_mismatch_evidence(found),
                details={"mismatches": found},
                valid_repairs=("Run apply with blocks=frozen for this instruction, then rerun the red check.",),
                next_command=_apply_first(
                    root, path, step, found, _prove_command(root, path, number, "red", attempt), red_pending=True
                ),
            )
        summary = _run_guarded(root, step.proof, results, f"instruction {number} red")
        proof["result"] = results[-1]
        proof["notices"] = _notices(results)
        outcome = _outcome(summary)
        if outcome == "passed":
            raise ConstructError(
                "step.red_passed",
                f"instruction {number} Proof run already passes before implementation, so it cannot demonstrate the declared defect: {step.red}",
                owner="blueprint",
                evidence=[json.dumps(summary["step"], sort_keys=True)],
                result={"proof": proof},
            )
        if outcome == "unavailable":
            raise ConstructError(
                "step.red_unobservable",
                f"instruction {number} Proof run could not launch, so no red observation exists",
                evidence=[summary["stderr_full"]],
                result={"proof": proof},
                valid_repairs=("Report the launch failure as incomplete; do not count it as the intended defect.",),
            )
        green = _prove_command(root, path, number, "green", attempt)
        following = _apply_first(root, path, step, _mismatches(assessment, step.blocks), green)
        then = (
            f" Then run the returned apply command, implement the rest, and run prove with instruction={number}, "
            f"check=green, attempt={attempt}."
            if following is not green
            else ""
        )
        proof.update(
            {
                "red": step.red,
                "judge": (
                    "Confirm the output shows the declared Red defect: the regression itself ran and failed because of "
                    "the wrong behavior Red names. If the runner reports it blocked by its environment (such as lock "
                    "contention or an exhausted deadline) with no failed case, it is incomplete: stop without rerunning "
                    "and report that block, never as the red. Any other failure, including an import, collection, or "
                    "tooling failure, or a regression left unexecuted because another case failed first, stops as "
                    "plan-contradiction."
                )
                + then,
                "next_command": following,
            }
        )
        return {"proof": proof}
    if not step.blocks and step.proof is None and not any(location.state == "deleted" for location in step.locations):
        proof.update({"status": "unprovable", **_forward_action(root, path, blueprint, number)})
        return {"proof": proof}
    frozen_found = _mismatches(assessment, frozen)
    changed = [item for item in frozen_found if item["state"] == "diverged"]
    if frozen_found and not changed:
        raise ConstructError(
            "step.frozen_mismatch",
            f"instruction {number} Frozen proof is not applied yet: " + ", ".join(item["path"] for item in frozen_found),
            evidence=_mismatch_evidence(frozen_found),
            details={"mismatches": frozen_found},
            valid_repairs=("Run apply with blocks=frozen for this instruction, then rerun the same green attempt.",),
            next_command=_apply_first(root, path, step, frozen_found, _prove_command(root, path, number, "green", attempt)),
        )
    if changed:
        raise ConstructError(
            "step.frozen_changed",
            f"instruction {number} Frozen proof differs from its sealed bytes; the executor must never edit frozen proof",
            owner="blueprint",
            evidence=_mismatch_evidence(changed),
            details={"mismatches": changed},
        )
    found = _mismatches(assessment, [block for block in step.blocks if block.kind == "exact"]) + _deletion_mismatches(view, [step])
    passed = not found
    if step.proof is not None:
        summary = _run_guarded(root, step.proof, results, f"instruction {number} green")
        proof["result"] = results[-1]
        proof["notices"] = _notices(results)
        outcome = _outcome(summary)
        if outcome == "unavailable":
            raise ConstructError(
                "step.proof_unavailable",
                f"instruction {number} Proof run could not launch; no attempt was used",
                category="missing_evidence",
                evidence=[summary["stderr_full"]],
                result={"proof": proof},
                valid_repairs=("Report the proof as unavailable and incomplete; do not count it as an implementation failure.",),
                next_command=_prove_command(root, path, number, "green", attempt),
            )
        passed = passed and outcome == "passed"
    if passed:
        proof.update({"passed": True, **_forward_action(root, path, blueprint, number)})
        return {"proof": proof}
    evidence = _mismatch_evidence(found) + [
        f"returncode: {item['returncode']}\nstdout:\n{item['stdout']}\nstderr:\n{item['stderr']}" for item in results
    ]
    details = {"attempt": attempt, "limit": STEP_ATTEMPT_LIMIT, "mismatches": found, "diff": _step_diff(root, step)}
    if attempt >= STEP_ATTEMPT_LIMIT:
        raise ConstructError(
            "step.attempts_exhausted",
            f"instruction {number} attempt {attempt} of {STEP_ATTEMPT_LIMIT} failed; no further attempt runs in this Construct run",
            evidence=evidence,
            result={"proof": proof},
            details=details,
            valid_repairs=("Stop this Construct run and report the failing output and diff to the caller.",),
        )
    raise ConstructError(
        "step.attempt_failed",
        f"instruction {number} attempt {attempt} of {STEP_ATTEMPT_LIMIT} failed",
        evidence=evidence,
        result={"proof": proof},
        details=details,
        valid_repairs=(
            "Run apply for this instruction's still-unapplied declared blocks and repair the rest of the "
            f"implementation to match the sealed instruction, then run prove with check=green and attempt={attempt + 1}.",
        ),
        next_command=_apply_first(root, path, step, found, _prove_command(root, path, number, "green", attempt + 1)),
    )


_REFUSED_REPAIRS = (
    "Already-applied blocks are never rewritten. For diverged text you wrote in this run, restore its sealed "
    "replaced text, or delete the new file you created, and rerun apply; otherwise stop as plan-contradiction.",
)


def _apply_refused(message: str, found: Sequence[dict[str, Any]] = ()) -> ConstructError:
    return ConstructError(
        "apply.block_refused",
        message + "; nothing was written",
        evidence=_mismatch_evidence(found),
        details={"mismatches": list(found)},
        valid_repairs=_REFUSED_REPAIRS,
    )


def apply_blocks(repo_root: Path, blueprint_path: Path, number: int, kind: str | None) -> dict[str, Any]:
    """Write one instruction's declared blocks with the seal's faithful-executor semantics, or nothing."""
    root, path, text, request_bytes, view = _load(repo_root, blueprint_path)
    blueprint = _authority_blueprint(text, root, request_bytes, view)
    step = _instruction(blueprint, number)
    phases = ("frozen", "exact") if kind is None else (kind,)
    selected = [block for block in step.blocks if block.kind in phases]
    if not selected:
        raise ConstructError(
            "apply.no_blocks",
            f"instruction {number} declares no {' or '.join(phases)} blocks to apply",
            valid_repairs=("Implement this instruction's specified work directly; apply writes only declared Exact/Frozen text.",),
        )
    kinds = {block.kind for block in step.blocks}
    if kind is None and step.red is not None and "exact" in kinds:
        raise ConstructError(
            "apply.red_split_required",
            f"instruction {number} declares Red, so its red must be observed before its Exact text is applied",
            valid_repairs=(
                f"Apply blocks=frozen when the instruction declares Frozen text, prove red, then apply instruction={number} with blocks=exact.",
            ),
        )
    assessment = _assess_blocks(root, blueprint, view)
    earlier_blocks = [block for item in blueprint.steps[: number - 1] for block in item.blocks]
    earlier = _mismatches(assessment, earlier_blocks) + _deletion_mismatches(view, blueprint.steps[: number - 1])
    if earlier:
        raise ConstructError(
            "step.earlier_unproven",
            f"text of an instruction before {number} does not match the sealed plan",
            evidence=_mismatch_evidence(earlier),
            details={"mismatches": earlier},
            valid_repairs=(
                "Prove earlier instructions first; run status to find the first unsatisfied one.",
                "If those instructions were already proven in this run and a later edit changed them, stop with plan-contradiction evidence.",
            ),
            next_command=_cli_command(root, path, [], "status"),
        )
    if kind == "exact":
        pending = _mismatches(assessment, [block for block in step.blocks if block.kind == "frozen"])
        if pending:
            raise ConstructError(
                "apply.frozen_unrealized",
                f"instruction {number} Frozen proof must be realized before its Exact text",
                evidence=_mismatch_evidence(pending),
                details={"mismatches": pending},
                valid_repairs=(
                    f"Run apply with instruction={number} and blocks=frozen first; diverged Frozen proof is a plan-contradiction.",
                ),
            )
    # Everything below happens in memory until every check passes.
    files: dict[str, dict[str, Any]] = {}
    for block in selected:
        try:
            key = view.path_key(block.path)
            if view.entry_path(block.path).is_symlink():
                raise ValueError("declared file is a symlink")
        except (OSError, ValueError) as exc:
            raise _apply_refused(f"{block.path} cannot be written inside the repository: {exc}") from exc
        if key not in files:
            current = _file_text(root, block.path)
            readable = current is not None and current != blueprint_runtime.UNREADABLE
            raw = view.entry_path(block.path).read_bytes().decode("utf-8") if readable else None
            files[key] = {"path": block.path, "raw": raw, "lf": current, "existed": current is not None, "touched": False}
    applied: list[blueprint_runtime.TextBlock] = []
    skipped: list[blueprint_runtime.TextBlock] = []
    for phase in phases:
        pending_blocks: list[blueprint_runtime.TextBlock] = []
        found: list[dict[str, Any]] = []
        for block in (item for item in selected if item.kind == phase):
            entry = files[view.path_key(block.path)]
            state, reason = blueprint_runtime.block_state(entry["lf"], block)
            if state == "exact":
                skipped.append(block)
            elif state == "unapplied":
                pending_blocks.append(block)
            else:
                mismatch = _block_mismatch(entry["lf"], block, state, reason)
                if mismatch is not None:
                    found.append(mismatch)
        if found:
            raise _apply_refused(f"instruction {number} declared text has diverged", found)
        for block in pending_blocks:
            entry = files[view.path_key(block.path)]
            if block.old is None:
                entry["raw"] = block.text
                expected = block.text
            else:
                offsets = blueprint_runtime.line_start_offsets(entry["lf"], block.old)
                if len(offsets) != 1:
                    raise _apply_refused(
                        f"{block.path} (Blueprint line {block.line}): the replaced text occurs {len(offsets)} times "
                        "at a line boundary where it is applied; it must occur exactly once"
                    )
                line = entry["lf"].count("\n", 0, offsets[0])
                starts = [0] + [index + 1 for index, char in enumerate(entry["raw"]) if char == "\n"]
                end = line + block.old.count("\n")
                eol = "\r\n" if "\r\n" in entry["raw"] else "\n"
                entry["raw"] = entry["raw"][: starts[line]] + block.text.replace("\n", eol) + entry["raw"][starts[end]:]
                expected = entry["lf"][: offsets[0]] + block.text + entry["lf"][offsets[0] + len(block.old):]
            entry["lf"] = entry["raw"].replace("\r\n", "\n")
            if entry["lf"] != expected:
                raise _apply_refused(f"{block.path} (Blueprint line {block.line}): its line endings cannot be preserved")
            entry["touched"] = True
            applied.append(block)
    if not applied:
        raise _apply_refused(f"every selected block of instruction {number} is already applied")
    for block in [*earlier_blocks, *(item for item in step.blocks if item.kind == "frozen" or item in selected)]:
        key = view.path_key(block.path)
        if key in files and blueprint_runtime.block_state(files[key]["lf"], block)[0] != "exact":
            raise _apply_refused(
                f"{block.path} (Blueprint line {block.line}) would no longer be realized after instruction {number} is applied"
            )
    written: list[str] = []
    for entry in files.values():
        if not entry["touched"]:
            continue
        target = view.entry_path(entry["path"])
        data = entry["raw"].encode("utf-8")
        try:
            if entry["existed"]:
                target.write_bytes(data)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "xb") as stream:
                    stream.write(data)
        except OSError as exc:
            raise ConstructError(
                "apply.write_failed",
                f"writing {entry['path']} failed: {exc}",
                category="unsafe_state",
                details={"written": written, "failed": entry["path"]},
                valid_repairs=(
                    "Stop as safety-contradiction: report the written and unwritten files; the caller re-establishes a trusted state.",
                ),
            ) from exc
        written.append(entry["path"])
    if step.red is not None and kind != "exact":
        then = f"run apply with instruction={number} and blocks=exact" if "exact" in kinds else "implement the instruction"
        action = (
            f"Run prove with instruction={number}, check=red, and its caller-held next unused attempt. "
            f"Confirm the declared Red defect, then {then}."
        )
    elif kind == "frozen" and "exact" in kinds:
        action = (
            f"Run apply with instruction={number} and blocks=exact, implement the rest, then run prove with "
            f"instruction={number}, check=green, and its caller-held next unused attempt."
        )
    else:
        action = (
            f"Implement the rest of instruction {number}, then run prove with instruction={number}, check=green, "
            "and its caller-held next unused attempt."
        )
    order = {block.line: index for index, block in enumerate(step.blocks)}

    def _listed(blocks: Sequence[blueprint_runtime.TextBlock]) -> list[dict[str, Any]]:
        return [{"path": block.path, "kind": block.kind, "line": block.line} for block in sorted(blocks, key=lambda item: order[item.line])]

    return {
        "apply": {
            "instruction": number,
            "blocks": kind or "all",
            "applied": _listed(applied),
            "skipped": _listed(skipped),
            "files": written,
            "next_command": None,
            "required_action": action,
        }
    }


def status(
    repo_root: Path, blueprint_path: Path, *, instruction: int | None = None, attempt: int | None = None
) -> dict[str, Any]:
    """Derive realized instructions from the sealed plan and current worktree alone.

    Only read-only green proof is rerun; a red observation is never replayed, so a
    satisfied regression's red is reported as unrecoverable rather than invented.
    Attempt history belongs to the caller; supplied context applies only to the
    first pending or diverged instruction, never to uncertain progress.
    """
    if (instruction is None) != (attempt is None):
        raise ConstructError(
            "verification.selection_invalid", "status requires instruction and attempt together, or neither",
            valid_repairs=("Supply both the instruction and its caller-held next unused attempt, or inspect status without either.",),
        )
    if attempt is not None:
        _validate_attempt(attempt)
    root, path, text, request_bytes, view = _load(repo_root, blueprint_path)
    blueprint = _authority_blueprint(text, root, request_bytes, view)
    if instruction is not None:
        _instruction(blueprint, instruction)
    match = blueprint_runtime.PROOF_RE.search(text)
    assert match is not None
    receipt = json.loads(match.group("json"))
    covered = {view.declared_path_key(block.path) for step in blueprint.steps for block in step.blocks}
    covered |= _carried_out_deletions(view, blueprint)
    unverified = sorted({entry["path"] for entry in receipt["locations"]
                         if view.declared_path_key(entry["path"]) not in covered and _entry_changed(view, entry)})
    if unverified:
        changed_keys = {view.declared_path_key(relative) for relative in unverified}
        affected = [step.number for step in blueprint.steps
                    if any(view.declared_path_key(location.path) in changed_keys for location in step.locations)]
        raise ConstructError(
            "status.progress_unverifiable", "changed targets have no declared text to establish safe resume: " + ", ".join(unverified),
            category="missing_evidence", evidence=unverified,
            details={"paths": unverified, "instructions": affected},
            result={"status": {"instructions": [{"instruction": number, "state": "unverifiable"} for number in affected],
                               "next_command": None, "notices": []}},
            valid_repairs=("Have the caller reconcile these target changes against the sealed instructions and protected work before using in-session prove and after-verification commands.",),
        )
    assessment = _assess_blocks(root, blueprint, view)
    instructions: list[dict[str, Any]] = [
        {"instruction": step.number, "title": step.title, "state": "not_checked"} for step in blueprint.steps
    ]
    results: list[dict[str, Any]] = []
    progress: dict[str, Any] = {"instructions": instructions, "next_command": None, "notices": []}
    for step in blueprint.steps:
        entry = instructions[step.number - 1]
        found = _mismatches(assessment, step.blocks) + _deletion_mismatches(view, [step])
        if any(item["state"] == "diverged" for item in found):
            entry.update({"state": "diverged", "mismatches": found})
            _match_status_context(instruction, step.number, progress)
            diverged_lines = {item["line"] for item in found if item["state"] == "diverged"}
            frozen_changed = any(block.kind == "frozen" and block.line in diverged_lines for block in step.blocks)
            own_edit = None
            if frozen_changed:
                repair = "Frozen proof changed: return the contradiction to Blueprint; never edit frozen proof."
            elif attempt is not None:
                own_edit = _prove_command(root, path, step.number, "green", attempt)
                repair = "If this is your own transcription in this run, run details.own_edit_command with the supplied next unused attempt."
            else:
                repair = f"For your own transcription, rerun status with instruction={step.number} and its caller-held next unused attempt; stop if history is unavailable or exhausted."
            raise ConstructError(
                "status.diverged",
                f"instruction {step.number} declared text differs from both its unapplied and its applied form",
                category="stale_evidence",
                evidence=_mismatch_evidence(found),
                result={"status": progress},
                details={"mismatches": found, "own_edit_command": own_edit},
                valid_repairs=(
                    repair,
                    "Otherwise the plan is stale: return the drift to Blueprint for a fresh sealed plan.",
                ),
            )
        passing = not found
        if passing and step.proof is not None:
            outcome = _outcome(_run_guarded(root, step.proof, results, f"instruction {step.number} status"))
            entry["result"] = results[-1]
            progress["notices"] = _notices(results)
            if outcome == "unavailable":
                entry["state"] = "unavailable"
                raise ConstructError(
                    "status.proof_unavailable",
                    f"instruction {step.number} Proof run could not launch, so progress from it on is unknown",
                    category="missing_evidence",
                    evidence=[results[-1]["stderr"]],
                    result={"status": progress},
                    valid_repairs=("Report the unavailable proof as an incomplete gap; do not treat the instruction as unimplemented.",),
                )
            passing = outcome == "passed"
        # Passing checks prove realization only through declared Exact text or a
        # declared regression that fails before implementation; anything else
        # can pass on untouched code, so progress stays uncertain.
        realized = (any(block.kind == "exact" for block in step.blocks) or step.red is not None
                    or any(location.state == "deleted" for location in step.locations))
        if passing and realized:
            entry["state"] = "satisfied"
            if step.red is not None:
                entry["red"] = "unrecoverable"
            continue
        if passing:
            entry["state"] = "unverifiable"
            raise ConstructError(
                "status.progress_unverifiable",
                f"instruction {step.number} has no Exact text or passing declared regression to establish completion",
                category="missing_evidence",
                evidence=[f"instruction {step.number}: {step.title}"],
                details={"instructions": [step.number], "paths": [location.path for location in step.locations]},
                result={"status": progress},
                valid_repairs=("Have the caller reconcile this instruction against the sealed plan and actual diff before continuing in-session; attempt context cannot establish semantic completion.",),
            )
        entry.update({"state": "pending", "mismatches": found})
        _match_status_context(instruction, step.number, progress)
        if attempt is not None:
            progress["next_command"] = _first_command(root, path, step, attempt, found)
        else:
            progress["required_action"] = (
                f"Resume with status instruction={step.number} and its caller-held next unused attempt; "
                "stop if attempt history is unavailable or exhausted."
            )
        return {"status": progress}
    progress["next_command"] = _after_command(root, path)
    return {"status": progress}


def _match_status_context(instruction: int | None, pending: int, progress: dict[str, Any]) -> None:
    if instruction is not None and instruction != pending:
        raise ConstructError(
            "status.attempt_context_mismatch",
            f"attempt context belongs to instruction {instruction}, but instruction {pending} must be resolved first",
            category="missing_evidence",
            details={"requested_instruction": instruction, "pending_instruction": pending},
            result={"status": progress},
            valid_repairs=(f"Use instruction {pending}'s caller-held next unused attempt; never transfer another instruction's budget.",),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--blueprint", type=Path, required=True)
    parser.add_argument("--phase", choices=("before", "after", "prove", "status", "apply"), required=True)
    parser.add_argument("--from-line", dest="from_line", default=None)
    parser.add_argument("--instruction", default=None)
    parser.add_argument("--check", default=None)
    parser.add_argument("--attempt", default=None)
    parser.add_argument("--blocks", choices=("frozen", "exact"), default=None)
    args = parser.parse_args(argv)
    try:
        if args.phase == "apply":
            if args.instruction is None:
                raise ConstructError("verification.selection_invalid", "apply requires instruction")
            result = apply_blocks(args.repo_root, args.blueprint, _positive_int(args.instruction, "instruction"), args.blocks)
        elif args.phase == "prove":
            if args.instruction is None or args.check is None or args.attempt is None:
                raise ConstructError("verification.selection_invalid", "prove requires instruction, check, and attempt")
            result = prove(
                args.repo_root,
                args.blueprint,
                _positive_int(args.instruction, "instruction"),
                args.check,
                _positive_int(args.attempt, "attempt"),
            )
        elif args.phase == "status":
            result = status(
                args.repo_root, args.blueprint,
                instruction=_positive_int(args.instruction, "instruction") if args.instruction is not None else None,
                attempt=_positive_int(args.attempt, "attempt") if args.attempt is not None else None,
            )
        else:
            from_line = _positive_int(args.from_line) if args.from_line is not None else None
            result = run_verification(args.repo_root, args.blueprint, args.phase, from_line)
    except ConstructError as exc:
        return _emit_error(exc)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        error = ConstructError("runtime.action_invalid", str(exc) or exc.__class__.__name__)
        return _emit_error(error)
    _write_utf8(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

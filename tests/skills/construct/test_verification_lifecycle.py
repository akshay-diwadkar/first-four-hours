"""Specified-step execution and verification lifecycle for the stateless Construct runner."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tools.validation.git_test_support import seed_git

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "workbench" / "construct" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import blueprint_runtime  # noqa: E402
import run_verification as runner  # noqa: E402


def _init_git(repo: Path, tracked: dict[str, str] | None = None) -> None:
    seed_git(repo, tracked or {"seed.txt": "seed\n"})


def _seal(repo: Path, name: str, draft: str) -> Path:
    blueprint = repo / ".first-four-hours" / "blueprints" / name / "blueprint.md"
    blueprint.parent.mkdir(parents=True)
    request = blueprint.with_name("request.md")
    request.write_text("Exercise authored verification.\n", encoding="utf-8")
    blueprint.write_text(draft, encoding="utf-8")
    sealed = blueprint_runtime.seal_blueprint(repo, request, blueprint)
    blueprint.write_text(sealed.text, encoding="utf-8")
    return blueprint


def _repo(tmp_path: Path, tracked: dict[str, str] | None = None) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git(repo, tracked)
    return repo


def _write(repo: Path, relative: str, content: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_phase(capsys: pytest.CaptureFixture[str], repo: Path, blueprint: Path, phase: str) -> tuple[int, dict]:
    code = runner.main(["--repo-root", str(repo), "--blueprint", str(blueprint), "--phase", phase])
    captured = capsys.readouterr()
    return code, json.loads(captured.out)


def _invoke(capsys: pytest.CaptureFixture[str], repo: Path, blueprint: Path, *args: str) -> tuple[int, dict]:
    code = runner.main(["--repo-root", str(repo), "--blueprint", str(blueprint), *args])
    return code, json.loads(capsys.readouterr().out)


def _prove(capsys: pytest.CaptureFixture[str], repo: Path, blueprint: Path, number: int, check: str, attempt: int = 1) -> tuple[int, dict]:
    return _invoke(capsys, repo, blueprint, "--phase", "prove", "--instruction", str(number), "--check", check, "--attempt", str(attempt))


def _apply(capsys: pytest.CaptureFixture[str], repo: Path, blueprint: Path, number: int, blocks: str | None = None) -> tuple[int, dict]:
    selection = ("--blocks", blocks) if blocks is not None else ()
    return _invoke(capsys, repo, blueprint, "--phase", "apply", "--instruction", str(number), *selection)


TEST_HEAD = "import sys\nsys.path.insert(0, 'src')\nfrom names import normalize\n"
FROZEN_OLD = "print('ready')\n"
FROZEN_NEW = "assert normalize(None) == '', repr(normalize(None))\nprint('absent ok')\n"
FROZEN_TEST = TEST_HEAD + FROZEN_NEW
TEST_CHECK = (
    "import subprocess, sys\n"
    "done = subprocess.run([sys.executable, '-B', 'tools/check.py'], capture_output=True, text=True)\n"
    "print(done.stdout, end='')\n"
    "assert 'checking' in done.stderr, done.stderr\n"
)
GREETING_TEXT = 'GREETING = "hello"\nPAYLOAD = """left\vtab\fform\x85nel\u2028line\u2029paragraph\rreturn"""\n'
STEP_PLAN = """<!-- blueprint-contract: 1.1.1 -->
# Blueprint: specified steps

## Goal
Absent names normalize to the empty string, the greeting module exists, and every check invocation is logged.

## Current State
`normalize` returns its input unchanged.
**Source:** `src/names.py`
**Source:** `docs/names.py`

## Implementation

### 1. Normalize absent names
**Location:** `src/names.py::normalize`
**State:** existing
**Location:** `tests/test_names.py`
**State:** existing

**Frozen:** `tests/test_names.py`
```python
""" + FROZEN_OLD + """```
**With:**
```python
""" + FROZEN_NEW + """```

**Exact:** `src/names.py`
```python
    return value
```
**With:**
```python
    return value if value is not None else ''
```

**Proof run:** `python tests/test_names.py`
Red: AssertionError showing None returned for an absent name
Expect: prints absent ok.

### 2. Log every repository check invocation
**Location:** `tools/check.py`
**State:** existing
**Location:** `tests/test_check.py`
**State:** new

Print checking to stderr before emitting the existing records; preserve their fields. Write `tests/test_check.py` as the regression: it runs `tools/check.py` with `-B`, reprints its stdout unchanged, and asserts its stderr contains checking, so a check that never logs fails it.

**Proof run:** `python -B tests/test_check.py`
Red: tools/check.py prints nothing to stderr, so the regression's checking assertion fails
Expect: the final record reports an empty errors list.

### 3. Add the greeting module
**Location:** `src/greeting.txt`
**State:** new
**Location:** `./src/names.py`
**State:** existing

**Exact:** `./src/names.py`
```python
    return value if value is not None else ''
```
**With:**
```python
    return value if value is not None else ''
    # greeting enabled
```

**Exact:** `src/greeting.txt`
```text
""" + GREETING_TEXT + """```

## Verification

### After implementation
Run: `python -B tools/check.py`
Expect: the final record reports an empty errors list.

## Completion Conditions
- Absent names normalize to the empty string.
- The greeting module exists.
- Every repository check invocation prints checking to stderr.
"""
UNAVAILABLE_PLAN = """<!-- blueprint-contract: 1.1.1 -->
# Blueprint: unavailable proof

## Goal
Keep the check green.

## Current State
The check passes.
**Source:** `tools/check.py`
**Source:** `docs/names.py`

## Implementation

### 1. Keep the check green
**Location:** `tools/check.py`
**State:** existing

Preserve the check.

**Proof run:** `missing-tool-505 --check`
Red: the missing tool reports the defect
Expect: prints ok.

## Verification

### After implementation
Run: `python -B tools/deadline.py`
Expect: the final record reports complete true.
Incomplete: the final record reports complete false because the deadline was exhausted.

## Completion Conditions
- The check passes.
"""


def test_specified_step_plan_executes_with_bound_proof(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    check = "import json\nprint(json.dumps({'event': 'plan'}))\nprint(json.dumps({'event': 'validation-budget', 'errors': [], 'slow': True}))\n"
    tracked = {
        "src/names.py": "def normalize(value):\n    return value\n",
        "tests/test_names.py": TEST_HEAD + FROZEN_OLD,
        "tools/check.py": check,
        "docs/names.py": "fixture\n",
        "tools/deadline.py": "import json, sys\nprint(json.dumps({'event': 'validation-budget', 'complete': False, 'reason': 'deadline'}))\nsys.exit(1)\n",
    }
    repo = _repo(tmp_path, tracked=tracked)
    # Construct parses sealed plans with its vendored runtime, so seal rules proven on Blueprint's copy must hold here.
    vendored = (SCRIPTS / "blueprint_runtime.py").read_bytes().replace(b"\r\n", b"\n")
    assert vendored == (ROOT / "skills" / "workbench" / "blueprint" / "scripts" / "blueprint_runtime.py").read_bytes().replace(b"\r\n", b"\n")
    blueprint = _seal(repo, "steps", STEP_PLAN)

    # A missing dependent anchor is an executor omission, not a defective plan.
    code, payload = _run_phase(capsys, repo, blueprint, "after")
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"], diagnostic["details"]["owner"], diagnostic["details"]["instructions"]) == (
        3, "verification.instruction_unapplied", "construct", [1, 3])
    dependent = next(item for item in diagnostic["details"]["mismatches"] if item["path"] == "./src/names.py")
    assert (dependent["state"], dependent["prerequisites"]) == ("unapplied", [1])

    # Unapplied Frozen proof is the executor's next action, not edited proof.
    code, payload = _prove(capsys, repo, blueprint, 1, "green")
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"], diagnostic["details"]["owner"]) == (3, "step.frozen_mismatch", "construct")
    assert diagnostic["next_command"]["argv"][-1] == "apply" and "blocks=frozen" in diagnostic["next_command"]["argv"]

    # Later instructions cannot be proven before earlier text exists; the attempt bound is fixed.
    code, payload = _prove(capsys, repo, blueprint, 2, "green")
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"], diagnostic["details"]["owner"]) == (3, "step.earlier_unproven", "construct")
    assert "status" in diagnostic["next_command"]["argv"]
    code, payload = _invoke(capsys, repo, blueprint, "--phase", "status")
    assert code == 0 and payload["status"]["next_command"] is None
    assert "instruction=1" in payload["status"]["required_action"]
    assert [item["state"] for item in payload["status"]["instructions"]] == ["pending", "not_checked", "not_checked"]
    code, payload = _invoke(capsys, repo, blueprint, "--phase", "status", "--instruction", "2", "--attempt", "2")
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"], diagnostic["next_command"]) == (3, "status.attempt_context_mismatch", None)
    assert diagnostic["details"]["pending_instruction"] == 1
    # Pending declared text resumes through apply, never straight to prove.
    code, payload = _invoke(capsys, repo, blueprint, "--phase", "status", "--instruction", "1", "--attempt", "1")
    resume = payload["status"]["next_command"]["argv"]
    assert code == 0 and resume[-1] == "apply" and "instruction=1" in resume and "blocks=frozen" in resume

    # Construct applies declared text itself. Earlier instructions come first, a Red step with Exact text
    # refuses the unfiltered form, and Exact text waits for its Frozen proof; each refusal writes nothing.
    (repo / "tests/test_names.py").write_bytes((TEST_HEAD + FROZEN_OLD).encode("utf-8"))
    code, payload = _apply(capsys, repo, blueprint, 3)
    assert (code, payload["diagnostics"][0]["code"]) == (3, "step.earlier_unproven")
    assert not (repo / "src/greeting.txt").exists()
    code, payload = _apply(capsys, repo, blueprint, 1)
    assert (code, payload["diagnostics"][0]["code"]) == (3, "apply.red_split_required")
    code, payload = _apply(capsys, repo, blueprint, 1, "exact")
    assert (code, payload["diagnostics"][0]["code"]) == (3, "apply.frozen_unrealized")
    assert (repo / "tests/test_names.py").read_bytes() == (TEST_HEAD + FROZEN_OLD).encode("utf-8")
    # Frozen-only apply keeps an LF file's endings and routes to red, then refuses already-applied text.
    code, payload = _apply(capsys, repo, blueprint, 1, "frozen")
    assert code == 0, payload
    assert [(item["path"], item["kind"]) for item in payload["apply"]["applied"]] == [("tests/test_names.py", "frozen")]
    assert "check=red" in payload["apply"]["required_action"]
    assert (repo / "tests/test_names.py").read_bytes() == FROZEN_TEST.encode("utf-8")
    assert (repo / "src/names.py").read_text(encoding="utf-8") == "def normalize(value):\n    return value\n"
    code, payload = _apply(capsys, repo, blueprint, 1, "frozen")
    assert (code, payload["diagnostics"][0]["code"]) == (3, "apply.block_refused")
    # A regression that already passes while the instruction is unapplied cannot show the defect.
    _write(repo, "src/names.py", "def normalize(value):\n    if value is None:\n        return ''\n    return value\n")
    # This Proof run imports src/names.py; it must not write bytecode even when the caller's environment allows it.
    with monkeypatch.context() as scoped:
        scoped.delenv("PYTHONDONTWRITEBYTECODE", raising=False)
        code, payload = _prove(capsys, repo, blueprint, 1, "red")
    assert (code, payload["diagnostics"][0]["code"], payload["diagnostics"][0]["details"]["owner"]) == (3, "step.red_passed", "blueprint")
    _write(repo, "src/names.py", "def normalize(value):\n    return value\n")

    # Declared regression: written verbatim, then observed red with full output.
    code, payload = _prove(capsys, repo, blueprint, 1, "red")
    assert code == 0
    assert payload["proof"]["result"]["passed"] is False
    assert "AssertionError: None" in payload["proof"]["result"]["stderr"]
    # The red result routes to applying the Exact text before green, keeping the caller's attempt.
    after_red = payload["proof"]["next_command"]["argv"]
    assert after_red[-1] == "apply" and "instruction=1" in after_red and "blocks=exact" in after_red
    assert "check=green" in payload["proof"]["judge"] and "attempt=1" in payload["proof"]["judge"]
    # A non-Red instruction resumes through unfiltered apply; diverged text keeps the prove route for local repair.
    plain = blueprint_runtime.ImplementationStep(number=4, title="plain", line=1, locations=())
    pending = [{"kind": "exact", "state": "unapplied", "line": 9}]
    route = runner._first_command(repo, blueprint, plain, 1, pending)["argv"]
    assert route[-1] == "apply" and "instruction=4" in route and not any(item.startswith("blocks=") for item in route)
    route = runner._first_command(repo, blueprint, plain, 1, [*pending, {"kind": "exact", "state": "diverged", "line": 10}])["argv"]
    assert route[-1] == "prove" and "check=green" in route

    # Editing applied frozen proof is a plan contradiction, never a repair.
    _write(repo, "tests/test_names.py", FROZEN_TEST.replace("== ''", "in ('', None)"))
    code, payload = _prove(capsys, repo, blueprint, 1, "green")
    assert code == 3
    assert payload["diagnostics"][0]["code"] == "step.frozen_changed"
    assert payload["diagnostics"][0]["details"]["owner"] == "blueprint"
    _write(repo, "tests/test_names.py", FROZEN_TEST)

    # A wrong implementation uses attempt 1; status must retain the caller's next attempt.
    _write(repo, "src/names.py", "def normalize(value):\n    return value or None\n")
    code, payload = _prove(capsys, repo, blueprint, 1, "green", 1)
    assert payload["diagnostics"][0]["code"] == "step.attempt_failed"
    assert "attempt=2" in payload["diagnostics"][0]["next_command"]["argv"]
    code, payload = _invoke(capsys, repo, blueprint, "--phase", "status", "--instruction", "1", "--attempt", "2")
    assert "attempt=2" in payload["diagnostics"][0]["details"]["own_edit_command"]["argv"]
    code, payload = _prove(capsys, repo, blueprint, 1, "red", 2)
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"]) == (3, "step.red_after_implementation")
    assert "attempt=2" in diagnostic["next_command"]["argv"]
    code, payload = _run_phase(capsys, repo, blueprint, "after")
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"]) == (3, "blueprint.exact_mismatch")
    assert {item["state"] for item in diagnostic["details"]["mismatches"]} == {"diverged", "unapplied"}

    # A transcription restored to its anchor is pending, without a fresh attempt budget.
    (repo / "src/names.py").write_bytes(b"def normalize(value):\n    return value\r\n")
    code, payload = _invoke(capsys, repo, blueprint, "--phase", "status", "--instruction", "1", "--attempt", "2")
    assert code == 0
    pending_command = payload["status"]["next_command"]["argv"]
    assert "instruction=1" in pending_command and "attempt=2" in pending_command

    # Exact-only apply gives replaced lines the file's CRLF and keeps every other byte, including its LF line;
    # the faithful edit proves green and names the next instruction.
    code, payload = _apply(capsys, repo, blueprint, 1, "exact")
    assert code == 0 and "check=green" in payload["apply"]["required_action"]
    assert (repo / "src/names.py").read_bytes() == b"def normalize(value):\n    return value if value is not None else ''\r\n"
    code, payload = _prove(capsys, repo, blueprint, 1, "green", 2)
    assert code == 0
    forward = payload["proof"]
    assert forward["passed"] is True
    assert forward["next_instruction"] == 2 and forward["next_command"] is None
    assert "instruction=2" in forward["required_action"] and "check=green" in forward["required_action"]
    assert "caller-held next unused attempt" in forward["required_action"]
    assert "check=red" in forward["required_action"] and "Write any test instruction 2 specifies in prose" in forward["required_action"]
    # The sealed baseline no longer holds; intake names the drift and the resume path, never auto-routes.
    code, payload = _run_phase(capsys, repo, blueprint, "before")
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"], diagnostic["next_command"]) == (3, "blueprint.invalid", None)
    evidence = "\n".join(diagnostic["supporting_evidence"])
    assert "src/names.py" in evidence and "run status instead" in evidence

    # Resume reaches the pending prose regression, without skipping to the exact instruction.
    code, payload = _invoke(capsys, repo, blueprint, "--phase", "status")
    assert code == 0, payload
    progress = payload["status"]
    assert [item["state"] for item in progress["instructions"]] == ["satisfied", "pending", "not_checked"]
    assert progress["instructions"][0]["red"] == "unrecoverable"
    assert progress["next_command"] is None and "instruction=2" in progress["required_action"]
    assert (repo / "tools/check.py").read_text(encoding="utf-8") == check

    # A prose-specified test that implements no stated case passes red: the executor repairs its own test.
    _write(repo, "tests/test_check.py", "print('ok')\n")
    code, payload = _prove(capsys, repo, blueprint, 2, "red")
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"], diagnostic["details"]["owner"]) == (3, "step.red_passed", "construct")
    assert "instruction=2" in diagnostic["next_command"]["argv"] and "check=red" in diagnostic["next_command"]["argv"]
    _write(repo, "tests/test_check.py", TEST_CHECK)
    code, payload = _prove(capsys, repo, blueprint, 2, "red")
    assert code == 0 and payload["proof"]["result"]["passed"] is False
    assert "AssertionError" in payload["proof"]["result"]["stderr"]

    # Implemented logging advances in-session even though status cannot recover its progress.
    logged_check = "import sys\nprint('checking', file=sys.stderr)\n" + check
    _write(repo, "tools/check.py", logged_check)
    completed = subprocess.run(
        [sys.executable, str(SCRIPTS / "cli.py"), "--repo-root", str(repo), "--input", f"blueprint_file={blueprint}",
         "--input", "instruction=2", "--input", "check=green", "--input", "attempt=1", "--format", "json", "prove"],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    forward = json.loads(completed.stdout)["result"]["proof"]
    assert forward["passed"] is True and forward["next_instruction"] == 3 and forward["next_command"] is None
    assert "instruction=3" in forward["required_action"] and "check=green" in forward["required_action"]
    assert "attempt=1" not in forward["required_action"]
    assert forward["notices"][0]["slow"] is True
    assert "Confirm instruction 2 realizes its sealed behavior" in forward["required_action"]
    code, payload = _invoke(capsys, repo, blueprint, "--phase", "status", "--instruction", "3", "--attempt", "1")
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"], diagnostic["next_command"]) == (3, "status.progress_unverifiable", None)
    assert diagnostic["details"]["instructions"] == [2]

    # Final diff proof still names the transcription mismatch.
    _write(repo, "src/greeting.txt", GREETING_TEXT.replace('"hello"', "'hello'", 1))
    code, payload = _prove(capsys, repo, blueprint, 3, "green", 1)
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"]) == (3, "step.attempt_failed")
    assert "attempt=2" in diagnostic["next_command"]["argv"]
    greeting = next(item for item in diagnostic["details"]["mismatches"] if item["path"] == "src/greeting.txt")
    assert "-GREETING = \"hello\"" in greeting["diff"]

    # A diverged block refuses the whole instruction without writes, even its unapplied alias block.
    names_before = (repo / "src/names.py").read_bytes()
    code, payload = _apply(capsys, repo, blueprint, 3)
    assert (code, payload["diagnostics"][0]["code"]) == (3, "apply.block_refused")
    assert (repo / "src/names.py").read_bytes() == names_before
    # The final faithful green returns authored after-verification directly.
    (repo / "src/greeting.txt").unlink()
    code, payload = _apply(capsys, repo, blueprint, 3)
    assert code == 0, payload
    assert payload["apply"]["files"] == ["./src/names.py", "src/greeting.txt"]
    assert (repo / "src/names.py").read_bytes() == b"def normalize(value):\n    return value if value is not None else ''\r\n    # greeting enabled\r\n"
    assert (repo / "src/greeting.txt").read_bytes() == GREETING_TEXT.encode("utf-8")
    code, payload = _prove(capsys, repo, blueprint, 3, "green", 2)
    assert code == 0 and payload["proof"]["passed"] is True and payload["proof"]["next_instruction"] is None
    after_command = payload["proof"]["next_command"]
    assert "phase=after" in after_command["argv"] and after_command["argv"][-1] == "verify"
    completed = subprocess.run(after_command["argv"], cwd=after_command["cwd"], capture_output=True,
                               text=True, encoding="utf-8", check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    verification = json.loads(completed.stdout)["result"]["verification"]
    assert verification["results"][0]["passed"] is True
    assert verification["results"][0]["stdout_json"][-1]["errors"] == []
    assert verification["notices"][0]["slow"] is True
    assert verification["results"][0]["stderr"].strip() == "checking"
    # An undeclared failure keeps the local-repair reverify route.
    _write(repo, "tools/check.py", "import sys\nsys.exit(1)\n")
    code, payload = _run_phase(capsys, repo, blueprint, "after")
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"]) == (3, "verification.step_failed")
    assert "reverify" in diagnostic["next_command"]["argv"] and "incomplete" not in diagnostic["details"]
    _write(repo, "tools/check.py", logged_check)

    # A changed directory link must not turn source-only evidence into an
    # exempt target alias. Windows junctions require no symlink privilege.
    evidence_file = repo / "docs/names.py"
    evidence_file.unlink()
    (repo / "docs").rmdir()
    if os.name == "nt":
        linked = subprocess.run(["cmd", "/c", "mklink", "/J", str(repo / "docs"), str(repo / "src")],
                                capture_output=True, text=True, check=False)
        assert linked.returncode == 0, linked.stdout + linked.stderr
    else:
        (repo / "docs").symlink_to(repo / "src", target_is_directory=True)
    try:
        code, payload = _invoke(capsys, repo, blueprint, "--phase", "status")
        diagnostic = payload["diagnostics"][0]
        assert (code, diagnostic["code"], diagnostic["details"]["paths"]) == (3, "blueprint.invalid", ["docs/names.py"])
    finally:
        if os.name == "nt":
            (repo / "docs").rmdir()
        else:
            (repo / "docs").unlink()
        _write(repo, "docs/names.py", "fixture\n")

    # Proof that cannot launch is unavailable evidence, never pending work.
    unavailable = _seal(repo, "unavailable", UNAVAILABLE_PLAN)
    # Source freshness wins over unavailable proof; status also rejects the link drift above.
    _write(repo, "docs/names.py", "drifted evidence\n")
    code, payload = _prove(capsys, repo, unavailable, 1, "red")
    assert (code, payload["diagnostics"][0]["code"]) == (3, "blueprint.invalid")
    _write(repo, "docs/names.py", "fixture\n")
    code, payload = _prove(capsys, repo, unavailable, 1, "red")
    assert (code, payload["diagnostics"][0]["code"]) == (3, "step.red_unobservable")
    code, payload = _invoke(capsys, repo, unavailable, "--phase", "status")
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"], diagnostic["category"]) == (3, "status.proof_unavailable", "missing_evidence")
    assert payload["result"]["status"]["instructions"][0]["state"] == "unavailable"
    code, payload = _prove(capsys, repo, unavailable, 1, "green", 2)
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"]) == (3, "step.proof_unavailable")
    assert "attempt=2" in diagnostic["next_command"]["argv"]
    # A declared environment-incomplete gate is reported, never passed or rerun unchanged.
    code, payload = _run_phase(capsys, repo, unavailable, "after")
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"], diagnostic["next_command"]) == (3, "verification.step_failed", None)
    assert diagnostic["details"]["incomplete"].startswith("the final record reports complete false")
    assert "reverify" in diagnostic["details"]["reverify_command"]["argv"]
    assert diagnostic["required_action"].startswith("If the output shows the declared incomplete outcome")

    # Expose the diverged-step route rather than the specified-target drift guard.
    _write(repo, "tools/check.py", check)
    (repo / "tests/test_check.py").unlink()
    # The final unused attempt fails with full output and diff; this run never restarts.
    _write(repo, "src/names.py", "def normalize(value):\n    return value or None\n")
    code, payload = _prove(capsys, repo, blueprint, 1, "green", 3)
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"], diagnostic["next_command"]) == (3, "step.attempts_exhausted", None)
    assert "return value or None" in diagnostic["details"]["diff"]
    assert any("AssertionError: None" in item for item in diagnostic["supporting_evidence"])
    code, payload = _invoke(capsys, repo, blueprint, "--phase", "status")
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"], diagnostic["details"]["own_edit_command"]) == (3, "status.diverged", None)
    code, payload = _invoke(capsys, repo, blueprint, "--phase", "status", "--instruction", "1", "--attempt", "4")
    assert (code, payload["diagnostics"][0]["code"]) == (3, "step.attempt_invalid")


def _porcelain_status(repo: Path, relative: str) -> str:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "--", relative],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout[:2]


RETIRE_STEP = "### 1. Remove the retired file\n**Location:** `retired.txt`\n**State:** deleted\n\nDelete the retired file.\n"
RED_DELETION_PLAN = (
    blueprint_runtime.CONTRACT_MARKER + "\n# Blueprint: red deletion\n\n## Goal\nRemove the obsolete file.\n\n## Current State\nThe obsolete file exists.\n\n"
    "## Implementation\n\n### 1. Replace the obsolete file\n**Location:** `obsolete.txt`\n**State:** deleted\n**Location:** `fresh.txt`\n**State:** new\n\n"
    "**Exact:** `fresh.txt`\n~~~text\nfresh\n~~~\n\n"
    "**Proof run:** `git --version`\nRed: the obsolete file is still present\nExpect: prints the Git version.\n\n"
    "### 2. Add the later file\n**Location:** `later.txt`\n**State:** new\n\n**Exact:** `later.txt`\n~~~text\nlater\n~~~\n\n"
    "## Verification\n\n### After implementation\nRun: `git --version`\nExpect: prints the Git version.\n\n"
    "## Completion Conditions\n- The obsolete file is gone.\n"
)


def _overwrite_draft() -> str:
    return """<!-- blueprint-contract: 1.1.1 -->
# Blueprint: ignored overwrite proof

## Goal
Reject an ignored-only overwrite while Git-visible content remains unchanged.

## Current State
The seed file exists.
**Source:** `seed.txt:1`

## Implementation

""" + RETIRE_STEP + """
### 2. Create the marker
**Location:** `marker.txt`
**State:** new

Create the marker file.

## Verification

### After implementation
Run: `python tests/test_overwrite.py`
Expect: exit 0.

## Completion Conditions
- The marker exists.
"""


def test_verification_rejects_ignored_only_overwrite(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    overwrite = (
        "from pathlib import Path\n"
        "Path('scratch/existing.txt').write_text('changed', encoding='utf-8')\n"
    )
    repo = _repo(tmp_path, tracked={"seed.txt": "seed\n", ".gitignore": "scratch/\n", "retired.txt": "retired\n", "obsolete.txt": "obsolete\n"})
    _write(repo, "seed.txt", "seed modified\n")
    # Bind the pre-existing dirty evidence, rather than introducing source drift.
    blueprint = _seal(repo, "ignored-overwrite", _overwrite_draft())
    # The sealed receipt binds the planned deletion's current bytes under its own state.
    proof_match = blueprint_runtime.PROOF_RE.search(blueprint.read_text(encoding="utf-8"))
    assert proof_match is not None
    receipt = json.loads(proof_match.group("json"))
    assert [(entry["state"], "sha256" in entry) for entry in receipt["locations"] if entry["path"] == "retired.txt"] == [("deleted", True)]
    # A planned-deletion target edited instead of deleted is drift that stops resume, never pending work.
    retired_bytes = (repo / "retired.txt").read_bytes()
    (repo / "retired.txt").write_bytes(retired_bytes + b"edited\n")
    code, payload = _run_phase(capsys, repo, blueprint, "status")
    assert code == 3, payload
    assert (payload["diagnostics"][0]["code"], payload["diagnostics"][0]["details"]["paths"]) == ("status.progress_unverifiable", ["retired.txt"])
    code, payload = _run_phase(capsys, repo, blueprint, "before")
    evidence = "\n".join(payload["diagnostics"][0]["supporting_evidence"])
    assert code == 3 and "retired.txt" in evidence and "run status instead" not in evidence
    (repo / "retired.txt").write_bytes(retired_bytes)
    # An undeleted planned deletion keeps its instruction pending.
    code, payload = _run_phase(capsys, repo, blueprint, "status")
    assert code == 0 and [item["state"] for item in payload["status"]["instructions"]] == ["pending", "not_checked"]
    _write(repo, "tests/test_overwrite.py", overwrite)
    # It also stops final verification before any authored Run executes, and fails green.
    code, payload = _run_phase(capsys, repo, blueprint, "after")
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"]) == (3, "verification.instruction_unapplied")
    assert diagnostic["details"]["instructions"] == [1]
    assert [item["path"] for item in diagnostic["details"]["mismatches"]] == ["retired.txt"]
    code, payload = _prove(capsys, repo, blueprint, 1, "green", 1)
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"]) == (3, "step.attempt_failed")
    assert [item["path"] for item in diagnostic["details"]["mismatches"]] == ["retired.txt"]
    # Once carried out, the deletion is resumable drift, realized progress, and passing green.
    (repo / "retired.txt").unlink()
    code, payload = _run_phase(capsys, repo, blueprint, "before")
    diagnostic = payload["diagnostics"][0]
    evidence = "\n".join(diagnostic["supporting_evidence"])
    assert (code, diagnostic["code"]) == (3, "blueprint.invalid")
    assert "retired.txt" in evidence and "run status instead" in evidence
    code, payload = _run_phase(capsys, repo, blueprint, "status")
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"], diagnostic["next_command"]) == (3, "status.progress_unverifiable", None)
    assert [item["state"] for item in payload["result"]["status"]["instructions"]] == ["satisfied", "unverifiable"]
    code, payload = _prove(capsys, repo, blueprint, 1, "green", 2)
    assert code == 0 and payload["proof"]["passed"] is True
    assert payload["proof"]["next_instruction"] == 2 and payload["proof"]["next_command"] is None
    _write(repo, "marker.txt", "marker\n")
    code, payload = _prove(capsys, repo, blueprint, 2, "green", 1)
    assert code == 0 and payload["proof"]["status"] == "unprovable"
    assert payload["proof"]["next_instruction"] is None
    assert "phase=after" in payload["proof"]["next_command"]["argv"]
    assert "Confirm instruction 2 realizes its sealed behavior" in payload["proof"]["required_action"]
    _write(repo, "scratch/existing.txt", "initial")
    assert _porcelain_status(repo, "seed.txt") == " M"
    assert _porcelain_status(repo, "scratch") == ""
    sentinel_before = (repo / "seed.txt").read_bytes()
    git_before = subprocess.run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=repo, capture_output=True, check=True).stdout
    code, payload = _run_phase(capsys, repo, blueprint, "after")
    assert code == 3
    assert payload["diagnostics"][0]["code"] == "verification.mutated_workspace"
    assert _porcelain_status(repo, "seed.txt") == " M"
    assert _porcelain_status(repo, "scratch") == ""
    assert (repo / "seed.txt").read_bytes() == sentinel_before
    assert (repo / "scratch/existing.txt").read_text(encoding="utf-8") == "changed"
    assert subprocess.run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=repo, capture_output=True, check=True).stdout == git_before
    assert payload["diagnostics"][0]["details"]["changed_paths"] == ["scratch/existing.txt"]
    # The stop names its authored command and routes recovery to a Blueprint amendment, never an unchanged rerun.
    assert payload["diagnostics"][0]["category"] == "unsafe_state"
    assert any("tests/test_overwrite.py" in item for item in payload["diagnostics"][0]["supporting_evidence"])
    assert "Blueprint amendment" in payload["diagnostics"][0]["required_action"]
    assert "preserve unrelated work" in payload["diagnostics"][0]["required_action"]
    assert payload["result"]["verification"]["results"][0]["passed"] is False
    # A carried-out deletion is started implementation: resume routes to apply, never to a red prove must refuse,
    # and prove red reports an unrecoverable gap, never a plan defect.
    red_plan = _seal(repo, "red-deletion", RED_DELETION_PLAN)
    obsolete_bytes = (repo / "obsolete.txt").read_bytes()
    (repo / "obsolete.txt").unlink()
    code, payload = _invoke(capsys, repo, red_plan, "--phase", "status", "--instruction", "1", "--attempt", "1")
    assert code == 0, payload
    resume = payload["status"]["next_command"]["argv"]
    assert resume[-1] == "apply" and "blocks=exact" in resume
    code, payload = _prove(capsys, repo, red_plan, 1, "red")
    assert (code, payload["diagnostics"][0]["code"]) == (3, "step.red_after_implementation")
    # A later instruction waits for every earlier planned deletion, not only earlier declared text.
    (repo / "obsolete.txt").write_bytes(obsolete_bytes)
    code, payload = _apply(capsys, repo, red_plan, 1, "exact")
    assert code == 0, payload
    code, payload = _apply(capsys, repo, red_plan, 2)
    assert (code, payload["diagnostics"][0]["code"]) == (3, "step.earlier_unproven")
    assert [item["path"] for item in payload["diagnostics"][0]["details"]["mismatches"]] == ["obsolete.txt"]
    assert not (repo / "later.txt").exists()
    code, payload = _prove(capsys, repo, red_plan, 2, "green")
    assert (code, payload["diagnostics"][0]["code"]) == (3, "step.earlier_unproven")

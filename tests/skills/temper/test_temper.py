from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tools.validation.git_test_support import seed_git
from tools.validation.python_test_support import run_python

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "skills" / "workbench" / "temper" / "scripts"
CLI = SCRIPTS / "cli.py"
BLUEPRINT_SCRIPTS = REPO_ROOT / "skills" / "workbench" / "blueprint" / "scripts"

CALC = "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"
CHECK_ADD = "from calc import add\nassert add(2, 3) == 5\n"


def _load(name: str) -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(f"temper_test_{name}", SCRIPTS / f"{name}.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS))


def _cli(repo: Path, command: str, **inputs: str) -> tuple[int, dict[str, Any]]:
    argv = [sys.executable, str(CLI), "--repo-root", str(repo)]
    for name, value in inputs.items():
        argv += ["--input", f"{name}={value}"]
    done = run_python([*argv, "--format", "json", command], capture_output=True, text=True, check=False)
    return done.returncode, json.loads(done.stdout)


def _messages(envelope: dict[str, Any]) -> str:
    return "\n".join(str(item.get("message", "")) for item in envelope.get("diagnostics", []))


def _bundle() -> dict[str, Any]:
    def selection(*argv: str) -> dict[str, Any]:
        return {"argv": list(argv), "timeout_seconds": 60}

    suite = "import glob, runpy\nfor p in sorted(glob.glob('check_*.py')): runpy.run_path(p)"
    return {
        "schema_version": "1.0.0",
        "title": "Calc audit",
        "summary": "Two checks overlap and one is vacuous; multiplication is unprotected.",
        "budget": {"seconds": None, "kind": "local", "basis": "none set"},
        "copy_git": False,
        "copy_exclude": [],
        "selections": {
            "suite": selection(sys.executable, "-c", suite),
            "add": selection(sys.executable, "check_add.py"),
            "dup": selection(sys.executable, "check_dup.py"),
            "smoke": selection(sys.executable, "check_smoke.py"),
            "probe": selection(sys.executable, "-c", "from calc import mul; assert mul(2, 3) == 6"),
        },
        "mutants": {
            "M1": {"path": "calc.py", "old": "return a + b", "new": "return a - b", "behavior": "addition subtracts"},
            "M2": {"path": "calc.py", "old": "return a * b", "new": "return a + b", "behavior": "multiplication adds"},
        },
        "findings": [
            {
                "kind": "redundant",
                "title": "check_dup repeats check_add",
                "tests": ["check_dup.py"],
                "rationale": "Same assertion as check_add.py; coverage contexts show identical lines.",
                "mutants": ["M1"],
                "candidate": "dup",
                "guard": "add",
            },
            {
                "kind": "vacuous",
                "title": "check_smoke asserts nothing",
                "tests": ["check_smoke.py"],
                "rationale": "It only imports calc; the selection runs the copy's relative modules.",
                "mutants": ["M1"],
                "candidate": "smoke",
                "guard": "add",
            },
            {
                "kind": "gap",
                "title": "multiplication is untested",
                "tests": [],
                "rationale": "No check calls mul; the probe shows the fault is observable.",
                "mutants": ["M2"],
                "guard": "suite",
                "witness": "probe",
            },
        ],
    }


def test_audit_replays_claims_and_verify_guards_kills(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    seed_git(
        repo,
        {"calc.py": CALC, "check_add.py": CHECK_ADD, "check_dup.py": CHECK_ADD, "check_smoke.py": "import calc\n"},
    )
    bundle = _bundle()
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    calc = repo / "calc.py"
    before = (calc.read_bytes(), calc.stat().st_mtime_ns)
    os.chmod(calc, stat.S_IREAD)
    try:
        # 1. A false claim and an escaping mutant path are refused before anything is written.
        false_claim = copy.deepcopy(bundle)
        false_claim["findings"][0]["kind"] = "vacuous"
        (tmp_path / "false.json").write_text(json.dumps(false_claim), encoding="utf-8")
        code, envelope = _cli(repo, "run", bundle=str(tmp_path / "false.json"), slug="cart")
        assert (code, envelope["status"]) == (3, "blocked")
        first = envelope["diagnostics"][0]["message"]
        assert "finding 1" in first and "M1" in first and "dup" in first
        escaping = copy.deepcopy(bundle)
        escaping["mutants"]["M1"]["path"] = "../outside.py"
        (tmp_path / "escape.json").write_text(json.dumps(escaping), encoding="utf-8")
        code, envelope = _cli(repo, "run", bundle=str(tmp_path / "escape.json"), slug="cart")
        assert code == 3 and "../outside.py" in _messages(envelope)
        assert not (repo / ".first-four-hours" / "test-audits").exists()

        # 2. The true bundle seals without touching the repository.
        code, envelope = _cli(repo, "run", bundle=str(bundle_path), slug="cart")
        assert code == 0, envelope
        audit = Path(envelope["result"]["path"])
        text = audit.read_text(encoding="utf-8")
        assert re.search(r"<!-- test-audit: 1\.0\.0; sha256: [0-9a-f]{64} -->$", text.rstrip("\n").splitlines()[-1])
        assert (calc.read_bytes(), calc.stat().st_mtime_ns) == before
        status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True)
        assert status.stdout == ""

        # 3. Blueprint accepts the rendered audit through its typed intake.
        probe = (
            "import sys; sys.path.insert(0, sys.argv[2]); import blueprint_runtime as r; "
            "d = r.detect_request_source(open(sys.argv[1], 'rb').read(), '3,1'); print(d['kind'], d['item'])"
        )
        seen = subprocess.run(
            [sys.executable, "-c", probe, str(audit), str(BLUEPRINT_SCRIPTS)], capture_output=True, text=True, check=True
        )
        assert seen.stdout.strip() == "test-audit 1,3"

        # 4. A correct removal still verifies.
        (repo / "check_dup.py").unlink()
        code, envelope = _cli(repo, "verify", audit=str(audit), item="1")
        assert code == 0, envelope
        assert envelope["result"]["kills"] == [{"finding": 1, "mutant": "M1", "guard": "add", "observed": "killed"}]

        # 5. Losing the guard's assertion loses the kill.
        (repo / "check_add.py").write_text("from calc import add\nadd(2, 3)\n", encoding="utf-8")
        code, envelope = _cli(repo, "verify", audit=str(audit), item="1")
        assert code == 3
        message = _messages(envelope)
        assert "M1" in message and "add" in message

        # 6. A slower suite fails on time alone.
        baseline = _load("audit_contract").read_sealed(text)["results"]["baseline"]["suite"]
        slow = f"import time\nfrom calc import add\nassert add(2, 3) == 5\ntime.sleep({1.1 * baseline + 1.5})\n"
        (repo / "check_add.py").write_text(slow, encoding="utf-8")
        code, envelope = _cli(repo, "verify", audit=str(audit), item="1")
        assert code == 3 and "audited baseline" in _messages(envelope)

        # 7. A tampered audit fails its receipt.
        tampered = tmp_path / "tampered.md"
        tampered.write_text(text.replace("overlap", "overlay", 1), encoding="utf-8", newline="\n")
        code, envelope = _cli(repo, "verify", audit=str(tampered), item="1")
        assert code == 3 and "receipt" in _messages(envelope)
    finally:
        os.chmod(calc, stat.S_IWRITE | stat.S_IREAD)

    # 8. The copy refuses to land where it could reach the repository.
    replay = _load("replay")
    inside = repo / "inside-tmp"
    inside.mkdir()
    old_tempdir = tempfile.tempdir
    tempfile.tempdir = str(inside)
    try:
        with pytest.raises(replay.ReplayError):
            with replay.RepositoryCopy(repo, False, []):
                pass
    finally:
        tempfile.tempdir = old_tempdir
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    with pytest.raises(replay.ReplayError):
        with replay.RepositoryCopy(worktree, True, []):
            pass

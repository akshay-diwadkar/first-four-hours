from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from tools.validation.git_test_support import seed_git


ROOT = Path(__file__).resolve().parents[2]
VALIDATION_DIR = ROOT / "tools" / "validation"
sys.path.insert(0, str(VALIDATION_DIR))

import test_ownership as ownership  # noqa: E402
import validation_budget as budget  # noqa: E402


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _synthetic(root: Path) -> dict:
    _write(root, "tests/repository/test_owner.py", "def test_owner():\n    assert True\n")
    _write(root, "tests/repository/test_routine_validation.py", "def test_live_repository_metadata(): pass\ndef test_routine_policy_is_the_normal_gate(): pass\n")
    skills = {name: f"{name}-runtime-contract" for name in ownership.SKILL_NAMES}
    skills["reason"] = "reason-guidance-contract"
    owners: dict[str, dict[str, Any]] = {
        name: {"test_targets": ["tests/repository/test_owner.py"]} for name in skills.values()
    }
    owners["skill-contracts"] = {"skill_scoped": True}
    owners.update({"repository-contract": {"test_targets": ["tests/repository/test_owner.py"]}, "validator-contract": {"test_targets": [target.partition("::")[0] for target in ownership.UNIVERSAL_TARGETS]}})
    return {
        "schema_version": "1.0.0",
        "description": "synthetic test manifest",
        "limits": {ownership.MAX_GATED_ITEMS_KEY: 48},
        "owners": owners,
        "skill_owners": skills,
        "universal_targets": list(ownership.UNIVERSAL_TARGETS),
        "rules": [
            {"id": "skills", "path_prefixes": ["skills"], "owner": "skill-contracts"},
            {"id": "tests", "path_prefixes": ["tests"], "owner": "repository-contract"},
            {"id": "tools", "path_prefixes": ["tools/validation"], "owner": "validator-contract"},
            {"id": "deferred", "path_prefixes": ["deferred"], "resolution": "deferred"},
        ],
        "scope_prefixes": ["skills", "tests", "tools"],
        "inventory": {"restricted_roots": [], "forbidden_prefixes": [], "forbidden_file_prefixes": [], "forbidden_paths": [], "policy_drift_patterns": []},
    }


def _capped_env(cap: str | None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in {"SKILLS_MAX_GATED_ITEMS", "SKILLS_CASE_REPORT"}}
    env.update({
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTEST_ADDOPTS": "", "PYTEST_PLUGINS": "",
        # absolute, and the run happens in tmp_path: using the repository as the
        # rootdir makes pytest walk the whole tree and costs over two minutes
        "PYTHONPATH": str(VALIDATION_DIR),
    })
    if cap is not None:
        env["SKILLS_MAX_GATED_ITEMS"] = cap
    return env


def test_all_is_finite_union_and_deduplicates_profiles(tmp_path: Path) -> None:
    manifest = _synthetic(tmp_path)
    owner_source = (
        "import pytest\nfrom pathlib import Path\n"
        "@pytest.mark.parametrize('value', ['alpha', 'alpha]'], ids=['alpha', 'alpha]'])\n"
        "def test_owner(value):\n"
        "    with Path('executions').open('a') as f: f.write(value + '\\n')\n"
    )
    _write(tmp_path, "tests/repository/test_owner.py", owner_source)
    # All whole-module references use an alias, so inventory coverage must
    # identify the actual module before dependency/explicit-node deduplication.
    for owner in manifest["owners"].values():
        if "test_targets" in owner:
            owner["test_targets"] = [target.replace("tests/repository/test_owner.py", "./tests/repository/./test_owner.py")
                                     for target in owner["test_targets"]]
    assert ownership.validate_manifest(manifest, root=tmp_path, paths=["tests/repository/test_owner.py"]) == []
    # Distinct parameter IDs must survive file alias normalization; an exact
    # duplicate alias must still execute only once in a focused selection.
    focused = ownership.select_changed_paths(manifest=manifest, root=tmp_path, tests=[
        "tests/repository/test_owner.py::test_owner[alpha]",
        "./tests/repository/./test_owner.py::test_owner[alpha]]",
        r".\tests\repository\test_owner.py::test_owner[alpha]",
    ])
    assert focused["valid"] and focused["scope"] == "focused"
    focused_targets = focused["selected"]["checks"][0]["targets"]
    assert focused_targets == sorted({
        "tests/repository/test_owner.py::test_owner[alpha]",
        "tests/repository/test_owner.py::test_owner[alpha]]",
        *ownership.UNIVERSAL_TARGETS,
    })
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "--rootdir", str(tmp_path), "-p", "no:cacheprovider", *focused_targets], cwd=tmp_path, capture_output=True, text=True, env=_capped_env(None))
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "executions").read_text().splitlines() == ["alpha", "alpha]"]
    (tmp_path / "executions").unlink()
    plan = ownership.select_changed_paths(
        manifest=manifest, root=tmp_path, all_profiles=True,
        tests=["./tests/repository/./test_owner.py::test_owner", r".\tests\repository\test_owner.py::test_owner"],
    )
    assert plan["valid"] and plan["scope"] == "required"
    targets = plan["selected"]["checks"][0]["targets"]
    assert targets == sorted({"tests/repository/test_owner.py", *(target.partition("::")[0] for target in ownership.UNIVERSAL_TARGETS)})
    assert not any(Path(t.split("::")[0]).is_dir() for t in plan["selected"]["checks"][0]["targets"])
    # Added cases in an already-profiled module must run automatically, once,
    # even when several dependency profiles select that module.
    _write(tmp_path, "tests/repository/test_owner.py", owner_source + "def test_added():\n    with Path('executions').open('a') as f: f.write('added\\n')\n")
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "--rootdir", str(tmp_path), "-p", "no:cacheprovider", *targets], cwd=tmp_path, capture_output=True, text=True, env=_capped_env(None))
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "executions").read_text().splitlines() == ["alpha", "alpha]", "added"]


def test_inventory_rejects_unprofiled_pytest_module(tmp_path: Path) -> None:
    manifest = _synthetic(tmp_path)
    _write(tmp_path, "tests/repository/unprofiled_test.py", "def test_hidden(): pass\n")
    assert any("whole-module owner target" in error for error in ownership.validate_manifest(manifest, root=tmp_path, paths=["tests/repository/unprofiled_test.py"]))
    # Pinning just the old node cannot hide future tests in the same module.
    manifest["owners"]["repository-contract"]["test_targets"] = ["tests/repository/unprofiled_test.py::test_hidden"]
    assert any("whole-module owner target" in error for error in ownership.validate_manifest(manifest, root=tmp_path, paths=["tests/repository/unprofiled_test.py"]))


def _supervised_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], targets: list[str]) -> tuple[int, dict, str]:
    worker = tmp_path / "worker.py"
    # The worker copies its stderr into a log that a still-running test can watch.
    worker.write_text(
        f"import sys,json\nfrom pathlib import Path\nsys.path.insert(0,{str(VALIDATION_DIR)!r})\n"
        "import test_ownership as ownership\n"
        "class Tee:\n"
        "    def __init__(self, stream):\n        self.stream, self.buffer = stream, self\n"
        "    def write(self, data):\n"
        "        raw = data.encode() if isinstance(data, str) else bytes(data)\n"
        f"        with open({str(tmp_path / 'worker-stderr.log')!r}, 'ab') as copy:\n            copy.write(raw)\n"
        "        self.stream.buffer.write(raw)\n        self.stream.buffer.flush()\n        return len(data)\n"
        "    def flush(self):\n        self.stream.flush()\n"
        "    def fileno(self):\n        return self.stream.fileno()\n"
        "def main():\n"
        " sys.stderr=Tee(sys.stderr)\n"
        f" result=ownership.run_pytest(Path({str(tmp_path)!r}),{targets!r},48)\n"
        " print(json.dumps(result))\n return result['executed'][0]['returncode']\n", encoding="utf-8",
    )
    monkeypatch.delenv("SKILLS_VALIDATION_ACTIVE", raising=False)
    exit_code = budget.bounded_main(worker, [], tmp_path, started_at=time.monotonic(), expect_cases=True)
    captured = capfd.readouterr()
    records = [json.loads(line) for line in captured.out.splitlines() if line.startswith("{")]
    return exit_code, next(record for record in records if record.get("event") == "validation-budget"), captured.err


def test_failed_verification_is_never_reported_passing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]) -> None:
    _write(tmp_path, "tests/repository/test_owner.py", "def test_wrong():\n    assert False, 'real failing verification'\ndef test_unexecuted():\n    raise AssertionError('must not run after failure')\n")
    # A second file runs in its own concurrent shard, so its cases complete despite the failure.
    # Its last case waits for the failed shard's traceback and for its own shard's unfinished
    # progress-shaped line on the worker's stderr, so output held back until a shard exits or a
    # line ends, and lost if the deadline stops the worker, fails it.
    _write(tmp_path, "tests/repository/test_other.py",
           "import sys\nimport time\nfrom pathlib import Path\n"
           "def test_progress(capsys):\n"
           "    with capsys.disabled():\n"
           "        sys.stdout.write('sxsxsxsx')\n"
           "        sys.stdout.flush()\n"
           "def test_passes():\n"
           f"    log = Path({str(tmp_path / 'worker-stderr.log')!r})\n"
           "    deadline = time.monotonic() + 15\n"
           "    markers = (b'real failing verification', b'sxsxsxsx')\n"
           "    while not all(marker in (log.read_bytes() if log.exists() else b'') for marker in markers):\n"
           "        assert time.monotonic() < deadline, 'shard output did not reach the worker while its shard ran'\n"
           "        time.sleep(0.05)\n")
    targets = ["tests/repository/test_owner.py", "tests/repository/test_other.py"]
    exit_code, result, _ = _supervised_run(tmp_path, monkeypatch, capfd, targets)
    assert exit_code == 1
    assert result["status"] == "failed" and result["valid"] is False
    assert result["failed_cases"] == ["tests/repository/test_owner.py::test_wrong"]
    assert result["complete"] is False
    assert result["unverified_cases"] == ["tests/repository/test_owner.py::test_unexecuted"]


def test_case_limits_are_refused_before_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]) -> None:
    # Split across two files, the skill's four cases are still counted together, and a
    # thirteenth shared case is refused too, all before any body runs.
    body = "import pytest\nfrom pathlib import Path\n@pytest.mark.parametrize('value', range({count}))\ndef test_case(value):\n    Path('body-ran').write_text(str(value))\n"
    for name in ("test_limit_a.py", "test_limit_b.py"):
        _write(tmp_path, f"tests/skills/ticket/{name}", body.format(count=2))
    _write(tmp_path, "tests/repository/test_limit.py", body.format(count=13))
    targets = ["tests/skills/ticket/test_limit_a.py", "tests/skills/ticket/test_limit_b.py", "tests/repository/test_limit.py"]
    exit_code, result, errors = _supervised_run(tmp_path, monkeypatch, capfd, targets)
    assert exit_code != 0 and result["valid"] is False
    assert not (tmp_path / "body-ran").exists()
    assert "ticket: 4 collected cases exceeds the hard 3-case limit" in errors
    assert "shared: 13 collected cases exceeds the hard 12-case limit" in errors


def test_shard_output_limit_survives_blocked_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]) -> None:
    # A shard floods its output while a child it started keeps a directory under the
    # runner's temp root in use; on Windows that blocks the root's removal, which must
    # not replace the output-limit verdict. The root lives under tmp_path so it never
    # accumulates in the system temp directory.
    worker_temp = tmp_path / "worker-temp"
    worker_temp.mkdir()
    for name in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.setenv(name, str(worker_temp))
    _write(tmp_path, "tests/repository/test_flood.py",
           "import subprocess\nimport sys\nimport time\n"
           "def test_flood(tmp_path, capsys):\n"
           "    subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], cwd=tmp_path,\n"
           "                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
           "    with capsys.disabled():\n"
           "        sys.stdout.write('x' * (17 * 1024 * 1024))\n"
           "        sys.stdout.flush()\n"
           "    time.sleep(30)\n")
    _write(tmp_path, "tests/repository/test_quiet.py", "def test_quiet():\n    pass\n")
    exit_code, result, errors = _supervised_run(tmp_path, monkeypatch, capfd, ["tests/repository/test_flood.py", "tests/repository/test_quiet.py"])
    assert exit_code == 3
    assert result["status"] == "output_limit" and result["reason"] == "child_output_limit"
    assert result["valid"] is False
    assert "pytest output exceeded" in errors
    if os.name == "nt":
        # Windows cannot remove a directory a live process uses, so the root must remain: the cleanup really failed.
        assert any(worker_temp.iterdir())


def test_misplaced_skill_integration_is_refused_before_any_body(tmp_path: Path) -> None:
    ticket = "tests/skills/ticket/test_ticket.py"
    integration = "tests/integration/test_ticket_installed_both_adapters.py"
    _write(tmp_path, ticket,
           "import pytest\nfrom pathlib import Path\n"
           "@pytest.mark.parametrize('value', range(3))\n"
           "def test_ticket(value):\n    Path('body-ran').write_text(str(value))\n")
    _write(tmp_path, integration,
           "from pathlib import Path\ndef test_ticket_publication():\n    Path('body-ran').write_text('integration')\n")
    manifest = _synthetic(tmp_path)
    manifest["owners"]["repository-contract"]["test_targets"].extend([ticket, integration])
    errors = ownership.validate_manifest(manifest, root=tmp_path, paths=[ticket, integration])
    assert any(integration in error and "unrecognized test location" in error for error in errors)
    result = subprocess.run([
        sys.executable, "-m", "pytest", "-q", "--rootdir", str(tmp_path), "-p", "no:cacheprovider",
        "-p", "size_cap", ticket, integration,
    ], cwd=tmp_path, capture_output=True, text=True, env=_capped_env("48"))
    assert result.returncode != 0, result.stdout + result.stderr
    assert "unrecognized test location" in result.stderr
    assert not (tmp_path / "body-ran").exists()


def test_cli_refuses_redirecting_gate_and_names_its_checkout(tmp_path: Path) -> None:
    # An isolated copy runs the real public CLI without nesting the active gate.
    checkout = tmp_path / "checkout"
    scripts = checkout / "tools" / "validation"
    scripts.mkdir(parents=True)
    shutil.copy2(VALIDATION_DIR / "test_ownership.py", scripts)
    shutil.copy2(VALIDATION_DIR / "validation_budget.py", scripts)
    shutil.copy2(VALIDATION_DIR / "size_cap.py", scripts)
    manifest = scripts / "test-ownership.json"
    manifest.write_text(json.dumps(_synthetic(checkout)), encoding="utf-8")
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    alternate = unrelated / "alternate.json"
    alternate.write_text(json.dumps(_synthetic(unrelated)), encoding="utf-8")
    _write(unrelated, "tests/repository/test_owner.py", "from pathlib import Path\ndef test_owner():\n    Path('wrong-tree-ran').write_text('ran')\n")
    seed_git(unrelated)
    environment = {key: value for key, value in os.environ.items() if key not in {"SKILLS_VALIDATION_ACTIVE", "SKILLS_CASE_REPORT"}}
    result = subprocess.run([
        sys.executable, str(scripts / "test_ownership.py"), "--repo-root", str(unrelated), "--manifest", str(alternate), "run", "--all",
    ], cwd=unrelated, capture_output=True, text=True, env=environment)
    records = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    verdict = next(record for record in records if record.get("event") == "validation-budget")
    assert result.returncode == 2
    assert verdict["valid"] is False and verdict["status"] == "failed"
    assert verdict["repo_root"] == str(checkout.resolve())
    assert verdict["manifest"] == str(manifest.resolve())
    assert not (unrelated / "wrong-tree-ran").exists()
    # A tracked path deleted but not yet committed has no content to own or
    # forbid, so the checkout's own full selection must not fail on it.
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["inventory"]["forbidden_prefixes"] = ["retired"]
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    _write(checkout, "retired/notes.md", "retired\n")
    seed_git(checkout)
    (checkout / "retired" / "notes.md").unlink()
    selected = subprocess.run([
        sys.executable, str(scripts / "test_ownership.py"), "select", "--all", "--format", "json",
    ], cwd=checkout, capture_output=True, text=True, env=environment)
    assert selected.returncode == 0, selected.stdout + selected.stderr
    assert "forbidden inventory path" not in selected.stdout + selected.stderr

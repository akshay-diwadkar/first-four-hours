from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills" / "workbench" / "atlas"
CLI = SKILL / "scripts" / "cli.py"
FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(SKILL / "scripts"))

from freshness_state import assess, baseline  # noqa: E402


def _write(root: Path, files: dict[str, str]) -> Path:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _simple(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "valid-simple", root)
    return root


def _obligations(root: Path) -> dict[str, Any]:
    report, diagnostics = assess(root)
    assert not [item for item in diagnostics if not str(item["code"]).startswith("map.freshness_state_")]
    return report["obligations"]


def _cycle(root: Path) -> str:
    report, diagnostics = assess(root)
    return str(report["cycle_fingerprint"])


def test_first_baseline_cycle_and_delta(tmp_path: Path) -> None:
    from tools.validation.python_test_support import run_python

    root = _write(
        _simple(tmp_path),
        {
            "docs/one.txt": "one\n",
            "docs/two.txt": "two\n",
            ".map/auth/LANDMARK.md": "# Authentication\n\nRoute through request identity and authorization concepts.\n\n- [Request authentication](request-auth.md) — read when a request establishes a principal.\n- [Sessions](session.md) — read for session lifecycle.\n",
            ".map/auth/session.md": "# Sessions\n\n- [Authentication middleware](../../src/auth.py) — sessions reuse the request principal.\n",
        },
    )
    state_path = root / ".map/.state/freshness.json"

    def cli(*args: str) -> Any:
        command = [sys.executable, str(CLI), "--repo-root", str(root), "--format", "json", *args]
        return run_python(command, capture_output=True, text=True)

    def refused(diagnostics: list[dict[str, Any]], code: str) -> dict[str, Any]:
        assert not state_path.exists()
        codes = [str(item["code"]) for item in diagnostics]
        assert len(codes) == len(set(codes)), codes
        return next(item for item in diagnostics if item["code"] == code)

    setup = cli("setup-guidance")
    assert setup.returncode == 0, setup.stdout + setup.stderr
    checked = cli("run")
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert not state_path.exists()
    first = cli("check")
    assert first.returncode == 0, first.stdout + first.stderr
    report = json.loads(first.stdout)["result"]
    assert (report["state_status"], report["status"]) == ("missing", "review-required")
    satellites = report["obligations"]["satellites"]
    assert satellites == [".map/auth/request-auth.md", ".map/auth/session.md"]
    assert report["obligations"]["unmapped_paths"] == ["AGENTS.md", "CLAUDE.md", "docs/one.txt", "docs/two.txt"]
    cycle = report["cycle_fingerprint"]

    _, diagnostics = baseline(root, cycle, satellites, ["docs/one.txt\r", "docs/two.txt"])
    assert repr("docs/one.txt\r") in refused(diagnostics, "map.freshness_input_malformed")["message"]
    assert not [item for item in diagnostics if "review_stale" in str(item["code"])]
    _, diagnostics = baseline(root, cycle, satellites, ["docs/one.txt"], acknowledge_all_unmapped=True)
    refused(diagnostics, "map.freshness_acknowledgement_ambiguous")
    _, diagnostics = baseline(root, "0" * 64, satellites, [], acknowledge_all_unmapped=True)
    refused(diagnostics, "map.freshness_cycle_stale")
    (root / "docs/three.txt").write_text("three\n", encoding="utf-8")
    _, diagnostics = baseline(root, cycle, satellites, [], acknowledge_all_unmapped=True)
    refused(diagnostics, "map.freshness_cycle_stale")
    (root / "docs/three.txt").unlink()
    _, diagnostics = baseline(root, cycle, [], [], acknowledge_all_unmapped=True)
    refused(diagnostics, "map.freshness_satellite_review_missing")
    _, diagnostics = baseline(root, cycle, [], [f"elsewhere/{index}.txt" for index in range(12)])
    assert "12 supplied" in refused(diagnostics, "map.freshness_unmapped_review_stale")["message"]
    refused(diagnostics, "map.freshness_unmapped_review_missing")
    refused(diagnostics, "map.freshness_satellite_review_missing")

    accepted = cli(
        "--input", f"cycle_fingerprint={cycle}",
        "--input", f"reviewed_satellite={satellites[0]}",
        "--input", f"reviewed_satellite={satellites[1]}",
        "--input", "acknowledge_unmapped=all",
        "baseline",
    )
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["receipts"]["acknowledged_unmapped"] == ["AGENTS.md", "CLAUDE.md", "docs/one.txt", "docs/two.txt"]
    current = cli("check")
    assert current.returncode == 0, current.stdout + current.stderr
    assert json.loads(current.stdout)["result"]["status"] == "current"
    (root / "docs/one.txt").write_text("changed\n", encoding="utf-8")
    assert _obligations(root)["unmapped_paths"] == ["docs/one.txt"]
    (root / "src/auth.py").write_text("changed\n", encoding="utf-8")
    obligations = _obligations(root)
    assert (obligations["satellites"], obligations["unmapped_paths"]) == (satellites, ["docs/one.txt"])
    result, diagnostics = baseline(root, _cycle(root), satellites, [], acknowledge_all_unmapped=True)
    assert diagnostics == []
    assert {item["outcome"] for item in result["receipts"]["reviewed_satellites"].values()} == {"unchanged"}

    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["receipts"]["obligations"]["satellites"] = [{"path": satellites[0]}]
    state_path.write_text(json.dumps(state), encoding="utf-8")
    recovered, diagnostics = assess(root)
    assert diagnostics == []
    assert (recovered["state_status"], recovered["status"]) == ("incompatible", "review-required")
    assert recovered["obligations"]["satellites"] == satellites
    assert recovered["obligations"]["unmapped_paths"] == ["AGENTS.md", "CLAUDE.md", "docs/one.txt", "docs/two.txt"]

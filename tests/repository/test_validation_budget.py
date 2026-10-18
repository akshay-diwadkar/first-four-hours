from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "validation"))

import validation_budget as budget  # noqa: E402


def _worker(tmp_path: Path, source: str) -> Path:
    worker = tmp_path / "worker.py"
    worker.write_text(source, encoding="utf-8")
    return worker


def _run(worker: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> tuple[int, list[str]]:
    monkeypatch.delenv("SKILLS_VALIDATION_ACTIVE", raising=False)
    result = budget.bounded_main(worker, [], worker.parent, started_at=time.monotonic())
    output = capsys.readouterr().out.splitlines()
    return result, output


def _final(output: list[str]) -> dict:
    records = [json.loads(line) for line in output if line.startswith("{")]
    return next(record for record in reversed(records) if record.get("event") == "validation-budget")


def test_deadline_kills_worker_and_grandchild(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    heartbeat = tmp_path / "heartbeat.txt"
    child = "import pathlib,time\np=pathlib.Path(r'%s')\ni=0\nwhile True:\n p.write_text(str(i)); i+=1; time.sleep(.05)\n" % heartbeat
    report_locator = tmp_path / "report-path.txt"
    source = (
        "import os,pathlib,subprocess,sys,time\ndef main():\n"
        " report=pathlib.Path(os.environ['SKILLS_CASE_REPORT'])\n"
        f" pathlib.Path({str(report_locator)!r}).write_text(str(report))\n"
        " report.write_text('{\"event\":\"case\",')\n"
        f" subprocess.Popen([sys.executable,'-c',{child!r}])\n"
        " time.sleep(30)\n return 0\n"
    )
    worker = _worker(tmp_path, source)
    # Expire the work deadline once the grandchild is alive instead of waiting a fixed wall-clock interval.
    monkeypatch.setattr(budget, "_deadline_due", lambda now, deadline: heartbeat.exists() or now >= deadline)
    monkeypatch.setattr(budget, "WORK_BUDGET_SECONDS", 5.0)
    exit_code, output = _run(worker, capsys, monkeypatch)
    assert exit_code == 3
    record = _final(output)
    assert record["status"] == "incomplete" and record["complete"] is False
    assert record["reason"] == "case_accounting_unconfirmed"
    assert record["valid"] is False
    assert not Path(report_locator.read_text()).exists()
    first = heartbeat.read_text(encoding="utf-8")
    time.sleep(0.15)
    assert heartbeat.read_text(encoding="utf-8") == first

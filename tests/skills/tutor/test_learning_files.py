from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

CLI = Path(__file__).resolve().parents[3] / "skills" / "learning" / "tutor" / "scripts" / "cli.py"


def cli(folder: Path, command: str, **inputs: str) -> tuple[int, Any]:
    argv = [sys.executable, str(CLI), "--repo-root", str(folder)]
    for name, value in inputs.items():
        argv += ["--input", f"{name}={value}"]
    result = subprocess.run(
        [*argv, "--format", "json", command], capture_output=True, text=True, check=False, env={**os.environ}
    )
    return result.returncode, json.loads(result.stdout)


def codes(envelope: dict[str, Any]) -> list[str]:
    return [item["code"] for item in envelope["diagnostics"]]


def tree(folder: Path) -> set[Path]:
    root = folder / ".learning"
    if not root.exists():
        return set()
    found: set[Path] = set()
    pending = [root]
    while pending:
        current = pending.pop()
        for entry in current.iterdir():
            found.add(entry)
            if entry.is_dir() and not entry.is_symlink():
                pending.append(entry)
    return found


def link_directory(link: Path, target: Path) -> None:
    if sys.platform == "win32":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    else:
        os.symlink(target, link, target_is_directory=True)


def test_scaffold_numbers_validates_never_overwrites_and_refuses_links(tmp_path: Path) -> None:
    learner = tmp_path / "learner"
    learner.mkdir()
    lessons = learner / ".learning" / "organic-chemistry" / "lessons"

    code, envelope = cli(learner, "scaffold", kind="lesson", subject="organic-chemistry", topic="sn1-versus-sn2", date="2026-10-31")
    assert code == 0, envelope
    first = lessons / "01-sn1-versus-sn2.html"
    assert envelope["result"]["created"] == [str(first.resolve())], envelope
    text = first.read_text(encoding="utf-8")
    assert '<section id="learning-record">' in text and "<!-- fill:" in text and "2026-10-31" in text
    assert "{{" not in text

    # Numbering counts every numbered entry in lessons/, including runnable code files.
    (lessons / "07-old.html").write_text("old", encoding="utf-8")
    (lessons / "09-starter.py").write_text("print(1)\n", encoding="utf-8")
    code, envelope = cli(learner, "scaffold", kind="lesson", subject="organic-chemistry", topic="e1", date="2026-10-31")
    assert code == 0, envelope
    assert envelope["result"]["created"] == [str((lessons / "10-e1.html").resolve())], envelope

    # Invalid, reserved, or unused inputs are refused before anything is written.
    before = tree(learner)
    for inputs in (
        {"kind": "start-here", "subject": "Organic Chem"},
        {"kind": "lesson", "subject": "organic-chemistry", "topic": "e2", "date": "2026-02-30"},
        {"kind": "lesson", "subject": "organic-chemistry", "topic": "con", "date": "2026-10-31"},
        {"kind": "study-plan", "subject": "organic-chemistry", "topic": "e2"},
    ):
        code, envelope = cli(learner, "scaffold", **inputs)
        assert code == 3, (inputs, envelope)
        assert codes(envelope) == ["learning.input_invalid"], (inputs, envelope)
    assert tree(learner) == before

    # An existing file is never replaced.
    plan = learner / ".learning" / "organic-chemistry" / "study-plan.html"
    code, envelope = cli(learner, "scaffold", kind="study-plan", subject="organic-chemistry")
    assert code == 0 and envelope["result"]["created"] == [str(plan.resolve())], envelope
    plan.write_bytes(b"edited")
    code, envelope = cli(learner, "scaffold", kind="study-plan", subject="organic-chemistry")
    assert code == 0, envelope
    assert envelope["result"]["created"] == [] and envelope["result"]["existing"] == [str(plan.resolve())]
    assert plan.read_bytes() == b"edited"

    # A linked .learning, or a linked subject folder inside a real .learning, is refused without writes.
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    linked.mkdir()
    link_directory(linked / ".learning", outside)
    deep = tmp_path / "deep"
    (deep / ".learning").mkdir(parents=True)
    link_directory(deep / ".learning" / "chemistry", outside)
    for folder in (linked, deep):
        code, envelope = cli(folder, "scaffold", kind="start-here", subject="chemistry")
        assert code == 3, envelope
        assert codes(envelope) == ["learning.unsafe_path"], envelope
        assert list(outside.iterdir()) == []

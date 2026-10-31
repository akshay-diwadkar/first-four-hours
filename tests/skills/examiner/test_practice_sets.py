from __future__ import annotations

import http.server
import json
import os
import re
import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

SKILL = Path(__file__).resolve().parents[3] / "skills" / "learning" / "examiner"
CLI = SKILL / "scripts" / "cli.py"
EXAM = "aqa-gcse-chemistry-8462"
SET_ID = f"chemistry/{EXAM}/2026-10-31-full-mock-01"


def cli(folder: Path, command: str, *inputs: tuple[str, str]) -> tuple[int, Any]:
    argv = [sys.executable, str(CLI), "--repo-root", str(folder)]
    for name, value in inputs:
        argv += ["--input", f"{name}={value}"]
    env = {**os.environ, "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
    result = subprocess.run([*argv, "--format", "json", command], capture_output=True, text=True, check=False, env=env)
    return result.returncode, json.loads(result.stdout)


def scaffold_set(folder: Path, **inputs: str) -> tuple[int, Any]:
    fields = {"kind": "set", "subject": "chemistry", **inputs}
    return cli(folder, "scaffold", *fields.items())


class Handler(http.server.BaseHTTPRequestHandler):
    def _answer(self) -> None:
        status = {"/gone": 404, "/private": 403}.get(self.path, 200)
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_HEAD = _answer
    do_GET = _answer

    def log_message(self, *args: object) -> None:
        pass


def snapshot(root: Path) -> dict[Path, bytes | None]:
    found: dict[Path, bytes | None] = {}
    pending = [root]
    while pending:
        current = pending.pop()
        for entry in current.iterdir():
            if entry.is_dir():
                found[entry] = None
                pending.append(entry)
            else:
                found[entry] = entry.read_bytes()
    return found


def page(*links: str) -> str:
    anchors = "\n".join(f'<p><a href="{link}">link</a></p>' for link in links)
    return f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><title>Key</title></head>\n<body><h2 id="ok">Answers</h2>\n<p><a href="#ok">top of answers</a></p>\n{anchors}\n</body></html>\n'


def test_set_scaffold_and_check_of_saved_files(tmp_path: Path) -> None:
    student = tmp_path / "student"
    student.mkdir()
    exams = student / ".learning" / "chemistry" / "exams" / EXAM

    code, envelope = scaffold_set(student, exam=EXAM, practice_kind="full-mock", date="2026-10-31", marking_scheme="yes")
    assert code == 0, envelope
    mock = exams / "2026-10-31-full-mock-01"
    assert sorted(path.name for path in mock.iterdir()) == ["answer-key.html", "marking-scheme.html", "paper.html", "source-notes.html"]
    paper = (mock / "paper.html").read_bytes()
    runtime = (SKILL / "assets" / "paper-runtime.html").read_bytes()
    assert paper.count(runtime) == 1
    assert "<!-- paper-runtime -->" not in paper.decode("utf-8").splitlines()
    meta = re.search(r'<script type="application/json" id="paper-meta">(.*?)</script>', paper.decode("utf-8"), re.S)
    assert meta is not None and json.loads(meta.group(1))["id"] == SET_ID
    assert all(b"{{" not in path.read_bytes() for path in mock.iterdir())

    # Set numbers count across kinds; a supplied paper gets only Examiner's source notes; an exam is required.
    code, envelope = scaffold_set(student, exam=EXAM, practice_kind="topic-practice", date="2026-10-31")
    assert code == 0, envelope
    topic = exams / "2026-10-31-topic-practice-02"
    assert sorted(path.name for path in topic.iterdir()) == ["answer-key.html", "paper.html", "source-notes.html"]
    code, envelope = scaffold_set(student, exam=EXAM, practice_kind="supplied-paper", date="2026-10-31")
    assert code == 0, envelope
    assert [path.name for path in (exams / "2026-10-31-supplied-paper-03").iterdir()] == ["source-notes.html"]
    code, envelope = scaffold_set(student, practice_kind="full-mock", date="2026-10-31")
    assert code == 3, envelope
    assert [item["code"] for item in envelope["diagnostics"]] == ["learning.input_invalid"]
    assert len(list(exams.iterdir())) == 3

    # Unfilled skeleton markers block.
    relative = f"exams/{EXAM}/2026-10-31-full-mock-01"
    code, envelope = cli(student, "check", ("subject", "chemistry"), ("file", f"{relative}/paper.html"))
    assert code == 3, envelope
    blocking = {item["code"] for item in envelope["diagnostics"] if item["severity"] == "error"}
    assert blocking == {"learning.unfilled"}, envelope

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        gone, private = f"http://127.0.0.1:{port}/gone", f"http://127.0.0.1:{port}/private"
        key = mock / "answer-key.html"
        key.write_text(page("paper.html", "missing.html", "#nope", "paper.html#absent", "/abs.html", gone, private), encoding="utf-8")

        # Broken relative targets and missing anchors block; absolute and external problems only warn; nothing is written.
        before = snapshot(student / ".learning")
        code, envelope = cli(student, "check", ("subject", "chemistry"), ("file", f"{relative}/answer-key.html"))
        assert code == 3, envelope
        errors = sorted(item["code"] for item in envelope["diagnostics"] if item["severity"] == "error")
        warnings = {item["code"] for item in envelope["diagnostics"] if item["severity"] == "warning"}
        assert errors == ["learning.fragment_missing", "learning.fragment_missing", "learning.link_broken"], envelope
        assert warnings == {"learning.link_absolute", "learning.external_dead", "learning.external_unverified"}, envelope
        assert snapshot(student / ".learning") == before

        # Without the broken links the page passes with warnings; skip fetches nothing.
        key.write_text(page("paper.html", "/abs.html", gone, private), encoding="utf-8")
        code, envelope = cli(student, "check", ("subject", "chemistry"), ("file", f"{relative}/answer-key.html"))
        assert code == 0, envelope
        result = envelope["result"]
        assert result["status"] == "checked" and result["external_checked"] is True
        assert sorted(item["code"] for item in result["warnings"]) == [
            "learning.external_dead", "learning.external_unverified", "learning.link_absolute"
        ], result
        code, envelope = cli(
            student, "check", ("subject", "chemistry"), ("file", f"{relative}/answer-key.html"), ("external", "skip")
        )
        assert code == 0, envelope
        assert [item["code"] for item in envelope["result"]["warnings"]] == ["learning.link_absolute"]
        assert envelope["result"]["external_checked"] is False
    finally:
        server.shutdown()
        server.server_close()

    # When no external link can be reached, one offline warning replaces the per-URL warnings.
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    closed = probe.getsockname()[1]
    probe.close()
    key.write_text(page("paper.html", f"http://127.0.0.1:{closed}/a", f"http://127.0.0.1:{closed}/b"), encoding="utf-8")
    code, envelope = cli(student, "check", ("subject", "chemistry"), ("file", f"{relative}/answer-key.html"))
    assert code == 0, envelope
    assert [item["code"] for item in envelope["result"]["warnings"]] == ["learning.external_offline"], envelope

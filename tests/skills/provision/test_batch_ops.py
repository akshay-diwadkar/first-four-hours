from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tools.validation.git_test_support import seed_git

ROOT = Path(__file__).resolve().parents[3]
SERVER = ROOT / "skills" / "workbench" / "provision" / "assets" / "batch-ops" / "batch_ops_server.py"
ENVELOPE = "batch_ops/envelope"


def _text(result) -> str:
    return "\n".join(c.text for c in result.content if getattr(c, "text", None))


def _items(result) -> list[dict]:
    return result.meta[ENVELOPE]["items"]


def test_batch_ops_stdio_session(tmp_path):
    repo = tmp_path / "repo"
    seed_git(repo, {".gitignore": "ignored/\n", "src/a.txt": "needle_token here\n", "notes.txt": "seed\n"})
    notes = repo / "notes.txt"
    notes.write_bytes(b"keep\r\nold line\r\n")
    (repo / "ignored").mkdir(exist_ok=True)
    (repo / "ignored" / "hit.txt").write_text("needle_token\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"keep\n")
    proc = tmp_path / "proc"
    proc.mkdir()
    child_script = f"import time; time.sleep(4); open({str(proc / 'child_alive')!r}, 'w').close()"
    parent_script = (
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', {child_script!r}])\n"
        f"open({str(proc / 'spawned')!r}, 'w').close()\n"
        "time.sleep(4)\n"
        f"open({str(proc / 'parent_alive')!r}, 'w').close()\n"
        "time.sleep(30)\n"
    )
    params = StdioServerParameters(
        command=sys.executable, args=[str(SERVER)], cwd=str(repo), env={"PYTHONDONTWRITEBYTECODE": "1"}
    )

    async def call(session, name, args):
        return await asyncio.wait_for(session.call_tool(name, args), 20)

    async def session_run():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), 20)

                tools = await asyncio.wait_for(session.list_tools(), 20)
                assert sorted(t.name for t in tools.tools) == ["batch_edit", "batch_read", "batch_run"]

                res = await call(session, "batch_read", {
                    "specs": ["notes.txt", {"grep": "needle_token", "paths": ["."]}], "cwd": str(repo)})
                assert not res.isError and res.structuredContent is None
                items = _items(res)
                assert len(items) == 2
                assert not [i for i in items if i["status"] in ("error", "missing")]
                text = _text(res).replace("\\", "/")
                assert "src/a.txt" in text and "ignored/hit.txt" not in text

                start = time.monotonic()
                res = await call(session, "batch_run", {"commands": [
                    {"argv": [sys.executable, "-c", parent_script], "label": "slow", "timeout": 2},
                    {"argv": [sys.executable, "-c", "raise SystemExit(3)"], "label": "bad"}], "cwd": str(repo)})
                assert time.monotonic() - start < 15
                by_label = {i["label"]: i for i in _items(res)}
                assert by_label["slow"]["status"] == "timeout"
                assert by_label["bad"]["status"] == "error" and by_label["bad"]["exit_code"] == 3
                assert (proc / "spawned").exists()
                await asyncio.sleep(max(0.0, start + 6 - time.monotonic()))
                assert not (proc / "parent_alive").exists()
                assert not (proc / "child_alive").exists()

                lf = repo / "lf.txt"
                lf.write_bytes(b"one\n")
                res = await call(session, "batch_edit", {
                    "manifest": "diff --git a/lf.txt b/lf.txt\n--- a/lf.txt\n+++ b/lf.txt\n@@ -1 +1 @@\n-one\n+two\n",
                    "cwd": str(repo)})
                assert not res.isError
                assert lf.read_bytes().replace(b"\r\n", b"\n") == b"two\n"

                sub = str(repo / "src")
                res = await call(session, "batch_edit", {
                    "manifest": "diff --git a/src/new.txt b/src/new.txt\nnew file mode 100644\n--- /dev/null\n+++ b/src/new.txt\n@@ -0,0 +1 @@\n+x\ndiff --git a/notes.txt b/copied.txt\nsimilarity index 100%\ncopy from notes.txt\ncopy to copied.txt\n",
                    "cwd": sub})
                assert res.isError
                assert not (repo / "copied.txt").exists()
                assert not (repo / "src" / "new.txt").exists()

                res = await call(session, "batch_edit", {
                    "manifest": "--- /dev/null\n+++ b/src/new.txt\n@@ -0,0 +1 @@\n+x\n--- /dev/null\n+++ /outside2.txt\n@@ -0,0 +1 @@\n+y\n",
                    "cwd": sub})
                assert res.isError
                assert not (repo / "outside2.txt").exists()
                assert not (repo / "src" / "new.txt").exists()

                res = await call(session, "batch_edit", {
                    "manifest": "diff --git a/notes.txt b/copied.txt\nsimilarity index 100%\ncopy from notes.txt\ncopy to copied.txt\n",
                    "verify": {"argv": [sys.executable, "-c", "raise SystemExit(1)"]}, "cwd": str(repo)})
                assert res.isError
                assert [(i["kind"], i["path"]) for i in _items(res) if i["kind"] != "verify"] == [("create", "copied.txt")]
                assert not (repo / "copied.txt").exists()

                edit = {"path": "notes.txt", "search": "old line", "replace": "new line"}
                res = await call(session, "batch_edit", {
                    "edits": [edit], "new_files": {"deep/er/made.txt": "x\n"},
                    "verify": {"argv": [sys.executable, "-c", "raise SystemExit(1)"]}, "cwd": str(repo)})
                assert res.isError
                assert notes.read_bytes() == b"keep\r\nold line\r\n"
                assert not (repo / "deep").exists()

                res = await call(session, "batch_edit", {
                    "new_files": {"deep2/made.txt": "x\n"},
                    "verify": {"argv": [sys.executable, "-c", "import pathlib; pathlib.Path('deep2/keep.txt').write_text('k'); raise SystemExit(1)"]},
                    "cwd": str(repo)})
                assert res.isError
                assert (repo / "deep2" / "keep.txt").exists()
                assert not (repo / "deep2" / "made.txt").exists()
                assert "rollback could not remove directory" in _text(res)

                res = await call(session, "batch_edit", {"edits": [edit], "cwd": str(repo)})
                assert not res.isError
                assert notes.read_bytes() == b"keep\r\nnew line\r\n"

                res = await call(session, "batch_edit", {
                    "edits": [{"path": "../outside.txt", "search": "keep", "replace": "gone"}], "cwd": str(repo)})
                assert res.isError
                assert outside.read_bytes() == b"keep\n"

                res = await call(session, "batch_read", {"mode": "survey", "cwd": str(repo)})
                assert not res.isError

    asyncio.run(asyncio.wait_for(session_run(), 40))

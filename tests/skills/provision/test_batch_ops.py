from __future__ import annotations

import asyncio
import json
import re
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
    fixture = {
        ".gitignore": "ignored/\n",
        "src/a.txt": "needle_token here\n",
        "notes.txt": "seed\n",
        "big.txt": "".join(
            f"block {k}:\n" + "".join(f"    body {k}-{j} filler text to take up room\n" for j in range(1, 21))
            for k in range(1, 31)
        ),
        "doc.md": "# Title\n\nIntro.\n\n## Setup (local)\n\nsetup paragraph\n\n## Next\n\nnext paragraph\n",
    }
    for i in range(1, 31):
        fixture[f"hits/f{i:02d}.txt"] = "".join(f"needle_census {n}\n" for n in range(1, 11))
    seed_git(repo, fixture)
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
                init = await asyncio.wait_for(session.initialize(), 20)
                assert "prefixed names" in (init.instructions or "")

                tools = await asyncio.wait_for(session.list_tools(), 20)
                assert sorted(t.name for t in tools.tools) == ["batch_edit", "batch_read", "batch_run"]
                removed = {
                    "batch_read": ["requests", "tokens", "item_tokens", "time_s", "max_output", "max_files"],
                    "batch_run": ["specs", "tokens", "item_tokens", "time_s", "max_output"],
                    "batch_edit": ["max_files", "tokens"],
                }
                for tool in tools.tools:
                    props = tool.inputSchema["properties"]
                    assert "budget" in props
                    assert not [name for name in removed[tool.name] if name in props]
                    if tool.name == "batch_edit":
                        assert "full_diff" in props
                    if tool.name == "batch_run":
                        assert "slices" in (tool.description or "")
                assert sum(len(json.dumps(t.inputSchema)) + len(t.description or "") for t in tools.tools) <= 5200

                res = await call(session, "batch_read", {
                    "specs": ["notes.txt", {"grep": "needle_token", "paths": ["."]}], "cwd": str(repo)})
                assert not res.isError and res.structuredContent is None
                items = _items(res)
                assert len(items) == 2
                assert not [i for i in items if i["status"] in ("error", "missing")]
                text = _text(res).replace("\\", "/")
                assert "src/a.txt" in text and "ignored/hit.txt" not in text

                res = await call(session, "batch_read", {
                    "specs": ["notes.txt"], "budget": {"tokenz": 5}, "cwd": str(repo)})
                assert res.isError and "tokenz" in _text(res)

                res = await call(session, "batch_read", {"specs": ["notes.txt@target:1-2"], "cwd": str(repo)})
                assert (
                    "1: keep\n2: old line\n\n=== [target: copy verbatim to batch_edit] ===\nkeep\nold line\n"
                    "=== [end target] ==="
                ) in _text(res).replace("\r", "")

                res = await call(session, "batch_read", {"specs": ["big.txt"], "cwd": str(repo)})
                text = _text(res)
                assert "block 30:" in text and "body 1-1 filler" not in text
                assert "next (read tool)" not in text and '"big.txt:1-630"' in text

                res = await call(session, "batch_read", {"specs": ["doc.md@block:## Setup (local"], "cwd": str(repo)})
                text = _text(res)
                assert "## Setup (local)" in text and "setup paragraph" in text and "## Next" not in text
                res = await call(session, "batch_read", {"specs": ["doc.md@outline"], "cwd": str(repo)})
                assert "## Setup (local)" in _text(res) and "## Next" in _text(res)

                res = await call(session, "batch_read", {
                    "specs": ["big.txt:1-630"], "budget": {"tokens": 1000}, "cwd": str(repo)})
                assert not res.isError
                text = _text(res)
                lines = text.replace("\r", "").split("\n")
                assert re.search(r"(?m)^\d+: block 15:$", text)
                assert "    body 15-5 filler" not in text
                next_lines = [ln for ln in lines if ln.startswith("next (read tool): specs=")]
                assert next_lines and "big.txt:" in next_lines[0] and "cwd=" not in next_lines[0]
                assert not [ln for ln in lines if ln.startswith(("cwd:", "workspace:"))]
                assert [ln for ln in lines if ln.startswith("budget:")]
                assert "artifact:" not in text

                res = await call(session, "batch_read", {
                    "specs": ["big.txt@context:body:0"], "budget": {"tokens": 1000}, "cwd": str(repo)})
                assert "artifact:" in _text(res)

                res = await call(session, "batch_read", {"specs": ["git:log::(top)big.txt"], "cwd": str(repo / "hits")})
                assert not res.isError
                assert "(no commits touch" in _text(res)

                grep = {"grep": "needle_census", "paths": ["hits"], "max_matches": 5}
                res = await call(session, "batch_read", {"specs": [grep], "cwd": str(repo)})
                text = _text(res).replace("\\", "/")
                assert "300 match(es) in 30 file(s)" in text
                for i in range(1, 31):
                    assert f"hits/f{i:02d}.txt (10)" in text

                res = await call(session, "batch_read", {"specs": [{**grep, "mode": "files"}], "cwd": str(repo)})
                text = _text(res).replace("\\", "/")
                for i in range(1, 31):
                    assert f"hits/f{i:02d}.txt (10)" in text
                assert "===" not in text and "needle_census 1" not in text

                start = time.monotonic()
                res = await call(session, "batch_run", {"commands": [
                    {"argv": [sys.executable, "-c", parent_script], "label": "slow", "timeout": 2},
                    {"argv": [sys.executable, "-c", "raise SystemExit(3)"], "label": "bad"},
                    {"argv": [sys.executable, "-c",
                              "import sys; sys.stdout.write(''.join(f'a\\x00b{i}\\n' for i in range(700)))"],
                     "label": "nul"},
                    {"cmd": "git --version ||| count", "label": "objslice"},
                    {"argv": [sys.executable, "-c", "print('x')"], "slices": ["grep:zzz"], "label": "emptied"},
                ], "cwd": str(repo)})
                assert time.monotonic() - start < 15
                by_label = {i["label"]: i for i in _items(res)}
                assert by_label["slow"]["status"] == "timeout"
                assert by_label["bad"]["status"] == "error" and by_label["bad"]["exit_code"] == 3
                run_text = _text(res)
                assert by_label["nul"]["status"] == "ok"
                assert "a\\0b699" in run_text and "NUL bytes shown as" in run_text
                assert by_label["objslice"]["status"] == "ok" and by_label["objslice"]["exit_code"] == 0
                assert "git version" not in run_text
                assert "slices kept none of" in run_text
                nul_read = await call(session, "batch_read", {
                    "specs": [by_label["nul"]["artifact"] + ":1-2"], "cwd": str(repo)})
                assert "a\\0b0" in _text(nul_read)
                assert (proc / "spawned").exists()
                await asyncio.sleep(max(0.0, start + 6 - time.monotonic()))
                assert not (proc / "parent_alive").exists()
                assert not (proc / "child_alive").exists()

                res = await call(session, "batch_run", {"commands": [
                    {"argv": [sys.executable, "-c", "raise SystemExit(1)"], "ok_exit": [0, 1]}], "cwd": str(repo)})
                assert not res.isError and _items(res)[0]["status"] == "ok"

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

                res = await call(session, "batch_edit", {"edits": [edit], "dry_run": True, "cwd": str(repo)})
                assert not res.isError
                assert " keep" in _text(res).replace("\r", "").split("\n")
                assert notes.read_bytes() == b"keep\r\nold line\r\n"

                res = await call(session, "batch_edit", {"edits": [edit], "cwd": str(repo)})
                assert not res.isError
                assert notes.read_bytes() == b"keep\r\nnew line\r\n"
                edit_lines = _text(res).replace("\r", "").split("\n")
                assert "+new line" in edit_lines and "-old line" in edit_lines
                assert " keep" not in edit_lines

                res = await call(session, "batch_edit", {
                    "edits": [{"path": "notes.txt", "search": "new line", "replace": "old line"}],
                    "full_diff": True, "cwd": str(repo)})
                assert not res.isError
                assert " keep" in _text(res).replace("\r", "").split("\n")

                res = await call(session, "batch_edit", {
                    "edits": [{"path": "../outside.txt", "search": "keep", "replace": "gone"}], "cwd": str(repo)})
                assert res.isError
                assert outside.read_bytes() == b"keep\n"

                res = await call(session, "batch_read", {"mode": "survey", "cwd": str(repo)})
                assert not res.isError

    asyncio.run(asyncio.wait_for(session_run(), 40))

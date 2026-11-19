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
        "doc.md": "# Title\n\nIntro.\n\n## Setup (local)\n\nsetup paragraph\n\n## Next\n\nnext paragraph\n\n"
                  "Under Line\n==========\n\nunder text\n\n- bullet one\n- bullet two\n",
    }
    fixture["cut.md"] = (
        "# Top\n\n" + "".join(f"para {i}\n" for i in range(3, 399)) + "\n\n"
        + "".join(f"more {i}\n" for i in range(9))
    )
    fixture["many.md"] = "".join(
        f"## Heading {i}\n\nbody text line for section {i} padded out a bit more\n\n" for i in range(400)
    )
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

                res = await call(session, "batch_read", {
                    "specs": ["notes.txt", {"grep": "needle_token", "paths": ["."]}, {}, "grep:zz_absent_zz"],
                    "cwd": str(repo)})
                assert not res.isError and res.structuredContent is None
                items = _items(res)
                assert [i["status"] for i in items[1:]] == ["ok", "error", "no_match"]
                assert items[0]["status"] == "ok"
                text = _text(res).replace("\\", "/")
                assert re.match(r"# batch_read \(files\) build [0-9a-f]{7}\n", text)
                assert "must have exactly one of" in text and "unknown read kind" not in text
                assert "src/a.txt" in text and "ignored/hit.txt" not in text
                res = await call(session, "batch_read", {"specs": [items[0]["handle"] + ":2-2"], "cwd": str(repo)})
                assert "2: old line" in _text(res) and "1: keep" not in _text(res)

                res = await call(session, "batch_read", {
                    "specs": ["notes.txt"], "budget": {"tokenz": 5}, "cwd": str(repo)})
                assert res.isError and "tokenz" in _text(res)
                assert re.match(r"# batch_read error build [0-9a-f]{7}\n", _text(res))
                res = await call(session, "batch_read", {"specs": [], "cwd": str(repo)})
                assert res.isError and re.match(r"# batch_read error build [0-9a-f]{7}\n", _text(res))

                res = await call(session, "batch_read", {"specs": ["notes.txt@target:1-2"], "cwd": str(repo)})
                assert (
                    "~~~\n=== [target lines 1-2: copy verbatim as search, or edit by range with since] ===\n"
                    "keep\nold line\n=== [end target] ==="
                ) in _text(res).replace("\r", "")

                res = await call(session, "batch_read", {"specs": ["big.txt"], "cwd": str(repo)})
                text = _text(res)
                assert "block 30:" in text and "body 1-1 filler" not in text
                assert "next (read tool)" not in text and '"big.txt:1-630"' in text

                res = await call(session, "batch_read", {"specs": ["doc.md@block:## Setup (local"], "cwd": str(repo)})
                text = _text(res)
                assert "## Setup (local)" in text and "setup paragraph" in text and "## Next" not in text
                res = await call(session, "batch_read", {"specs": ["doc.md@outline"], "cwd": str(repo)})
                text = _text(res)
                assert "## Setup (local)" in text and "## Next" in text and "Under Line" in text
                assert "bullet" not in text
                res = await call(session, "batch_read", {"specs": ["cut.md@block:# Top"], "cwd": str(repo)})
                assert 'read "cut.md:399-409" to continue' in _text(res)

                res = await call(session, "batch_read", {
                    "specs": ["many.md"], "budget": {"tokens": 500}, "cwd": str(repo)})
                text = _text(res).replace("\r", "")
                next_line = [ln for ln in text.split("\n") if ln.startswith("next (read tool): specs=")]
                found = re.findall(r'"(artifact:[^:"]+:(\d+)-400)"', next_line[0]) if next_line else []
                assert len(found) == 1
                spec, first = found[0][0], int(found[0][1])
                assert first > 1
                assert f'more outline line(s): "{spec}"' in text
                assert f": ## Heading {first - 2}\n" in text and f": ## Heading {first - 1}\n" not in text
                res = await call(session, "batch_read", {"specs": [spec], "cwd": str(repo)})
                assert f"{first}: {4 * (first - 1) + 1}: ## Heading {first - 1}" in _text(res)
                assert ": ## Heading 399" in _text(res)

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
                assert "=== hits/f05.txt (1 of 10) ===" in text and "=== hits/f06.txt" not in text

                res = await call(session, "batch_read", {"specs": ["grep:needle_census in hits/f02.txt hits/f03.txt"], "cwd": str(repo)})
                assert "20 match(es) in 2 file(s)" in _text(res)

                res = await call(session, "batch_read", {"specs": [{"git": "diff", "stat": True}], "cwd": str(repo)})
                assert "notes.txt |" in _text(res) and "@@" not in _text(res)

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
                    {"argv": [sys.executable, "-c", "import sys; sys.stdout.write("
                              "'\\x1b[31mred\\x1b[0m\\n10%\\r50%\\r100%\\n' + 'same\\n' * 5)"], "label": "noisy"},
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
                assert "slices kept none of" in run_text and by_label["emptied"]["artifact"]
                assert "red\n100%\nsame\n[... repeated 4 more times]" in run_text.replace("\r", "")
                assert "\x1b" not in run_text and "50%" not in run_text and by_label["noisy"]["artifact"]
                nul_read = await call(session, "batch_read", {
                    "specs": [by_label["nul"]["artifact"] + ":1-2"], "cwd": str(repo)})
                assert "a\\0b0" in _text(nul_read)
                assert (proc / "spawned").exists()
                await asyncio.sleep(max(0.0, start + 6 - time.monotonic()))
                assert not (proc / "parent_alive").exists()
                assert not (proc / "child_alive").exists()

                res = await call(session, "batch_run", {"commands": [
                    {"argv": [sys.executable, "-c", "raise SystemExit(1)"], "ok_exit": [0, 1], "label": "okexit"},
                    {"argv": [sys.executable, "-c",
                              "import sys; sys.stdout.write('same\\n' * 300 + "
                              "''.join(f'unique line number {i} padded padded\\n' for i in range(400)))"],
                     "label": "folded"},
                    {"argv": [sys.executable, "-c",
                              "print('a'); print('-' * 40); print('b\\x0cc'); print('d')"],
                     "slices": ["target:2-3"], "label": "dashes"},
                ], "cwd": str(repo)})
                by_label = {i["label"]: i for i in _items(res)}
                assert not res.isError and by_label["okexit"]["status"] == "ok"
                run_text = _text(res).replace("\r", "")
                assert ("=== [target: copy verbatim to batch_edit] ===\n" + "-" * 40
                        + "\nb\x0cc\n=== [end target] ===") in run_text
                hint = re.search(r'omitted: "(artifact:[^"]+):1-387"', run_text)
                assert hint
                res_tail = await call(session, "batch_read", {"specs": [hint.group(1) + ":387-388"], "cwd": str(repo)})
                assert "387: unique line number 384 padded padded" in _text(res_tail)
                assert "388: unique line number 385 padded padded" in _text(res_tail)
                raw_lines = [ln for ln in run_text.split("\n") if "output condensed" in ln and 'raw: "artifact:' in ln]
                assert raw_lines
                raw_ref = re.search(r'raw: "(artifact:[^"]+)"', raw_lines[0])
                assert raw_ref and raw_ref.group(1) != hint.group(1)
                assert run_text.count("output condensed") == 1

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
                    "edits": [{"path": "../outside.txt", "search": "keep", "replace": "gone"},
                              {"path": "nope.txt", "search": "a", "replace": "b"}], "cwd": str(repo)})
                assert res.isError and "nope.txt: file not found" in _text(res)
                assert outside.read_bytes() == b"keep\n"

                sha = _items(await call(session, "batch_read", {"specs": ["notes.txt"], "cwd": str(repo)}))[0]["hash"]
                ranged = {"path": "notes.txt", "range": "2", "replace": "ranged"}
                res = await call(session, "batch_edit", {"edits": [{**ranged, "since": "0" * 12}], "cwd": str(repo)})
                assert res.isError and "changed since it was read" in _text(res)
                assert notes.read_bytes() == b"keep\r\nold line\r\n"
                res = await call(session, "batch_edit", {"edits": [{**ranged, "since": sha[:12]}], "cwd": str(repo)})
                assert not res.isError and notes.read_bytes() == b"keep\r\nranged\r\n"

                ff = repo / "ff.txt"
                ff.write_bytes(b"a\x0cb\nc\n")
                ff_hash = _items(await call(session, "batch_read", {"specs": ["ff.txt"], "cwd": str(repo)}))[0]["hash"]
                res = await call(session, "batch_edit", {
                    "edits": [{"path": "ff.txt", "range": "1", "since": ff_hash[:12], "replace": "X"}],
                    "cwd": str(repo)})
                assert not res.isError and ff.read_bytes() == b"X\nb\nc\n"

                sql = repo / "q.sql"
                sql.write_bytes(b"select 1;\n-- old note\nselect 2;\n")
                res = await call(session, "batch_edit", {
                    "edits": [{"path": "q.sql", "search": "-- old note\n", "replace": ""}], "cwd": str(repo)})
                assert not res.isError and sql.read_bytes() == b"select 1;\nselect 2;\n"
                sql_lines = _text(res).replace("\r", "").split("\n")
                assert "--- old note" in sql_lines and "--- a/q.sql" not in sql_lines

                res = await call(session, "batch_read", {"mode": "survey", "cwd": str(repo)})
                assert not res.isError
                text = _text(res).replace("\\", "/")
                assert re.match(r"# batch_read \(survey\) build [0-9a-f]{7}\n# Survey: ", text)
                assert re.search(r"M notes\.txt \+\d+ -\d+", text) and "Diff stat" not in text
                res = await call(session, "batch_read", {"mode": "survey", "cwd": str(repo / "hits")})
                assert "notes.txt" not in _text(res)

                assert sum(len(json.dumps(t.inputSchema)) + len(t.description or "") for t in tools.tools) <= 5200

    asyncio.run(asyncio.wait_for(session_run(), 40))

from __future__ import annotations

import asyncio
import errno
import hashlib
import importlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tools.validation.git_test_support import seed_git

ROOT = Path(__file__).resolve().parents[3]
SERVER = ROOT / "skills" / "workbench" / "provision" / "assets" / "batch-ops" / "batch_ops_server.py"
GUARD = SERVER.parent / "batch_ops_guard.py"
ENVELOPE = "batch_ops/envelope"


def _text(result) -> str:
    return "\n".join(c.text for c in result.content if getattr(c, "text", None))


def _items(result) -> list[dict]:
    return result.meta[ENVELOPE]["items"]


def test_batch_ops_stdio_session(tmp_path, monkeypatch):
    monkeypatch.delenv("BATCH_OPS_ARTIFACT_DIR", raising=False)
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))
    monkeypatch.syspath_prepend(str(SERVER.parent))
    ArtifactStore = importlib.import_module("batch_ops.artifacts").ArtifactStore
    SafetyError = importlib.import_module("batch_ops.safety").SafetyError

    if sys.platform == "win32":
        store = ArtifactStore()
        assert store.root == tmp / "batch_ops"
        assert store.get(store.put(b"x")) == b"x"
    else:
        store = ArtifactStore()
        default_root = tmp / f"batch_ops-{os.geteuid()}"
        assert store.root == default_root
        assert stat.S_IMODE(default_root.lstat().st_mode) == 0o700
        assert store.get(store.put(b"x")) == b"x"
        default_root.chmod(0o755)
        with pytest.raises(SafetyError):
            ArtifactStore()
        shutil.rmtree(default_root)
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir(mode=0o700)
        default_root.symlink_to(elsewhere, target_is_directory=True)
        with pytest.raises(SafetyError):
            ArtifactStore()
        default_root.unlink()

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
    fixture["aa/ab/x.txt"] = "x\n"
    fixture["blocks.txt"] = (
        "alpha:\n    beta one\n    target_mark first\n    target_mark again\n    beta two\n"
        "gamma:\n    delta\n    target_mark second\n    delta tail\nwide:\n"
        + "".join(f"    {'target_mark deep' if n == 120 else f'row {n}'}\n" for n in range(1, 151))
    )
    for i in range(1, 31):
        fixture[f"hits/f{i:02d}.txt"] = "".join(f"needle_census {n}\n" for n in range(1, 11))
    fixture[".github/workflows/ci.yml"] = (
        "name: ci\njobs:\n  t:\n    steps:\n      - run: pytest -q\n"
        "      - name: lint\n        run: |\n          ruff check .\n          ruff format --check .\n          echo done\n"
        "      - name: ship\n        run: >-\n          deploy --env prod\n          --fast\n"
    )
    fixture["Makefile"] = (
        ".PHONY: build test lint\nVAR := x\nbuild: deps\n\tcc -o app main.c\ntest lint:\n\techo t\n%.o: %.c\n"
    )
    fixture["package.json"] = '{"scripts": {"test": "vitest run", "build": "tsc"}}\n'
    fixture["src/package.json"] = "{bad\n"
    fixture["src/Makefile"] = "big:\n" + "#" * (1024 * 1024)
    fixture["src/GNUmakefile"] = "fallback:\n"
    fixture["src/fail.py"] = "".join(f"v{n} = {n}\n" for n in range(1, 13))
    fixture["src/other.txt"] = "o1\no2\no3\n"
    fixture["tests/test_misc.py"] = "x = 1\n"
    seed_git(repo, fixture)
    reader = importlib.import_module("batch_ops.reader")
    denied = {repo / ".github" / "workflows" / "ci.yml", repo / "package.json"}
    original_stat = Path.stat

    def guarded_stat(self, *args, **kwargs):
        if self in denied:
            raise PermissionError(errno.EACCES, "Permission denied")
        return original_stat(self, *args, **kwargs)

    with monkeypatch.context() as m:
        m.setattr(Path, "stat", guarded_stat)
        rows = reader._survey_commands(repo)
    assert "  .github/workflows/ci.yml: steps not read (unreadable)" in rows
    assert "  package.json: scripts not read (unreadable)" in rows
    assert "  Makefile: make build, make test, make lint" in rows
    (repo / "later.txt").write_text("later\n", encoding="utf-8")
    for git_args in (["add", "later.txt"], ["commit", "-qm", "later only"]):
        subprocess.run(["git", *git_args], cwd=repo, check=True, capture_output=True)
    (repo / "tests" / "a_test.py").write_text("y = 1\n", encoding="utf-8")
    notes = repo / "notes.txt"
    notes.write_bytes(b"keep\r\nold line\r\n")
    (repo / "ignored").mkdir(exist_ok=True)
    (repo / "ignored" / "hit.txt").write_text("needle_token\n", encoding="utf-8")
    (repo / "ignored" / "two.txt").write_text("needle_token\n", encoding="utf-8")
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
    server_env = {"PYTHONDONTWRITEBYTECODE": "1"}
    if os.name == "nt":
        # No bash on PATH outside %SystemRoot%, so the default shell must be found through Git.
        system_root = os.path.normcase(os.environ.get("SystemRoot", ""))
        server_env["PATH"] = os.pathsep.join(
            entry for entry in os.environ.get("PATH", "").split(os.pathsep)
            if not (entry and (Path(entry) / "bash.exe").is_file()
                    and not os.path.normcase(entry).startswith(system_root))
        )
    params = StdioServerParameters(
        command=sys.executable, args=[str(SERVER)], cwd=str(repo), env=server_env
    )

    apply_slices = importlib.import_module("batch_ops.slices").apply_slices
    document = '{"items": [{"n": 1, "v": "a"}, {"n": 2, "v": "b"}, {"n": 3}]}'
    assert apply_slices(document, ["json:items[*].n"]) == ("1\n2\n3", [])
    assert apply_slices(document, ["json:items[*].v"]) == ("a\nb", [])
    actions = '{"Action":"pass"}\n{"Action":"fail"}\n{"Action":"pass"}\n'
    assert apply_slices(actions, ["json:Action", "uniq"]) == ("2 pass\n1 fail", [])
    assert apply_slices(actions, ['countby:"Action":"(\\w+)"']) == ("2 pass\n1 fail", [])
    numbered = "x10\nnone\nx9\nx-1\n"
    assert apply_slices(numbered, ["sort:n"]) == ("x-1\nx9\nx10\nnone", [])
    assert apply_slices(numbered, ["sort:-n"]) == ("x10\nx9\nx-1\nnone", [])
    assert apply_slices("a b  c\nd e f\n", ["cut::2"]) == ("b\ne", [])
    assert apply_slices("a,b,c\nx,y\n", ["cut:,:3"]) == ("c", [])
    assert apply_slices("a\tb\tc\nd\n", ["cut:\\t:2"]) == ("b", [])
    assert apply_slices("not json\n", ["json:a"]) == ("not json", ["json: input is neither JSON nor JSON Lines"])
    # Shell text written after ' ||| ' is parsed as a slice; the error must say it never ran.
    _, shell_errors = apply_slices("a\nb\n", ["tail:8; git diff --stat"])
    assert len(shell_errors) == 1 and "`; git diff --stat` was read as a slice and never ran" in shell_errors[0]
    for shell_op, shell_text in [
        ("tail:8 && make", "&& make"),
        ("head:3 || true", "|| true"),
        ("tail:5 | wc -l", "| wc -l"),
        ("lines:1-20; git diff --stat", "; git diff --stat"),
        ("raw:x; ls", "; ls"),
        ("target:x && ls", "&& ls"),
        ("lines:5-2,1; ls", "; ls"),
        ("num:x; ls", "; ls"),
        ("cut:;:2; ls", "; ls"),
        ("cut:,:2; echo a:b", "; echo a:b"),
        ("cut:&&:2 ; echo a:b", "; echo a:b"),
        ("cut: | :1 | grep a:b", "| grep a:b"),
        ("json:items[0]; ls", "; ls"),
        ("json:items; ls .", "; ls ."),
        ("json:a;b[x]", ";b[x]"),
    ]:
        _, hinted = apply_slices("a\nb\n", [shell_op])
        assert len(hinted) == 1 and f"`{shell_text}` was read as a slice and never ran" in hinted[0], shell_op
    for plain_op, plain_errors in [
        ("tail:x", ["tail:x: expected an integer"]),
        ("num:1|2", ["num:1|2: invalid literal for int() with base 10: '1|2'"]),
        ("cut:;:x", ["cut:;:x: N must be a positive integer"]),
        ("cut:;", ["cut:;: expected cut:SEP:N"]),
        ("cut:||:x", ["cut:||:x: N must be a positive integer"]),
    ]:
        assert apply_slices("a\nb\n", [plain_op])[1] == plain_errors, plain_op

    run_commands = importlib.import_module("batch_ops.runner").run_commands
    read_batch = importlib.import_module("batch_ops.reader").read_batch
    specs_mod = importlib.import_module("batch_ops.specs")
    parse_run_spec, parse_read_spec = specs_mod.parse_run_spec, specs_mod.parse_read_spec
    budget_mod = importlib.import_module("batch_ops.budget")
    Budget, BudgetTracker = budget_mod.Budget, budget_mod.BudgetTracker
    alias_store = ArtifactStore(tmp_path / "alias_store")
    alias_root = repo.resolve()

    def run_labelled(specs, **kwargs):
        requests = [parse_run_spec(spec, index) for index, spec in enumerate(specs, start=1)]
        return asyncio.run(run_commands(requests, root=alias_root, tracker=BudgetTracker(Budget()),
                                        artifacts=alias_store, bind_labels=True, **kwargs))

    def read_many(specs, budget=None, root=alias_root):
        return asyncio.run(read_batch([parse_read_spec(spec) for spec in specs], root=root,
                                      tracker=BudgetTracker(budget or Budget()), artifacts=alias_store))

    def read_labelled(spec, budget=None):
        return read_many([spec], budget)

    def alias_text(name):
        record = alias_store.resolve(alias_root, name)
        if record is None:
            return None
        return alias_store.get_text(str(record["target"])).replace("\r\n", "\n")

    def py(code, **extra):
        return {"argv": [sys.executable, "-c", code], **extra}

    def failing_bind(*args, **kwargs):
        raise OSError("simulated save failure")

    # a. json: on stderr is skipped when stderr is not JSON; stdout errors and JSON stderr stay.
    json_a = py("import sys; print('{\"a\": 1}'); sys.stderr.write('warn')", slices=["json:a"])
    json_b = py("import sys; print('not json'); sys.stderr.write('{\"a\": 2}')", slices=["json:a"])
    res_a, res_b = run_labelled([json_a, json_b])
    assert res_a.stdout.strip() == "1" and "warn" in res_a.stderr and res_a.slice_errors == []
    assert res_b.slice_errors == ["stdout json: input is neither JSON nor JSON Lines"]
    assert res_b.stderr.strip() == "2"

    # b. a dry run leaves both aliases untouched.
    rb_cmd = py("import sys; print('out1'); sys.stderr.write('err1')", label="rb_cmd")
    run_labelled([rb_cmd])
    run_labelled([py("print('dry')", label="rb_cmd")], dry_run=True)
    assert alias_text("rb_cmd").strip() == "out1" and alias_text("rb_cmd.stderr") == "err1"

    # c. merged streams rebind the label and drop the stale stderr alias.
    run_labelled([{**rb_cmd, "merge_streams": True}])
    merged = alias_text("rb_cmd")
    assert "out1" in merged and "err1" in merged
    assert alias_store.resolve(alias_root, "rb_cmd.stderr") is None

    # d. a failed save on the command side removes both aliases.
    run_labelled([rb_cmd])
    assert alias_text("rb_cmd.stderr") == "err1"
    with monkeypatch.context() as m:
        m.setattr(alias_store, "bind", failing_bind)
        run_labelled([rb_cmd])
    assert alias_store.resolve(alias_root, "rb_cmd") is None
    assert alias_store.resolve(alias_root, "rb_cmd.stderr") is None

    # e. a failed save on the read side removes the alias while the read succeeds.
    rb_grep = {"grep": "needle_token", "paths": ["src"], "label": "rb_grep"}
    read_labelled(rb_grep)
    assert "needle_token here" in alias_text("rb_grep")
    with monkeypatch.context() as m:
        m.setattr(alias_store, "bind", failing_bind)
        (grep_result,) = read_labelled(rb_grep)
    assert grep_result.status == "ok"
    assert alias_store.resolve(alias_root, "rb_grep") is None

    # f. a timed-out command keeps its partial output under its label.
    (slow,) = run_labelled([py("import time; print('partial', flush=True); time.sleep(30)",
                               label="rb_slow", timeout=3)])
    assert slow.status == "timeout" and "partial" in alias_text("rb_slow")

    # g. an abandoned read binds nothing, then or later.
    read_labelled(rb_grep)
    assert "needle_token here" in alias_text("rb_grep")
    original_grep = reader._grep_request

    def slow_grep(*args, **kwargs):
        time.sleep(2)
        return original_grep(*args, **kwargs)

    with monkeypatch.context() as m:
        m.setattr(reader, "_grep_request", slow_grep)
        (late,) = read_labelled(rb_grep, Budget(time_s=1))
    assert late.status == "error" and "timed out" in late.message
    assert alias_store.resolve(alias_root, "rb_grep") is None

    # h. an item-limit skip drops the alias; a deferred read keeps the one its full read made.
    read_labelled(rb_grep)
    assert "needle_token here" in alias_text("rb_grep")
    first_read, skipped_read = read_many([{"glob": "src/*.txt"}, rb_grep], Budget(max_items=1))
    assert skipped_read.status == "skipped"
    assert alias_store.resolve(alias_root, "rb_grep") is None
    defer_root = tmp_path / "defer_root"
    defer_root.mkdir()
    (defer_root / "big.txt").write_text("needle_token here\n" * 400, encoding="utf-8")
    _, deferred_read = read_many(
        [{"grep": "needle_token", "label": "rb_d1"}, {"grep": "needle_token", "label": "rb_d2"}],
        Budget(tokens=500), root=defer_root.resolve(),
    )
    assert deferred_read.status == "deferred"
    assert alias_store.resolve(defer_root.resolve(), "rb_d1") is not None
    assert alias_store.resolve(defer_root.resolve(), "rb_d2") is not None

    # i. a read or a command labelled with a reserved stderr name never replaces the stderr alias.
    run_labelled([rb_cmd])
    assert alias_text("rb_cmd.stderr") == "err1"
    run_labelled([py("print('evil')", label="rb_cmd.stderr")])
    (reserved_grep,) = read_labelled({"grep": "needle_token", "paths": ["src"], "label": "rb_cmd.stderr"})
    assert reserved_grep.status == "ok"
    (reserved_glob,) = read_labelled({"glob": "src/*.txt", "label": "rb_cmd.stderr"})
    assert reserved_glob.status == "ok"
    assert alias_text("rb_cmd.stderr") == "err1"

    # j. artifact reads take slices after a range, in a string, in a list, or in an object.
    run_labelled([py("print('a'); print('b'); print('c'); print('d')", label="rb_lines")])

    def body_of(spec):
        (result,) = read_labelled(spec)
        return result.body.replace("\r\n", "\n").strip()

    assert body_of("artifact:rb_lines:2-3 ||| sort:-") == "c\nb"
    assert body_of({"artifact": "rb_lines", "slices": "sort:- ||| head:2"}) == "d\nc"
    assert body_of({"artifact": "rb_lines", "slices": ["sort:-", "head:2"]}) == "d\nc"
    with pytest.raises(specs_mod.SpecError, match="slices apply only to artifact reads"):
        parse_read_spec({"path": "src/other.txt", "slices": ["head:1"]})
    with pytest.raises(specs_mod.SpecError, match="use a grep: slice instead of pattern"):
        parse_read_spec({"artifact": "rb_lines", "slices": ["head:1"], "pattern": "x"})

    # k. in sort:n a minus sign joined to a word character is a hyphen, not a sign.
    hyphens = "build-10\nbuild-2\nbuild-30\n"
    assert apply_slices(hyphens, ["sort:n"]) == ("build-2\nbuild-10\nbuild-30", [])
    assert apply_slices(hyphens, ["sort:-n"]) == ("build-30\nbuild-10\nbuild-2", [])
    assert apply_slices("t 3\n-7\nt -5\nrun_-4\n", ["sort:n"]) == ("-7\nt -5\nt 3\nrun_-4", [])

    # l. each reads every file its source found, bounded by limit and the 32-file call cap.
    def slash(path):
        return (path or "").replace("\\", "/")

    bounded = read_many([
        {"grep": "needle_census", "paths": ["hits"], "max_matches": 5, "label": "hs"},
        {"each": "hs", "read": ":10-10", "limit": 30},
        {"glob": "hits/*.txt", "label": "hg"},
        {"each": "hg"},
    ])
    assert len(bounded) == 36
    assert [r.kind for r in (bounded[0], bounded[1], bounded[32], bounded[33])] == ["grep", "each", "glob", "each"]
    assert bounded[1].meta["expanded"] == 30 and bounded[1].message == "30 file(s) listed by hs; 30 read"
    assert [slash(r.path) for r in bounded[2:32]] == [f"hits/f{i:02d}.txt" for i in range(1, 31)]
    assert all(r.status == "ok" and "needle_census 10" in r.body and "needle_census 9" not in r.body
               for r in bounded[2:32])
    assert bounded[33].meta["expanded"] == 2 and bounded[33].meta["over_cap"] == 6
    assert bounded[33].message == "30 file(s) listed by hg; 2 read; 22 past limit 8; 6 past the 32-file call cap"
    assert [slash(r.path) for r in bounded[34:]] == ["hits/f01.txt", "hits/f02.txt"]
    assert all(all(f"needle_census {n}" in r.body for n in range(1, 11)) for r in bounded[34:])

    # m. an expansion the report has no room for is deferred, listed whole in next: as a literal spec.
    for suffix in (":2-9", "@outline"):
        crowded = read_many(
            [{"glob": "hits/*.txt", "label": "hb"}, {"each": "hb", "read": suffix}], Budget(tokens=600))
        deferred = [r for r in crowded if r.status == "deferred"]
        assert deferred and all(
            r.kind == "file" and r.meta["continuation"] == f"{r.path}{suffix}" for r in deferred)

    # n. git sources expand over files that exist now, and over every co-changed file, not the 20 shown.
    git_repo = tmp_path / "git_repo"
    seed_git(git_repo, {
        "keep.txt": "k\n", "edit.txt": "e1\n", "gone.txt": "g\n", "more.txt": "m\n",
        " lead.txt": "l\n", "caf\u00e9.txt": "a\n",
        **{f"c{i:02d}.txt": f"c{i}\n" for i in range(1, 21)},
    })
    (git_repo / "keep.txt").write_text("k2\n", encoding="utf-8")
    (git_repo / "more.txt").write_text("m2\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(git_repo), "commit", "-qam", "second"], check=True, capture_output=True)
    (git_repo / "edit.txt").write_text("e2\n", encoding="utf-8")
    (git_repo / "gone.txt").unlink()
    (git_repo / "new").mkdir()
    (git_repo / "new" / "n.txt").write_text("n\n", encoding="utf-8")
    from_git = read_many([
        {"git": "changed", "label": "ch"},
        {"each": "ch", "read": ":1-1"},
        {"git": "cochange", "paths": ["keep.txt"], "label": "co"},
        {"each": "co", "read": ":1-1", "limit": 24},
    ], root=git_repo.resolve())
    assert len(from_git) == 29
    assert from_git[1].meta["expanded"] == 1 and from_git[1].meta["skipped"] == 2
    assert from_git[1].message == "3 file(s) listed by ch; 1 read; 2 not a file now or outside cwd"
    assert slash(from_git[2].path) == "edit.txt" and "e2" in from_git[2].body
    assert from_git[3].meta["commits"] == 2 and "2x more.txt" in from_git[3].body
    assert from_git[4].meta["expanded"] == 24 and from_git[4].meta["skipped"] == 0
    assert from_git[4].meta["over_limit"] == 1
    assert from_git[4].message == "25 file(s) listed by co; 24 read; 1 past limit 24"
    assert [slash(r.path) for r in from_git[5:]] == (
        ["more.txt", " lead.txt"] + [f"c{i:02d}.txt" for i in range(1, 21)] + ["caf\u00e9.txt", "edit.txt"])

    # the batch deadline stops the walk: paths after it are counted, not checked, and the real deadline is passed.
    ticks = iter([0.0])
    with monkeypatch.context() as m:
        m.setattr(reader, "time", type("Clock", (), {"monotonic": staticmethod(lambda: next(ticks, 9.0))})())
        timed_item, timed_reads, _ = reader._each_item(
            parse_read_spec({"each": "ch"}), [parse_read_spec({"git": "changed", "label": "ch"})],
            [from_git[0]], git_repo.resolve(), 32, 5.0)
    assert timed_item.status == "ok"
    assert timed_item.message == "3 file(s) listed by ch; 1 read; 2 not checked by the batch deadline"
    assert timed_item.meta["unchecked"] == 2 and timed_item.meta["skipped"] == 0
    assert [slash(r.path) for r in timed_reads] == ["edit.txt"]
    seen_args: list = []
    original_each = reader._each_item

    def spy_each(*args):
        seen_args.append(args[-1])
        return original_each(*args)

    with monkeypatch.context() as m:
        m.setattr(reader, "_each_item", spy_each)
        read_many([{"git": "changed", "label": "ch"}, {"each": "ch"}], root=git_repo.resolve())
    assert len(seen_args) == 1 and 0 < seen_args[0] - time.monotonic() <= Budget().time_s

    # names git escapes are listed verbatim, and a commit that lists no files still counts.
    quoted_repo = tmp_path / "quoted_repo"
    seed_git(quoted_repo, {"s.txt": "s\n"})
    (quoted_repo / "s.txt").write_text("s2\n", encoding="utf-8")

    def git_in(repo_dir, *args, stdin=None):
        return subprocess.run(["git", "-C", str(repo_dir), *args], input=stdin, check=True,
                              capture_output=True, text=True).stdout.strip()

    git_in(quoted_repo, "add", "s.txt")
    blob = git_in(quoted_repo, "hash-object", "-w", "--stdin", stdin="x\n")
    escaped = ["b\\ack.txt", "n\nl.txt", "q\"uote.txt", "t\tab.txt"]
    for name in escaped:
        git_in(quoted_repo, "-c", "core.protectNTFS=false", "update-index", "--add",
               "--cacheinfo", f"100644,{blob},{name}")
    git_in(quoted_repo, "commit", "-qm", "names")
    [verbatim] = read_many([{"git": "cochange", "paths": ["s.txt"]}], root=quoted_repo.resolve())
    assert verbatim.found == escaped and verbatim.meta["commits"] == 2
    real_git = reader._git

    def fileless_git(root, args, *rest, **kw):
        if "log" in args:
            return 0, "\x00aaaaaaa\x00\x00bbbbbbb\x00\nkeep.txt\x00x.txt\x00", ""
        return real_git(root, args, *rest, **kw)

    with monkeypatch.context() as m:
        m.setattr(reader, "_git", fileless_git)
        [fileless] = read_many([{"git": "cochange", "paths": ["keep.txt"]}], root=git_repo.resolve())
    assert fileless.meta["commits"] == 2 and fileless.found == ["x.txt"]

    # o. an unknown, later, non-source, ambiguous or failed source is an error item; bad templates are refused.
    refused = read_many([
        {"each": "later"}, {"glob": "src/*.txt", "label": "later"},
        {"path": "notes.txt", "label": "plain"}, {"each": "plain"},
        {"glob": "src/*.txt", "label": "dup"}, {"grep": "needle_token", "label": "dup"}, {"each": "dup"},
        {"grep": "needle_token", "paths": [str(tmp_path)], "label": "bad"}, {"each": "bad"},
    ])
    assert len(refused) == 9
    assert [(refused[i].kind, refused[i].status) for i in (0, 3, 6, 8)] == [("each", "error")] * 4
    for bad_each in (
        {"each": "x", "read": "grep:a"}, {"each": "x", "read": "@diff"}, {"each": "x", "read": "@block:a@b"},
        {"each": "x", "limit": 33}, {"each": ""}, {"each": "x", "path": "notes.txt"},
    ):
        with pytest.raises(specs_mod.SpecError):
            parse_read_spec(bad_each)

    # p. edit text may be a list of parts copied from files as read and from kept results, all resolved first.
    types_mod = importlib.import_module("batch_ops.types")
    editor_mod = importlib.import_module("batch_ops.editor")
    render_mod = importlib.import_module("batch_ops.render")
    parts = tmp_path / "parts"
    parts.mkdir()
    mv_bytes = b"import os\r\ndef keep():\r\n    return 1\r\ndef moved():\r\n    return 2\r\n"
    (parts / "mv.py").write_bytes(mv_bytes)
    (parts / "other.txt").write_bytes(b"o1\no2\no3\n")
    sha = hashlib.sha256(mv_bytes).hexdigest()[:12]
    alias_store.bind(parts.resolve(), "gen", b"g1\ng2\n", ".txt", "parts test")

    def apply_parts(edits=(), new_files=(), deletes=(), renames=()):
        bundle = types_mod.EditRequestBundle(
            edits=[specs_mod.parse_edit_spec(e) for e in edits],
            new_files=specs_mod.parse_new_files(list(new_files)),
            deletes=list(deletes), renames=[specs_mod.parse_rename(r) for r in renames], cwd=str(parts),
        )
        return asyncio.run(editor_mod.apply_edits(bundle, root=parts, artifacts=alias_store))

    def file_part(path, span, since=None):
        return {"path": path, "range": span, "since": since or sha}

    stale = apply_parts(edits=[{"path": "other.txt", "search": "o2\n", "replace": [file_part("mv.py", "4-5", "0" * 12)]}])
    assert not stale.ok and any("changed since it was read" in error for error in stale.errors)
    assert (parts / "other.txt").read_bytes() == b"o1\no2\no3\n"

    outside_sha = hashlib.sha256(outside.read_bytes()).hexdigest()[:12]
    bin_bytes, latin_bytes = b"a\x00b\n", b"caf\xe9\n"
    (parts / "bin.dat").write_bytes(bin_bytes)
    (parts / "lat.txt").write_bytes(latin_bytes)
    bin_sha = hashlib.sha256(bin_bytes).hexdigest()[:12]
    latin_sha = hashlib.sha256(latin_bytes).hexdigest()[:12]
    copy_new = lambda source, since=None, span="1": [{"path": "cp.txt", "content": [file_part(source, span, since)]}]
    for refused_args in (
        {"new_files": copy_new("mv.py"), "deletes": ["mv.py"]},
        {"new_files": copy_new("mv.py"), "renames": [{"from": "mv.py", "to": "mv3.py"}]},
        {"new_files": [{"path": "mv.py", "content": "x\n", "overwrite": True}, *copy_new("mv.py")]},
        {"new_files": copy_new("../outside.txt", outside_sha)},
        {"new_files": copy_new("bin.dat", bin_sha)},
        {"new_files": copy_new("lat.txt", latin_sha)},
        {"new_files": copy_new("gone.txt", sha)},
        {"new_files": copy_new("mv.py", sha, "4-9")},
    ):
        assert not apply_parts(**refused_args).ok
        assert (parts / "mv.py").read_bytes() == mv_bytes and outside.read_bytes() == b"keep\n"
        assert not (parts / "cp.txt").exists() and not (parts / "mv3.py").exists()
    binary = apply_parts(new_files=copy_new("bin.dat", bin_sha))
    assert not binary.ok and any("binary source" in error for error in binary.errors)

    moved = apply_parts(
        edits=[
            {"path": "mv.py", "range": "4-5", "since": sha, "replace": ""},
            {"path": "mv.py", "range": "1", "since": sha,
             "replace": [file_part("mv.py", "1-1"), "from mv2 import moved\n"]},
            {"path": "other.txt", "search": "o2\n", "replace": [file_part("mv.py", "3-3")]},
        ],
        new_files=[{"path": "mv2.py", "content": ["# moved\n", file_part("mv.py", "4-5"), {"artifact": "gen:2-2"}]}],
    )
    assert moved.ok, moved.errors
    assert (parts / "mv.py").read_bytes() == b"import os\r\nfrom mv2 import moved\r\ndef keep():\r\n    return 1\r\n"
    assert (parts / "mv2.py").read_bytes() == b"# moved\r\ndef moved():\r\n    return 2\r\ng2\r\n"
    assert (parts / "other.txt").read_bytes() == b"o1\n    return 1\no3\n"
    moved_text = render_mod.render_edit_report(moved)
    assert "copied 2 line(s) from mv.py:4-5" in moved_text
    assert "copied 1 line(s) from artifact:gen:2-2" in moved_text
    assert not any("return 2" in (change.message or "") for change in moved.changes)

    for bad_parts in (
        {"path": "mv.py", "search": "x", "replace": []},
        {"path": "mv.py", "search": "x", "replace": [{**file_part("mv.py", "1"), "lines": "1"}]},
    ):
        with pytest.raises(specs_mod.SpecError):
            specs_mod.parse_edit_spec(bad_parts)

    cli_src = b"c1\nc2\n"
    (parts / "cli_src.txt").write_bytes(cli_src)
    cli_part = file_part("cli_src.txt", "2-2", hashlib.sha256(cli_src).hexdigest()[:12])
    cli_mod = importlib.import_module("batch_ops.cli")
    dict_payload = {"new_files": {"cli_dict.txt": [cli_part]}}
    assert cli_mod.main(["edit", "--root", str(parts), "--payload", json.dumps(dict_payload)]) == 1
    assert not (parts / "cli_dict.txt").exists()
    cli_payload = {"new_files": [{"path": "cli_copy.txt", "content": [cli_part]}]}
    assert cli_mod.main(["edit", "--root", str(parts), "--payload", json.dumps(cli_payload)]) == 0
    assert (parts / "cli_copy.txt").read_bytes() == b"c2\n"
    (parts / "cli_rb.txt").write_bytes(b"a\n")
    cli_fail = ["--verify", "exit 1"]
    rb_payload = {"edits": [{"path": "cli_rb.txt", "search": "a", "replace": "b"}]}
    assert cli_mod.main(["edit", "--root", str(parts), "--payload", json.dumps(rb_payload), *cli_fail]) != 0
    assert (parts / "cli_rb.txt").read_bytes() == b"b\n"
    rb_payload = {"edits": [{"path": "cli_rb.txt", "search": "b", "replace": "c"}]}
    assert cli_mod.main(["edit", "--root", str(parts), "--payload", json.dumps(rb_payload), *cli_fail,
                         "--rollback"]) != 0
    assert (parts / "cli_rb.txt").read_bytes() == b"b\n"

    async def call(session, name, args):
        return await asyncio.wait_for(session.call_tool(name, args), 20)

    async def session_run():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await asyncio.wait_for(session.initialize(), 20)
                assert "prefixed names" in (init.instructions or "")
                assert "load all three in one request" in (init.instructions or "")

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
                        assert "full_diff" in props and "diff" in props
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
                assert "1 gitignored path(s) not searched" in text
                res = await call(session, "batch_read", {
                    "specs": [{"grep": "needle_census", "paths": ["hits"], "mode": "files", "label": "hs2"},
                              {"each": "hs2", "read": ":1-1", "limit": 3}],
                    "cwd": str(repo)})
                each_items = _items(res)
                assert not res.isError and len(each_items) == 5
                assert all(i["status"] == "ok" for i in each_items)
                assert [slash(i["path"]) for i in each_items[2:]] == ["hits/f01.txt", "hits/f02.txt", "hits/f03.txt"]
                assert "30 file(s) listed by hs2; 3 read; 27 past limit 3" in _text(res)
                res = await call(session, "batch_read", {
                    "specs": [{"grep": "needle_token", "paths": ["ignored"], "ignored": True}],
                    "cwd": str(repo)})
                assert not res.isError and _items(res)[0]["status"] == "ok"
                assert "ignored/hit.txt" in _text(res).replace("\\", "/")
                res = await call(session, "batch_read", {"specs": ["glob:**/a*/**/*.txt"], "cwd": str(repo)})
                text = _text(res).replace("\\", "/")
                assert "matches: 1" in text and text.count("aa/ab/x.txt") == 1
                res = await call(session, "batch_read", {
                    "specs": ["big.txt@context:block 1:0", {"grep": "needle_census [37]$", "paths": ["hits/f01.txt"]}],
                    "cwd": str(repo)})
                text = _text(res).replace("\r", "")
                assert "block 19:" in text and "3: needle_census 3" in text and "--" not in text.split("\n")
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
                assert "outline only" in text and "body 1-1 filler" not in text and '"big.txt:1-630" for all of it' in text
                res = await call(session, "batch_read", {"specs": ["big.txt:1-630"], "cwd": str(repo)})
                text = _text(res)
                assert "body 1-1 filler" in text and _items(res)[0]["status"] == "ok"
                (repo / "plain.csv").write_text("".join(f"{i},{2 * i},{3 * i}\n" for i in range(1, 1501)),
                                                encoding="utf-8")
                res = await call(session, "batch_read", {"specs": ["plain.csv"], "cwd": str(repo)})
                assert _items(res)[0]["status"] == "ok" and "1499,2998,4497" in _text(res)

                def block_groups(count):
                    return "".join(
                        f"block {k}:\n" + "".join(f"    body {k}-{j} filler text to take up room\n" for j in range(1, 21))
                        for k in range(1, count + 1))

                (repo / "mid.txt").write_text(block_groups(10), encoding="utf-8")
                res = await call(session, "batch_read", {"specs": ["mid.txt"], "cwd": str(repo)})
                assert "outline only" in _text(res)
                (repo / "small.txt").write_text(block_groups(6), encoding="utf-8")
                res = await call(session, "batch_read", {"specs": ["small.txt"], "cwd": str(repo)})
                assert _items(res)[0]["status"] == "ok" and "body 6-20 filler" in _text(res)
                res = await call(session, "batch_read", {
                    "specs": ["big.txt"], "budget": {"tokens": 4000}, "cwd": str(repo)})
                text = _text(res)
                assert "outline only" in text and '"big.txt:1-630" in parts' in text
                res = await call(session, "batch_read", {
                    "specs": ["big.txt:1-300", "big.txt:301-630", {"path": "big.txt", "range": "301-630"},
                              "big.txt:331-360", "big.txt:1-630"],
                    "budget": {"tokens": 5000}, "cwd": str(repo)})
                assert not res.isError
                assert [i["status"] for i in _items(res)] == ["ok", "deferred", "deferred", "ok", "deferred"]
                text = _text(res)
                assert "300:     body 15-5 filler" in text
                next_line = [ln for ln in text.split("\n") if ln.startswith("next: call batch_read with specs=")]
                assert next_line and '"big.txt:301-630"' in next_line[0] and '"range": "301-630"' in next_line[0] and '"big.txt:1-630"' in next_line[0]

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
                next_line = [ln for ln in text.split("\n") if ln.startswith("next: call batch_read with specs=")]
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
                next_lines = [ln for ln in lines if ln.startswith("next: call batch_read with specs=")]
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

                bgrep = {"grep": "target_mark", "paths": ["blocks.txt"]}
                res = await call(session, "batch_read", {"specs": [{**bgrep, "blocks": True}], "cwd": str(repo)})
                text = _text(res).replace("\r", "")
                assert text.count("1- alpha:") == 1
                for row in ("3:     target_mark first", "9-     delta tail", "10- wide:", "125- ", "135- ",
                            "130:     target_mark deep"):
                    assert row in text
                assert not re.search(r"(?m)^(124|136|60)- ", text)
                assert "--" in text.split("\n")
                res = await call(session, "batch_read", {"specs": [bgrep], "cwd": str(repo)})
                assert "1- alpha:" not in _text(res)
                res = await call(session, "batch_read", {"specs": [{**grep, "blocks": True}], "cwd": str(repo)})
                text = _text(res).replace("\\", "/")
                assert "blocks skipped: 300 matches over 20" in text and "=== hits/f05.txt (1 of 10) ===" in text
                assert not re.search(r"(?m)^\d+- ", text)  # plain rows: no window lines past 20 matches

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
                res_default = await call(session, "batch_run", {"commands": [
                    {"cmd": "echo shell_probe | tr a-z A-Z", "label": "auto"},
                    {"argv": [sys.executable, "-c", "print('hit 1'); print('x'); print('hit 2')"],
                     "slices": ["context:hit:0"], "label": "ctx0"},
                ], "cwd": str(repo)})
                default_text = _text(res_default).replace("\r", "")
                assert "3: hit 2" in default_text and "--" not in default_text.split("\n")
                assert {i["label"]: i["status"] for i in _items(res_default)}["auto"] == "ok"
                assert "SHELL_PROBE" in default_text
                assert re.search(r"ms bash - auto" if os.name == "nt" else r"ms sh - auto", default_text)
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
                    "echo ran > split_str.txt && echo a ||| b",
                    {"cmd": "echo ran > split_obj.txt && echo a ||| b"},
                    {"cmd": "echo 'a ||| b' | tr '|' x", "slices": [], "label": "literal"},
                    "echo ok ||| count ||| tail:3",
                ], "cwd": str(repo)})
                split_items = _items(res)
                assert split_items[0]["status"] == "error" and split_items[1]["status"] == "error"
                assert "nothing ran" in _text(res)
                assert not (repo / "split_str.txt").exists() and not (repo / "split_obj.txt").exists()
                assert split_items[2]["status"] == "ok" and "a xxx b" in _text(res)
                assert split_items[3]["status"] == "ok"

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

                ref_script = (
                    "print('ignored/hit.txt:1: x'); print('missing.py:3: x'); "
                    f"print({str(outside)!r} + ':1: x'); print('src/a.txt:99: x'); "
                    "print('  File \"src/fail.py\", line 5, in f'); print('src/fail.py:6: AssertionError'); "
                    "print('src/other.txt(2,7): error X'); print('src/fail.py:12: late'); raise SystemExit(1)"
                )
                res = await call(session, "batch_run", {"commands": [
                    {"argv": [sys.executable, "-c", ref_script], "label": "fails"},
                    {"argv": [sys.executable, "-c", "print('src/fail.py:1: note')"], "label": "passref"},
                ], "cwd": str(repo)})
                ref_text = _text(res).replace("\r", "")
                marker = "source now (> marks cited lines):"
                assert ref_text.count(marker) == 1
                shown = ref_text.split(marker)[1]
                for want in ("src/fail.py:2-9", "> 5  v5 = 5", "> 6  v6 = 6", "  9  v9 = 9",
                             "src/other.txt:1-3", "> 2  o2"):
                    assert want in shown
                for unwanted in ("ignored/hit.txt:", "missing.py:", "outside.txt:", "src/a.txt:",
                                 "v12 = 12", "src/fail.py:1-"):
                    assert unwanted not in shown.replace("\\", "/").split("stdout")[0]
                snap_script = (
                    "print('FAILED test_snapshot: received data:image/png;base64,' + 'QUJD' * 15000"
                    " + ' at src/fail.py:5'); raise SystemExit(1)"
                )
                start = time.monotonic()
                res = await call(session, "batch_run", {"commands": [
                    {"argv": [sys.executable, "-c", snap_script], "label": "snapshot"},
                ], "cwd": str(repo)})
                assert time.monotonic() - start < 5
                snap_text = _text(res).replace("\r", "")
                for want in ("source now (> marks cited lines):", "src/fail.py:2-8", "> 5  v5 = 5"):
                    assert want in snap_text

                uni_name = chr(0x6570) + chr(0x636e) + ".py"
                uni_src = repo / "src" / uni_name
                uni_ign = repo / "ignored" / (chr(0x6570) + ".txt")
                uni_src.write_text("".join(f"w{n} = {n}\n" for n in range(1, 10)), encoding="utf-8")
                (repo / "ignored").mkdir(exist_ok=True)
                uni_ign.write_text("secret_row\n", encoding="utf-8")
                uni_script = (
                    "import sys; sys.stdout.reconfigure(encoding='utf-8'); "
                    "print('ignored/\\u6570.txt:1: x'); print('src/\\u6570\\u636e.py:5: boom'); raise SystemExit(1)"
                )
                try:
                    res = await call(session, "batch_run", {"commands": [
                        {"argv": [sys.executable, "-c", uni_script], "label": "short"},
                    ], "cwd": str(repo)})
                finally:
                    uni_src.unlink()
                    uni_ign.unlink()
                uni_text = _text(res).replace("\r", "")
                assert "source now (> marks cited lines):" in uni_text
                assert "src/" + uni_name + ":2-8" in uni_text
                assert "> 5  w5 = 5" in uni_text
                assert "secret_row" not in uni_text and "source lines dropped" not in uni_text

                (repo / "src" / "other.txt").write_bytes(b"o1\no2\no3\n")
                res = await call(session, "batch_edit", {
                    "edits": [{"path": "src/other.txt", "search": "o3", "replace": "o4"}],
                    "verify": {"argv": [sys.executable, "-c", "print('src/fail.py:5: boom'); raise SystemExit(1)"]},
                    "cwd": str(repo)})
                assert res.isError and "boom" in _text(res) and "source now" not in _text(res)

                lf = repo / "lf.txt"
                lf.write_bytes(b"one\n")
                res = await call(session, "batch_edit", {
                    "manifest": "diff --git a/lf.txt b/lf.txt\n--- a/lf.txt\n+++ b/lf.txt\n@@ -1 +1 @@\n-one\n+two\n",
                    "cwd": str(repo)})
                assert not res.isError
                assert lf.read_bytes().replace(b"\r\n", b"\n") == b"two\n"
                res = await call(session, "batch_edit", {
                    "edits": [{"path": "lf.txt", "search": "two", "replace": "three"}],
                    "verify": {"argv": [sys.executable, "-c", "raise SystemExit(1)"]},
                    "cwd": str(repo)})
                kept = _text(res).replace("\r", "").split("\n")
                assert res.isError and "-two" in kept and "+three" in kept
                assert lf.read_bytes().replace(b"\r\n", b"\n") == b"three\n"
                (repo / "mkeep.txt").write_bytes(b"m1\n")
                res = await call(session, "batch_edit", {
                    "manifest": "diff --git a/mkeep.txt b/mkeep.txt\n--- a/mkeep.txt\n+++ b/mkeep.txt\n@@ -1 +1 @@\n-m1\n+m2\n",
                    "verify": {"argv": [sys.executable, "-c", "raise SystemExit(1)"]}, "cwd": str(repo)})
                assert res.isError
                assert (repo / "mkeep.txt").read_bytes().replace(b"\r\n", b"\n") == b"m2\n"
                res = await call(session, "batch_edit", {
                    "edits": [{"path": "lf.txt", "search": "three", "replace": "four"}],
                    "verify": "git --version ||| count", "cwd": str(repo)})
                assert not res.isError
                res = await call(session, "batch_edit", {
                    "edits": [{"path": "lf.txt", "search": "four", "replace": "five"}],
                    "verify": {"cmd": "git --version ||| count"}, "cwd": str(repo)})
                assert not res.isError
                assert lf.read_bytes().replace(b"\r\n", b"\n") == b"five\n"
                for name, verify in (("split_verify.txt", "echo ran > split_verify.txt ||| b"),
                                     ("split_vobj.txt", {"cmd": "echo ran > split_vobj.txt ||| b"})):
                    res = await call(session, "batch_edit", {
                        "edits": [{"path": "lf.txt", "search": "five", "replace": "six"}],
                        "verify": verify, "cwd": str(repo)})
                    assert res.isError and "nothing ran" in _text(res)
                    assert lf.read_bytes().replace(b"\r\n", b"\n") == b"five\n"
                    assert not (repo / name).exists()
                res = await call(session, "batch_edit", {
                    "edits": [{"path": "lf.txt", "search": "five", "replace": "six"}],
                    "verify": {"cmd": "echo 'v ||| w' | tr '|' x", "slices": []}, "cwd": str(repo)})
                assert not res.isError
                assert lf.read_bytes().replace(b"\r\n", b"\n") == b"six\n"

                mcp_src = b"m1\nm2\n"
                (parts / "mcp_src.txt").write_bytes(mcp_src)
                res = await call(session, "batch_edit", {
                    "new_files": [{"path": "mcp_copy.txt", "content": [
                        file_part("mcp_src.txt", "2-2", hashlib.sha256(mcp_src).hexdigest()[:12])]}],
                    "cwd": str(parts)})
                assert not res.isError
                assert (parts / "mcp_copy.txt").read_bytes() == b"m2\n"

                # A path wrapped in quotes names the unquoted file; a failed write names its path and cause.
                res = await call(session, "batch_edit", {"new_files": {'"q/quoted.txt"': "q\n"}, "cwd": str(parts)})
                assert not res.isError, _text(res)
                assert (parts / "q" / "quoted.txt").read_bytes() == b"q\n"
                res = await call(session, "batch_edit", {"new_files": {"'sq.txt'": "s\n"}, "cwd": str(parts)})
                assert not res.isError, _text(res)
                assert (parts / "'sq.txt'").read_bytes() == b"s\n"
                res = await call(session, "batch_edit", {
                    "manifest": '<<<NEWFILE: "q/block.txt">>>\nb\n<<<END>>>\n', "cwd": str(parts)})
                assert not res.isError, _text(res)
                assert (parts / "q" / "block.txt").read_bytes() == b"b\n"
                (parts / "wf.txt").write_bytes(b"w\n")
                res = await call(session, "batch_edit", {
                    "edits": [{"path": "wf.txt", "search": "w", "replace": "x"}],
                    "new_files": {"wf.txt/child.txt": "c\n"}, "cwd": str(parts)})
                assert res.isError
                assert "write failed for wf.txt/child.txt: " in _text(res)
                assert "all changes were rolled back" in _text(res)
                assert (parts / "wf.txt").read_bytes() == b"w\n"

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
                    "verify": {"argv": [sys.executable, "-c", "raise SystemExit(1)"]},
                    "rollback_on_failure": True, "cwd": str(repo)})
                assert res.isError
                assert [(i["kind"], i["path"]) for i in _items(res) if i["kind"] != "verify"] == [("create", "copied.txt")]
                assert not (repo / "copied.txt").exists()

                edit = {"path": "notes.txt", "search": "old line", "replace": "new line"}
                res = await call(session, "batch_edit", {
                    "edits": [edit], "new_files": {"deep/er/made.txt": "x\n"},
                    "verify": {"argv": [sys.executable, "-c", "raise SystemExit(1)"]},
                    "rollback_on_failure": True, "cwd": str(repo)})
                assert res.isError
                assert "-old line" in _text(res).replace("\r", "").split("\n")
                assert notes.read_bytes() == b"keep\r\nold line\r\n"
                assert not (repo / "deep").exists()

                res = await call(session, "batch_edit", {
                    "new_files": {"deep2/made.txt": "x\n"},
                    "verify": {"argv": [sys.executable, "-c", "import pathlib; pathlib.Path('deep2/keep.txt').write_text('k'); raise SystemExit(1)"]},
                    "rollback_on_failure": True, "cwd": str(repo)})
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
                assert "+new line" not in edit_lines and "@@" not in _text(res)
                assert "1 replacement(s)" in _text(res) and "hash " in _text(res)

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
                    "edits": [{"path": "q.sql", "search": "-- old note\n", "replace": ""}],
                    "diff": "hunks", "cwd": str(repo)})
                assert not res.isError and sql.read_bytes() == b"select 1;\nselect 2;\n"
                sql_lines = _text(res).replace("\r", "").split("\n")
                assert "--- old note" in sql_lines and "--- a/q.sql" not in sql_lines

                res = await call(session, "batch_read", {"mode": "survey", "cwd": str(repo)})
                assert not res.isError
                text = _text(res).replace("\\", "/")
                assert re.match(r"# batch_read \(survey\) build [0-9a-f]{7}\n# Survey: ", text)
                assert re.search(r"M notes\.txt \+\d+ -\d+", text) and "Diff stat" not in text
                survey_text = text.replace("\r", "")
                assert "  .github/workflows/ci.yml:\n    pytest -q\n    ruff check . (+2 more lines)\n    deploy --env prod --fast\n" in survey_text
                assert "  Makefile: make build, make test, make lint\n" in survey_text
                assert "  package.json scripts:\n    test: vitest run\n    build: tsc\n" in survey_text
                assert "make VAR" not in survey_text and "make deps" not in survey_text and "cc -o" not in survey_text
                res = await call(session, "batch_read", {"mode": "survey", "cwd": str(repo / "src")})
                assert "package.json: scripts not read (invalid JSON)" in _text(res)
                assert "Makefile: targets not read (over 1 MB)" in _text(res) and "make fallback" not in _text(res)
                res = await call(session, "batch_read", {"mode": "survey", "cwd": str(repo / "hits")})
                assert "notes.txt" not in _text(res) and "Commands (" not in _text(res)

                res = await call(session, "batch_read", {
                    "mode": "survey", "specs": ["later.txt", "grep:zz_absent_zz"], "cwd": str(repo)})
                text = _text(res).replace("\\", "/")
                assert re.match(r"# batch_read \(survey\) build [0-9a-f]{7}\n# Survey: ", text)
                assert "\n# batch_read (files) build " in text.partition("# Survey: ")[2]
                assert "[R1] ok later.txt" in text
                assert [i["status"] for i in _items(res)] == ["ok", "no_match"]
                res = await call(session, "batch_read", {
                    "mode": "survey", "focus": ["src/a.txt"], "cwd": str(repo)})
                text = _text(res).replace("\\", "/").replace("\r", "")
                focus_text = text.partition("\nFocus ['src/a.txt']: 1 match(es)\n")[2]
                assert re.search(
                    r"Focus recent commits \(newest 5 touching a match\):\n  [0-9a-f]{7,} \d{4}-\d{2}-\d{2} fixture\n",
                    focus_text)
                assert "  1x .github/workflows/ci.yml\n" in focus_text
                assert "Focus related tests:\n  tests/a_test.py\n  tests/test_misc.py\n" in focus_text
                assert "later" not in focus_text
                assert not re.search(r"(?m)^ +\d+x [0-9a-f]{7,} ", text)
                res = await call(session, "batch_read", {
                    "mode": "survey", "focus": ["tests/a_test.py"], "cwd": str(repo)})
                text = _text(res)
                assert "Focus history: no commit in the newest 200 touches a match" in text
                assert "Focus related tests:" not in text

                kept_code = (
                    "import os, sys; [print('{\"n\": \"%s\"}' % n) for n in os.environ['KEPT_N'].split(',')]; "
                    "sys.stderr.write(os.environ.get('KEPT_ERR', ''))  # kept-cmd"
                )

                def kept(values, err=""):
                    return {"argv": [sys.executable, "-c", kept_code], "label": "kept",
                            "env": {"KEPT_N": values, "KEPT_ERR": err}}

                passing = {"argv": [sys.executable, "-c", "print(1)"], "label": "gone"}
                res = await call(session, "batch_run", {"commands": [kept("beta-v1,alpha-v1", "warn1"), passing],
                                                         "cwd": str(repo)})
                assert not res.isError
                res = await call(session, "batch_read", {
                    "specs": ["artifact:kept ||| json:n ||| sort", "artifact:kept.stderr", "artifact:gone"],
                    "cwd": str(repo)})
                text = _text(res).replace("\r", "")
                assert [i["status"] for i in _items(res)] == ["ok", "ok", "ok"]
                assert "alpha-v1\nbeta-v1" in text and "warn1" in text
                assert "ago from: " in text and "kept-cmd" in text

                res = await call(session, "batch_read", {
                    "specs": [{"grep": "needle_token", "paths": ["src"], "label": "gr_tok"},
                              {"glob": "src/*.txt", "label": "gl_txt"},
                              {"grep": "needle_token", "paths": [str(tmp_path)], "label": "kept.stderr"},
                              {"grep": "needle_census", "paths": ["hits"], "max_matches": 5, "label": "gr_cut"}],
                    "cwd": str(repo)})
                assert [i["status"] for i in _items(res)] == ["ok", "ok", "error", "ok"]
                res = await call(session, "batch_read", {
                    "specs": ["artifact:gr_tok", "artifact:gl_txt", "artifact:kept.stderr",
                              "artifact:gr_cut ||| grep:\\(10\\)$ ||| count",
                              "artifact:gr_cut ||| grep:needle_census ||| count"],
                    "cwd": str(repo)})
                text = _text(res).replace("\\", "/")
                assert "needle_token here" in text and "a.txt" in text
                assert "warn1" in text  # an invalid label never unbinds the runner's .stderr alias
                assert re.search(r"(?m)^30$", text)  # a cut grep keeps every file's count
                assert re.search(r"(?m)^5$", text)  # and only the rows within max_matches
                res = await call(session, "batch_read", {
                    "specs": [{"grep": "needle_token", "paths": [str(tmp_path)], "label": "gr_tok"}],
                    "cwd": str(repo)})
                assert _items(res)[0]["status"] == "error"
                res = await call(session, "batch_read", {"specs": ["artifact:gr_tok"], "cwd": str(repo)})
                assert _items(res)[0]["status"] == "missing"  # a labelled read that kept nothing drops its old result

                res = await call(session, "batch_run", {
                    "commands": [kept("gamma-v2"), {**passing, "cwd": "no_such_dir"}], "cwd": str(repo)})
                assert res.isError  # the setup error
                res = await call(session, "batch_read", {
                    "specs": ["artifact:kept ||| json:n", "artifact:kept.stderr", "artifact:gone"],
                    "cwd": str(repo)})
                text = _text(res)
                assert [i["status"] for i in _items(res)] == ["ok", "missing", "missing"]
                assert "gamma-v2" in text and "alpha-v1" not in text and "warn1" not in text
                res = await call(session, "batch_read", {"specs": ["artifact:kept"], "cwd": str(repo / "src")})
                assert _items(res)[0]["status"] == "missing"

                assert sum(len(json.dumps(t.inputSchema)) + len(t.description or "") for t in tools.tools) <= 5600

        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), 20)
                res = await call(session, "batch_read", {"specs": ["artifact:kept ||| json:n"], "cwd": str(repo)})
                assert "gamma-v2" in _text(res) and "alpha-v1" not in _text(res)

    asyncio.run(asyncio.wait_for(session_run(), 40))

    # The guard Provision installs beside the server refuses native tools only while batch-ops is
    # connected, and never strands a subagent, a path outside the project, or a disconnected session.
    # The checks run the hooks as the references document them, in a non-ASCII project whose own
    # json.py must never load.
    project = tmp_path / "guardé"
    project.mkdir()
    (project / "json.py").write_text('raise SystemExit("project json.py imported")\n', encoding="utf-8")
    references = ROOT / "skills" / "workbench" / "provision" / "references"
    lines = (references / "batch-ops.md").read_text(encoding="utf-8").splitlines()
    after = next(i for i, line in enumerate(lines) if line.startswith("6. **Guard.**"))
    fence = next(i for i in range(after, len(lines)) if lines[i].strip() == "```text")
    launcher = lines[fence + 1].strip()

    def hook(name):
        text = (references / name).read_text(encoding="utf-8")
        line = next(line for line in text.splitlines() if line.startswith("- **Guard:**"))
        return json.loads(re.search(r'`(\{"matcher"[^`]*)`', line).group(1))["hooks"][0]

    claude_hook, codex_hook = hook("claude-code.md"), hook("codex.md")
    transcript = tmp_path / "session.jsonl"

    def delta(change):
        attachment = {"type": "mcp_instructions_delta", change: ["batch-ops"]}
        return json.dumps({"type": "attachment", "attachment": attachment}) + "\n"

    def guard(tool_input, tool="Read", codex=False, guard_path=GUARD, **extra):
        event = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input,
                 "cwd": str(project), "transcript_path": str(transcript), "permission_mode": "default", **extra}

        def fill(text):
            return text.replace("<python>", sys.executable).replace("<launcher>", launcher).replace("<guard>", str(guard_path))

        run = {"input": json.dumps(event, ensure_ascii=False).encode("utf-8"), "capture_output": True,
               "cwd": project, "env": {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}, "timeout": 30}
        if codex:
            done = subprocess.run(fill(codex_hook["command"]), shell=True, **run)
        else:
            done = subprocess.run([fill(claude_hook["command"]), *map(fill, claude_hook["args"])], **run)
        stdout, stderr = done.stdout.decode("utf-8"), done.stderr.decode("utf-8")
        assert done.returncode == 0 and not stderr
        return json.loads(stdout)["hookSpecificOutput"] if stdout else None

    inside = {"file_path": str(project / "a.txt")}
    assert guard(inside) is None  # no transcript yet: what it cannot read allows the call
    transcript.write_text(delta("addedNames"), encoding="utf-8")
    refused = guard(inside)
    assert refused["permissionDecision"] == "deny"
    assert "mcp__batch-ops__batch_read" in refused["permissionDecisionReason"]
    assert guard({"command": "git status"}, tool="Bash")["permissionDecision"] == "deny"
    assert guard(inside, agent_id="sub") is None  # subagents keep native tools
    assert guard({"file_path": str(tmp_path / "outside.txt")}) is None
    assert guard({"file_path": str(project / "shot.PNG")}) is None  # media keeps the native reader
    assert guard({"command": "git status", "run_in_background": True}, tool="Bash") is None
    moved = tmp_path / "moved" / "batch_ops_guard.py"  # a removed guard must not refuse every tool
    assert guard(inside, guard_path=moved) is None
    assert guard({"command": "git status"}, tool="Bash", codex=True, guard_path=moved) is None
    with transcript.open("a", encoding="utf-8") as stream:
        stream.write(delta("removedNames"))
    assert guard(inside) is None  # a disconnect lifts the guard
    # Codex hooks see no connections, so its guard refuses the shell regardless, but not patches elsewhere.
    assert guard({"command": "git status"}, tool="Bash", codex=True)["permissionDecision"] == "deny"
    elsewhere = f"*** Begin Patch\n*** Add File: {tmp_path / 'x.txt'}\n+x\n*** End Patch"
    assert guard({"command": elsewhere}, tool="apply_patch", codex=True) is None

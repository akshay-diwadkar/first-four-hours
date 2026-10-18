from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tools.validation.python_test_support import run_python

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "skills" / "workbench" / "pr" / "scripts"
CLI = SCRIPTS / "cli.py"

APP_BASE = "def hello():\n    return 'hi'\n"
APP_HEAD = (
    "# Greeting text lives in config/settings.toml.\n"
    "def hello():\n    return 'hi'\n\n\n"
    "def greet(name):\n    return 'hi ' + name\n"
)

GOOD = """## Why

Adds `src/app.py::greet` so callers can greet by name, and removes `old/legacy.py::legacy`.

## Reading guide

Start at `src/app.py`; `src/util.py:1` is unchanged context, [the settings](config/settings.toml) hold the
greeting, the `read/write` split is unchanged, `os.path` is untouched, and `HTTP/1.1` is unaffected.

```mermaid
---
title: Step1>Step2
---
flowchart LR
    accDescr {
        Callers reach greet (by name
    }
    caller["caller"] --> greet["src/app.py::greet"]
    subgraph helpers
        helper["src/util.py"]
    end
    greet --> helper
    greet --> done([done])
    done --> sub[[sub]]
    sub --> store[(cache)]
    store --> note>note]
    note --> cmp[size>0]
    cmp --> big[file size>0]
    big --> gen[Map<String, Integer>]
    gen -- a>b --> fin
    fin--c>d-->last
```

## Verification

- Ran: `{passed}` and it exited 0.
- Not verified: non-ASCII names.
"""

BAD = """## Why

Adds `src/app.py::greet`, replaces `src/missing.py:10`, follows [the guide](docs/guide.md), updates
`CONTRIBUTING.md`, and keeps `src/app.py::farewell`; `src/util.py` stays and the `read/write` split is unchanged.

```Mermaid
flowchart LR
    a --> b
```

```mermaid
graphviz LR
    a --> b
```

```mermaid
flowchart LR
    a --> b[unclosed
```

```mermaid
flowchart TD
    a["src/phantom.py"] --> b
    subgraph inner
        b --> c
```

```mermaid
flowchart LR
    x-->y>oops-->z
```

```mermaid
flowchart LR
    accDescr {
    a --> b
```

```mermaid
flowchart LR
    a -- "open --> b
```

```mermaid
sequenceDiagram
    loop every call
        A->>B: greet
```

```git push``` was not run, so the claims below must still be checked.

## Verification

- Ran: `python -m pytest`
- Ran: `{failed}`
- Ran: `{stale}` covering `src/ghost.py`
- Ran: `{dirty}`
1. Ran: pytest on `src/nowhere.py`, all passed
- [x] Ran: `ruff check`
> Ran: `mypy .`
- [ ] Ran: ruff format, clean

```mermaid
flowchart LR
    a --> b
"""


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-c", "user.name=PR Test", "-c", "user.email=pr@example.invalid", *args],
        cwd=repo, capture_output=True, encoding="utf-8", check=True,
    ).stdout


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _repo(tmp_path: Path) -> Path:
    """main holds five files; feature changes src/app.py and deletes old/legacy.py."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _write(repo / "src" / "app.py", APP_BASE)
    _write(repo / "src" / "util.py", "def helper():\n    return 1\n")
    _write(repo / "config" / "settings.toml", "greeting = 'hi'\n")
    _write(repo / "docs" / "guide.md", "# Guide\n")
    _write(repo / "old" / "legacy.py", "def legacy():\n    pass\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "checkout", "-q", "-b", "feature")
    _write(repo / "src" / "app.py", APP_HEAD)
    _git(repo, "rm", "-q", "old/legacy.py")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feature")
    return repo


def _cli(repo: Path, command: str, *inputs: str) -> tuple[int, dict]:
    argv = [sys.executable, str(CLI), "--repo-root", str(repo)]
    for value in inputs:
        argv += ["--input", value]
    result = run_python([*argv, "--format", "json", command], capture_output=True, text=True, check=False)
    return result.returncode, json.loads(result.stdout)


def _record(repo: Path, runs: Path, *argv: str) -> dict:
    code, envelope = _cli(repo, "record", f"runs={runs}", *(f"arg={value}" for value in argv))
    assert code == 0, envelope
    return envelope["result"]


def test_grounded_description_passes_check(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    runs = tmp_path / "runs.jsonl"
    recorded = _record(repo, runs, sys.executable, "-c", "pass")
    head = _git(repo, "rev-parse", "HEAD").strip()
    assert (recorded["exit_code"], recorded["head"], recorded["clean"]) == (0, head, True), recorded
    draft = tmp_path / "draft.md"
    _write(draft, GOOD.replace("{passed}", recorded["command"]))
    code, envelope = _cli(repo, "check", f"draft={draft}", f"runs={runs}", "base=main")
    assert code == 0, envelope
    assert envelope["result"] == {
        "status": "checked",
        "head": head,
        "body_sha256": hashlib.sha256(draft.read_bytes()).hexdigest(),
    }, envelope
    assert _git(repo, "status", "--porcelain", "--untracked-files=all") == ""


def test_ungrounded_description_is_rejected_with_repairs(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    runs = tmp_path / "runs.jsonl"
    failed = _record(repo, runs, sys.executable, "-c", "raise SystemExit(3)")
    assert failed["exit_code"] == 3, failed
    stale = _record(repo, runs, sys.executable, "-c", "print(1)")["command"]
    _write(repo / "src" / "app.py", APP_HEAD + "\n\ndef wave():\n    return 'bye'\n")
    _git(repo, "commit", "-q", "-am", "later")
    # A run recorded at the current HEAD on a dirty worktree is not trusted either.
    (repo / "scratch.txt").write_text("wip\n", encoding="utf-8")
    dirty = _record(repo, runs, sys.executable, "-c", "print(2)")
    assert dirty["clean"] is False, dirty
    (repo / "scratch.txt").unlink()
    draft = tmp_path / "draft.md"
    _write(
        draft,
        BAD.replace("{failed}", failed["command"]).replace("{stale}", stale).replace("{dirty}", dirty["command"]),
    )
    code, envelope = _cli(repo, "check", f"draft={draft}", f"runs={runs}", "base=main")
    assert code != 0, envelope
    # Valid citations (`src/app.py::greet`, sibling `src/util.py`) and the non-path `read/write` are not flagged.
    assert set(envelope["blocking_reasons"]) == {
        "pr.citation_missing",
        "pr.citation_out_of_scope",
        "pr.symbol_missing",
        "pr.verification_unrecorded",
        "pr.verification_failed",
        "pr.verification_stale",
        "pr.verification_malformed",
        "pr.mermaid_fence",
        "pr.mermaid_type",
        "pr.mermaid_syntax",
    }, envelope
    messages = " ".join(item["message"] for item in envelope["diagnostics"])
    for token in (
        "src/missing.py", "docs/guide.md", "CONTRIBUTING.md", "farewell", "src/ghost.py", "src/nowhere.py",
        "src/phantom.py", "ruff check", "mypy .",
    ):
        assert token in messages, messages
    assert all(item["required_action"] for item in envelope["diagnostics"]), envelope
    # An unclosed `subgraph`, an unclosed bracket, a broken node between chained arrows, an unclosed `accDescr {`,
    # an unclosed quote, and a sequence `loop` without `end`.
    assert [item["code"] for item in envelope["diagnostics"]].count("pr.mermaid_syntax") == 6, envelope
    assert [item["code"] for item in envelope["diagnostics"]].count("pr.verification_malformed") == 2, envelope
    # The `Mermaid` info mismatch and the unclosed mermaid block that ends the draft.
    assert [item["code"] for item in envelope["diagnostics"]].count("pr.mermaid_fence") == 2, envelope
    stale_messages = " ".join(
        item["message"] for item in envelope["diagnostics"] if item["code"] == "pr.verification_stale"
    )
    assert dirty["command"] in stale_messages and stale in stale_messages, stale_messages


def _load_publish():
    spec = importlib.util.spec_from_file_location("pr_publish_under_test", SCRIPTS / "publish_pr.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_publish_requires_confirmed_text_and_pushed_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    runs = tmp_path / "runs.jsonl"
    recorded = _record(repo, runs, sys.executable, "-c", "pass")
    draft = tmp_path / "draft.md"
    text = GOOD.replace("{passed}", recorded["command"])
    _write(draft, text)
    code, checked = _cli(repo, "check", f"draft={draft}", f"runs={runs}", "base=main")
    assert code == 0, checked
    confirmed = checked["result"]["body_sha256"]
    monkeypatch.setattr(sys, "path", list(sys.path))
    publish = _load_publish()
    calls: list[list[str]] = []

    def fake_gh(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "https://github.com/acme/widget/pull/7\n", "")

    monkeypatch.setattr(publish, "run_gh", fake_gh)

    def run(confirm: str, base: str = "main") -> tuple[int, Any]:
        code = publish.main([
            "--repo-root", str(repo), "--draft", str(draft), "--runs", str(runs),
            "--base", base, "--title", "Greet callers by name", "--confirm", confirm,
        ])
        return code, json.loads(capsys.readouterr().out)

    # Unconfirmed text on a branch with no upstream opens nothing.
    code, out = run("0" * 64)
    assert code == 1 and {item["code"] for item in out} == {"pr.publish_unconfirmed", "pr.branch_unpushed"}, out
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-q", "-u", "origin", "feature")
    # A draft edited after the user confirmed it is no longer the confirmed text.
    _write(draft, text + "\nOne more line.\n")
    code, out = run(confirmed)
    assert code == 1 and [item["code"] for item in out] == ["pr.publish_unconfirmed"], out
    assert calls == []
    _write(draft, text)
    # An upstream that exists but sits behind HEAD opens nothing.
    _write(repo / "src" / "app.py", APP_HEAD + "# tidy\n")
    _git(repo, "commit", "-q", "-am", "tidy")
    _record(repo, runs, sys.executable, "-c", "pass")
    code, out = run(confirmed)
    assert code == 1 and [item["code"] for item in out] == ["pr.branch_unpushed"], out
    assert calls == []
    _git(repo, "push", "-q")
    # A base on a different remote than the pushed upstream is a fork PR, which opens nothing.
    _git(repo, "remote", "add", "upstream", str(remote))
    _git(repo, "push", "-q", "upstream", "main")
    _git(repo, "fetch", "-q", "upstream")
    code, out = run(confirmed, "upstream/main")
    assert code == 1 and [item["code"] for item in out] == ["pr.branch_unpushed"], out
    assert "fork PRs are not supported" in out[0]["message"], out
    assert calls == []
    code, out = run(confirmed)
    assert code == 0, out
    assert out == {"status": "opened", "url": "https://github.com/acme/widget/pull/7"}
    assert calls == [[
        "gh", "pr", "create", "--base", "main", "--head", "feature",
        "--title", "Greet callers by name", "--body-file", str(draft.resolve()),
    ]]

#!/usr/bin/env python3
"""Provider-free proof of Ticket's local Markdown persistence through the public flow."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from tools.validation.python_test_support import run_python

ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "skills" / "workbench" / "ticket" / "scripts" / "cli.py"
MARKER = "<!-- ticket-item: "
EPIC: dict[str, Any] = {
    "backend": "local",
    "local_store": "backlog",
    "shape": "epic",
    "epic_id": "auth",
    "task": {"text": "Ship auth."},
    "work_items": [
        {"id": "login", "outcome": "Users log in."},
        {"id": "logout", "outcome": "Users log out.", "dependencies": ["login"]},
    ],
}
SINGLE: dict[str, Any] = {
    "backend": "local",
    "local_store": "backlog",
    "shape": "single",
    "task": {"text": "Add token refresh."},
    "work_items": [{"id": "refresh", "outcome": "Expired tokens refresh automatically."}],
}


def cli(repo: Path, run: Path, command: str, *inputs: str) -> tuple[int, dict[str, Any]]:
    argv = [sys.executable, str(CLI), "--repo-root", str(repo), "--run-dir", str(run), "--format", "json"]
    for value in inputs:
        argv += ["--input", value]
    # No gh executable is reachable, so any GitHub access would fail the flow.
    env = {**os.environ, "PATH": ""}
    result = run_python([*argv, command], capture_output=True, text=True, check=False, env=env)
    return result.returncode, json.loads(result.stdout)


def persist(tmp: Path, repo: Path, name: str, payload: dict[str, Any], *, confirm: bool = True) -> tuple[int, dict[str, Any]]:
    source = tmp / f"{name}.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    code, out = cli(repo, tmp / name, "start", "backend=local", f"persist_input={source}")
    assert code == 0 and out["phase"] == "approval-required", out
    code, out = cli(repo, tmp / name, "next")
    if code or not confirm:
        return code, out
    assert out["phase"] == "publication-ready", out
    return cli(repo, tmp / name, "next", "publish_confirmation=yes")


def result(tmp: Path, name: str) -> dict[str, Any]:
    return json.loads((tmp / name / "publication-result.json").read_text(encoding="utf-8"))


def meta(path: Path) -> dict[str, Any]:
    first = path.read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith(MARKER) and first.endswith(" -->"), first
    return json.loads(first[len(MARKER) : -len(" -->")])


def test_local_persist_publishes_resumes_and_blocks_conflicts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    store = repo / "backlog"

    code, out = persist(tmp_path, repo, "first", EPIC, confirm=False)
    assert code == 0 and out["phase"] == "publication-ready", out
    reviewed = json.loads((tmp_path / "first" / "reconciliation.json").read_text(encoding="utf-8"))
    assert [(item["id"], item["action"]) for item in reviewed["records"]] == [
        ("auth", "create"),
        ("login", "create"),
        ("logout", "create"),
    ]
    assert not store.exists()

    # Saved run state from another protocol minor resumes; another major is refused without writes.
    state_path = tmp_path / "first" / ".skill-cli-state.json"
    saved = json.loads(state_path.read_text(encoding="utf-8"))

    def restamp(version: str) -> None:
        body = {key: value for key, value in saved.items() if key != "state_sha256"} | {"protocol_version": version}
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        state_path.write_text(json.dumps({**body, "state_sha256": digest}), encoding="utf-8")

    restamp("2.0.0")
    code, out = cli(repo, tmp_path / "first", "next", "publish_confirmation=yes")
    assert code != 0 and out["diagnostics"][0]["code"] == "state.identity_mismatch", out
    assert not store.exists()
    restamp("1.3.0")

    code, out = cli(repo, tmp_path / "first", "next", "publish_confirmation=yes")
    assert code == 0 and out["phase"] == "complete", out
    first = result(tmp_path, "first")
    assert first["anchor"] == "auth"
    assert [(item["id"], item["outcome"], item["path"]) for item in first["records"]] == [
        ("auth", "created", "backlog/auth.md"),
        ("login", "created", "backlog/login.md"),
        ("logout", "created", "backlog/logout.md"),
    ]
    assert sorted(path.name for path in store.iterdir()) == ["auth.md", "login.md", "logout.md"]
    root, login, logout = (meta(store / f"{name}.md") for name in ("auth", "login", "logout"))
    assert (root["kind"], root["parent"], root["depends_on"]) == ("epic", None, [])
    assert (login["kind"], login["state"], login["parent"], login["depends_on"]) == ("issue", "open", "auth", [])
    assert (logout["parent"], logout["depends_on"]) == ("auth", ["login"])
    assert "# Users log out." in (store / "logout.md").read_text(encoding="utf-8")

    lines = (store / "login.md").read_text(encoding="utf-8").splitlines(keepends=True)
    lines[0] = MARKER + json.dumps({**login, "state": "closed", "parent": None}) + " -->\n"
    (store / "login.md").write_text("".join(lines) + "\nHuman note.\n", encoding="utf-8")
    preserved = (store / "login.md").read_bytes()
    interrupted = (store / "logout.md").read_bytes()
    (store / "auth.md").unlink()
    (store / "logout.md").unlink()

    code, out = persist(tmp_path, repo, "second", EPIC, confirm=False)
    assert code == 0 and out["phase"] == "publication-ready", out
    (store / "logout.md").write_bytes(interrupted)
    code, out = cli(repo, tmp_path / "second", "next", "publish_confirmation=yes")
    assert code == 0 and out["phase"] == "complete", out
    assert [(item["id"], item["outcome"], item["relations_changed"]) for item in result(tmp_path, "second")["records"]] == [
        ("auth", "created", False),
        ("login", "existing", True),
        ("logout", "existing", False),
    ]
    assert (store / "login.md").read_bytes() == preserved
    assert (store / "logout.md").read_bytes() == interrupted
    assert meta(store / "auth.md") == root

    code, out = persist(tmp_path, repo, "drift", EPIC, confirm=False)
    assert code == 0 and out["phase"] == "publication-ready", out
    held = (store / "auth.md").read_bytes()
    (store / "auth.md").unlink()
    code, out = cli(repo, tmp_path / "drift", "next", "publish_confirmation=yes")
    assert code != 0 and "persist.local_plan_drift" in out["blocking_reasons"], out
    assert not (store / "auth.md").exists()
    takeover = {**EPIC, "work_items": [{"id": "signup", "outcome": "Users sign up."}, {"id": "reset", "outcome": "Users reset passwords."}]}
    code, out = persist(tmp_path, repo, "takeover", takeover)
    assert code != 0 and "persist.local_record_conflict" in out["blocking_reasons"], out
    assert not any((store / f"{name}.md").exists() for name in ("auth", "signup", "reset"))
    (store / "auth.md").write_bytes(held)

    edited = json.loads(json.dumps(EPIC))
    edited["work_items"][0]["outcome"] = "Users sign in."
    (store / "Refresh.md").write_text("Unmanaged notes.\n", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in store.iterdir()}
    code, out = persist(tmp_path, repo, "third", edited)
    assert code != 0 and "persist.local_record_conflict" in out["blocking_reasons"], out
    assert {path.name: path.read_bytes() for path in store.iterdir()} == before
    code, out = persist(tmp_path, repo, "fourth", SINGLE)
    assert code != 0 and "persist.local_record_conflict" in out["blocking_reasons"], out
    assert {path.name: path.read_bytes() for path in store.iterdir()} == before
    foreign = {**EPIC, "epic_id": "accounts", "work_items": [EPIC["work_items"][0], {"id": "signup", "outcome": "Users sign up."}]}
    code, out = persist(tmp_path, repo, "foreign", foreign)
    assert code != 0 and "persist.local_record_conflict" in out["blocking_reasons"], out
    assert {path.name: path.read_bytes() for path in store.iterdir()} == before
    (store / "Refresh.md").unlink()

    unsafe = tmp_path / "unsafe.json"
    unsafe_items = [{"id": "ticket-scope", "outcome": "Shadow the scope handoff."}]
    unsafe.write_text(json.dumps({**SINGLE, "local_store": "../outside", "work_items": unsafe_items}), encoding="utf-8")
    code, out = cli(repo, tmp_path / "unsafe", "start", "backend=local", f"persist_input={unsafe}")
    assert code != 0, out
    assert {"persist.bad_local_store", "persist.bad_local_id"} <= set(out["blocking_reasons"]), out
    device = tmp_path / "device.json"
    # The store never sits inside the ignored artifact folder.
    device_input = {**SINGLE, "local_store": ".first-four-hours/ticket-scopes/backlog", "work_items": [{"id": "aux", "outcome": "Unclonable on Windows."}]}
    device.write_text(json.dumps(device_input), encoding="utf-8")
    code, out = cli(repo, tmp_path / "device", "start", "backend=local", f"persist_input={device}")
    assert code != 0 and set(out["blocking_reasons"]) == {"persist.bad_local_store", "persist.bad_local_id"}, out

    code, out = persist(tmp_path, repo, "fifth", SINGLE, confirm=False)
    assert code == 0 and out["phase"] == "publication-ready", out
    code, out = cli(repo, tmp_path / "fifth", "next", "label=triage", "publish_confirmation=yes")
    assert code != 0 and "persist.local_input_unsupported" in out["blocking_reasons"], out
    assert not (store / "refresh.md").exists()

    code, out = persist(tmp_path, repo, "sixth", SINGLE)
    assert code == 0 and out["phase"] == "complete", out
    assert result(tmp_path, "sixth")["anchor"] == "refresh"
    assert (meta(store / "refresh.md")["kind"], meta(store / "refresh.md")["parent"]) == ("issue", None)

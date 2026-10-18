#!/usr/bin/env python3
"""Focused provider-free proof of Ticket's confirmed GitHub publication."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "workbench" / "ticket" / "scripts"
sys.path.insert(0, str(SCRIPTS))
for _name in ("reconcile_github", "publish_github"):
    _spec = importlib.util.spec_from_file_location(_name, SCRIPTS / f"{_name}.py")
    assert _spec and _spec.loader
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = _module
    _spec.loader.exec_module(_module)
rg = sys.modules["reconcile_github"]
pg = sys.modules["publish_github"]

from compile_persist import render_preview  # noqa: E402
from github_common import GitHubError

REPO = "/repos/acme/widget"
EPIC: dict[str, Any] = {
    "backend": "github",
    "github_repo_url": "acme/widget",
    "shape": "epic",
    "task": {"text": "Ship auth."},
    "work_items": [
        {"id": "login", "outcome": "Users log in."},
        {"id": "logout", "outcome": "Users log out.", "dependencies": ["login"]},
    ],
}
EPIC_DECISIONS = {
    "epic": {"action": "reuse", "issue": 5, "basis": "#5 is the auth epic."},
    "items": {
        "login": {"action": "reuse", "issue": 2, "basis": "#2 is the login work."},
        "logout": {
            "action": "create",
            "basis": "New logout work.",
            "search": {"terms": ["log out"], "limit": 5},
            "candidates": {"8": {"classification": "different", "basis": "#8 tracks a mobile logout bug."}},
        },
    },
}


def repo_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": 1,
        "full_name": "acme/widget",
        "has_issues": True,
        "archived": False,
        "disabled": False,
        "permissions": {"push": True},
    }
    payload.update(overrides)
    return payload


def issue(number: int, *, title: str | None = None, body: str = "", labels: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "number": number,
        "id": 1000 + number,
        "node_id": f"I_{number}",
        "repository_url": "https://api.github.com/repos/acme/widget",
        "html_url": f"https://github.com/acme/widget/issues/{number}",
        "title": title if title is not None else f"Issue {number}",
        "body": body,
        "state": "open",
        "state_reason": None,
        "labels": [{"name": name} for name in labels],
    }


class Crash(Exception):
    """A process death between a write and its recorded outcome."""


class FakeGitHub:
    """Stateful fake: reads serve routes; writes apply to the routes their readback uses."""

    def __init__(
        self,
        routes: dict[str, Any],
        *,
        fail: dict[str, Exception] | None = None,
        lost: dict[str, Exception] | None = None,
    ) -> None:
        self.routes = copy.deepcopy(routes)
        self.fail = fail or {}
        self.lost = lost or {}
        self.preflight_error: Exception | None = None
        self.calls: list[str] = []
        self.writes: list[tuple[str, dict[str, Any]]] = []
        self.next_number = 40
        self.search_items: list[dict[str, Any]] = []
        self.search_incomplete = False

    def preflight(self) -> None:
        self.calls.append("preflight")
        if self.preflight_error is not None:
            raise self.preflight_error

    def request(self, method: str, path: str) -> Any:
        assert method == "GET"
        self.calls.append(path)
        if path.startswith("/search/issues?"):
            items = copy.deepcopy(self.search_items)
            return {"total_count": len(items), "incomplete_results": self.search_incomplete, "items": items}
        if path.startswith(f"{REPO}/issues?"):
            listed = [value for key, value in self.routes.items() if re.fullmatch(rf"{REPO}/issues/\d+", key)]
            return copy.deepcopy(sorted(listed, key=lambda value: -value["number"]))
        if path.endswith("/dependencies/blocked_by"):
            return copy.deepcopy(self.routes.get(path, []))
        if path not in self.routes:
            raise GitHubError(f"GitHub API GET {path} failed: 1 HTTP 404", status=404)
        return copy.deepcopy(self.routes[path])

    def paginated_get(self, path: str, *, item_limit: int | None = None) -> list[dict[str, Any]]:
        value = self.request("GET", path)
        assert isinstance(value, list)
        return value

    def _by_id(self, issue_id: int) -> dict[str, Any]:
        return next(value for key, value in self.routes.items() if re.fullmatch(rf"{REPO}/issues/\d+", key) and value["id"] == issue_id)

    def mutate(self, method: str, path: str, payload: dict[str, Any]) -> Any:
        """Apply one write; ``fail`` raises before applying, ``lost`` (created title or path) raises after applying."""

        assert method == "POST"
        self.calls.append(f"POST {path}")
        self.writes.append((path, copy.deepcopy(payload)))
        if path in self.fail:
            raise self.fail.pop(path)
        if path == f"{REPO}/issues":
            self.next_number += 1
            created = issue(self.next_number, title=payload["title"], body=payload["body"], labels=tuple(payload["labels"]))
            self.routes[f"{REPO}/issues/{self.next_number}"] = created
            key, result = payload["title"], copy.deepcopy(created)
        else:
            number = int(path.split("/")[5])
            key, result = path, copy.deepcopy(self.routes[f"{REPO}/issues/{number}"])
            if path.endswith("/labels"):
                current = self.routes[f"{REPO}/issues/{number}"]
                current["labels"] += [{"name": name} for name in payload["labels"]]
                result = copy.deepcopy(current["labels"])
            elif path.endswith("/sub_issues"):
                child = self._by_id(payload["sub_issue_id"])
                self.routes[f"{REPO}/issues/{child['number']}/parent"] = copy.deepcopy(self.routes[f"{REPO}/issues/{number}"])
                self.routes.setdefault(f"{REPO}/issues/{number}/sub_issues", []).append(copy.deepcopy(child))
            else:
                assert path.endswith("/dependencies/blocked_by")
                self.routes.setdefault(path, []).append(copy.deepcopy(self._by_id(payload["issue_id"])))
        if key in self.lost:
            raise self.lost.pop(key)
        return result


class Run:
    def __init__(self, root: Path, persist: dict[str, Any], decisions: dict[str, Any]) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.persist = root / "persist-input.json"
        self.preview = root / "preview.json"
        self.input = root / "reconciliation-input.json"
        self.reconciliation = root / "reconciliation.json"
        self.output = root / "publication-result.json"
        self.persist.write_text(json.dumps(persist), encoding="utf-8")
        text, diagnostics = render_preview(persist)
        assert text is not None, diagnostics
        self.preview.write_bytes(text.encode("utf-8"))
        payload = {"version": "1.0.0", "preview_sha256": hashlib.sha256(self.preview.read_bytes()).hexdigest(), **decisions}
        self.input.write_text(json.dumps(payload), encoding="utf-8")

    def common(self, backend: str, labels: tuple[str, ...]) -> list[str]:
        argv = ["--backend", backend, "--github-repo", "acme/widget"]
        for label in labels:
            argv += ["--label", label]
        return argv + [
            "--persist-input",
            str(self.persist),
            "--preview",
            str(self.preview),
            "--reconciliation-input",
            str(self.input),
        ]

    def reconcile(self, capsys, github: FakeGitHub, labels: tuple[str, ...] = ()) -> dict[str, Any]:
        capsys.readouterr()
        rc = rg.main(["build", *self.common("github", labels), "--output", str(self.reconciliation)], client_factory=lambda: github)
        assert rc == 0, capsys.readouterr().out
        return json.loads(self.reconciliation.read_text(encoding="utf-8"))

    def publish(
        self, capsys, github: FakeGitHub, *, labels: tuple[str, ...] = (), backend: str = "github", confirmation: str | None = "yes"
    ) -> tuple[int, dict[str, Any]]:
        argv = [*self.common(backend, labels), "--reconciliation", str(self.reconciliation), "--output", str(self.output)]
        if confirmation is not None:
            argv += ["--publish-confirmation", confirmation]
        capsys.readouterr()
        rc = pg.main(argv, client_factory=lambda: github)
        return rc, json.loads(capsys.readouterr().out)

    def result(self) -> dict[str, Any]:
        return json.loads(self.output.read_text(encoding="utf-8"))


def codes(stdout: dict[str, Any]) -> list[str]:
    return [item["code"] for item in stdout.get("diagnostics", [])]


def test_github_publication_resumes_interrupted_epic_without_repeating_writes(tmp_path: Path, capsys) -> None:
    epic = issue(5, title="Auth", labels=("triage",))
    routes = {
        REPO: repo_payload(),
        f"{REPO}/labels/triage": {"name": "triage"},
        f"{REPO}/issues/2": issue(2, title="Login"),
        f"{REPO}/issues/2/parent": epic,
        f"{REPO}/issues/5": epic,
        f"{REPO}/issues/5/sub_issues": [issue(2, title="Login")],
        f"{REPO}/issues/7": issue(7, title="Other epic"),
        f"{REPO}/issues/8": issue(8, title="Users log out.", labels=("triage",)),
    }
    rejecting = FakeGitHub(
        routes, fail={f"{REPO}/issues/2/labels": GitHubError("GitHub API POST failed: 1 HTTP 422", status=422)}
    )
    rejected = Run(tmp_path / "rejected", EPIC, EPIC_DECISIONS)
    rejected.reconcile(capsys, rejecting, ("triage",))
    rc, out = rejected.publish(capsys, rejecting, labels=("triage",))
    assert rc == 1 and codes(out) == ["persist.publish_rejected"], out
    assert [path for path, _ in rejecting.writes] == [f"{REPO}/issues/2/labels"]
    assert not rejected.output.exists()

    timeout = "gh did not finish POST /repos/acme/widget/issues within 120 seconds"
    github = FakeGitHub(
        routes,
        fail={f"{REPO}/issues": GitHubError(timeout)},
        lost={"Users log out.": Crash("process killed"), f"{REPO}/issues/41/dependencies/blocked_by": GitHubError(timeout)},
    )
    run = Run(tmp_path / "resume", EPIC, EPIC_DECISIONS)
    twin_body = rg.issue_content(json.loads(run.preview.read_text(encoding="utf-8")))["item logout"]["body"]
    github.routes[f"{REPO}/issues/8"]["body"] = twin_body
    github.search_items = [github.routes[f"{REPO}/issues/8"]]
    plan = run.reconcile(capsys, github, ("triage",))["plan"]
    assert plan["sub_issue_links"] == [{"child": "logout", "child_issue": None}]
    code, refused = run.publish(capsys, github, labels=("triage",), confirmation=None)
    assert code == 1
    assert codes(refused) == ["persist.publish_unconfirmed"]

    def publish(expected: str | None) -> list[str]:
        rc, out = run.publish(capsys, github, labels=("triage",))
        assert rc == (0 if expected is None else 1), out
        assert codes(out) == ([] if expected is None else [expected]), out
        return [path for path, _ in github.writes]

    lock = pg._hold_lock(run.output.with_name("publication-result.json.lock"))
    assert lock is not None
    before = len(github.calls)
    assert publish("persist.publish_in_progress") == []
    assert github.calls[before:] == []
    pg._release_lock(lock)
    assert not run.output.exists()

    labeled = [f"{REPO}/issues/2/labels", f"{REPO}/issues"]
    assert publish("persist.publish_ambiguous") == labeled
    assert [step["status"] for step in run.result()["steps"]] == ["verified", "ambiguous", "pending", "pending"]
    github.routes[f"{REPO}/issues/5/sub_issues"].append(issue(10, title="Sign out"))
    assert publish("persist.recovery_drift") == labeled
    github.routes[f"{REPO}/issues/5/sub_issues"].pop()
    github.search_items = [github.routes[f"{REPO}/issues/8"], issue(9, title="Users log out")]
    assert publish("persist.recovery_drift") == labeled
    github.search_items = [github.routes[f"{REPO}/issues/8"]]
    github.search_incomplete = True
    assert publish("persist.recovery_drift") == labeled
    github.search_incomplete = False

    try:
        run.publish(capsys, github, labels=("triage",))
    except Crash:
        pass
    else:
        raise AssertionError("the simulated crash did not propagate")
    created = labeled + [f"{REPO}/issues"]
    assert [path for path, _ in github.writes] == created
    crashed = run.result()
    assert crashed["status"] == "in-progress"
    assert [step["status"] for step in crashed["steps"]] == ["verified", "attempting", "pending", "pending"]
    assert crashed["steps"][1]["issue"] is None and f"{REPO}/issues/41" in github.routes

    github.routes[f"{REPO}/issues/43"] = issue(43, title="Users log out.", body=twin_body, labels=("triage",))
    assert publish("persist.recovery_ambiguous") == created
    del github.routes[f"{REPO}/issues/43"]
    assert run.result() == crashed
    del github.routes[f"{REPO}/issues/2/parent"]
    assert publish("persist.recovery_drift") == created
    matched = run.result()
    assert matched["status"] == "stopped" and matched["issues"]["item logout"] == 41
    assert matched["steps"][1]["issue"] == 41 and matched["steps"][1]["status"] == "attempting"
    assert matched["steps"][2:] == crashed["steps"][2:]
    github.routes[f"{REPO}/issues/2/parent"] = issue(7, title="Other epic")
    assert publish("persist.recovery_conflict") == created
    github.routes[f"{REPO}/issues/2/parent"] = epic
    github.routes[f"{REPO}/issues/2"]["labels"] = []
    assert publish("persist.recovery_drift") == created
    github.routes[f"{REPO}/issues/2"]["labels"] = [{"name": "triage"}]
    github.routes[f"{REPO}/issues/41/parent"] = issue(7, title="Other epic")
    assert publish("persist.recovery_conflict") == created
    del github.routes[f"{REPO}/issues/41/parent"]
    assert run.result() == matched

    linked = created + [f"{REPO}/issues/5/sub_issues", f"{REPO}/issues/41/dependencies/blocked_by"]
    assert publish("persist.publish_ambiguous") == linked
    assert [step["status"] for step in run.result()["steps"]] == ["verified", "verified", "verified", "ambiguous"]
    parent = github.routes.pop(f"{REPO}/issues/41/parent")
    assert publish("persist.recovery_drift") == linked
    github.routes[f"{REPO}/issues/41/parent"] = parent
    assert publish(None) == linked
    assert [payload for _, payload in github.writes] == [
        {"labels": ["triage"]},
        github.writes[1][1],
        github.writes[1][1],
        {"sub_issue_id": 1041},
        {"issue_id": 1002},
    ]
    assert github.writes[1][1] == {"title": "Users log out.", "body": twin_body, "labels": ["triage"]}
    assert github.routes[f"{REPO}/issues/41/parent"]["number"] == 5
    assert github.routes[f"{REPO}/issues/41/dependencies/blocked_by"][0]["number"] == 2
    assert github.routes[f"{REPO}/issues/2"]["title"] == "Login"
    result = run.result()
    assert result["status"] == "complete"
    assert result["issues"] == {"epic": 5, "item login": 2, "item logout": 41}
    assert [step["kind"] for step in result["steps"]] == ["labels", "create", "sub_issue", "dependency"]
    assert {step["status"] for step in result["steps"]} == {"verified"}
    assert publish("persist.publish_already_attempted") == linked

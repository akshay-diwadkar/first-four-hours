"""Freshness, read-only boundary, and GitHub/local parity for select."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from tools.validation.git_test_support import seed_git

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills" / "workbench" / "ticket"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))
import check_issue_plan as check  # noqa: E402
import github_common as common  # noqa: E402
import scope_workspace  # noqa: E402

SOURCE = (ROOT / "tests" / "skills" / "ticket" / "fixtures" / "repo" / "src" / "names.py").read_text(encoding="utf-8")


def init_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "names.py").write_text(SOURCE, encoding="utf-8")
    (repo / "src" / "other.py").write_text("def other():\n    return 1\n", encoding="utf-8")
    seed_git(repo, remote="https://github.com/acme/widget.git")
    return repo


class FakeClient:
    def __init__(self, issues, children=None, comments=None, timelines=None, prs=None):
        self.issues = dict(issues)
        self.children = children or {}
        self.comments = comments or {}
        self.timelines = timelines or {}
        self.prs = prs or {}
        self.methods: list[str] = []
        self.response_bytes = 0
        self.preflight = mock.Mock()

    def request(self, method: str, path: str):
        self.methods.append(method)
        if method != "GET":
            raise common.ConfigError("GitHubClient.request supports only GET")
        number = int(path.rsplit("/", 1)[-1])
        if "/pulls/" in path:
            if number not in self.prs:
                raise common.GitHubError("missing", status=404)
            return self.prs[number]
        if number not in self.issues:
            raise common.GitHubError("missing", status=404)
        return self.issues[number]

    def paginated_get(self, path: str, *, item_limit=None):
        self.methods.append("GET")
        number = int(path.split("/issues/")[1].split("/")[0])
        if path.endswith("/sub_issues"):
            values = self.children.get(number, [])
        elif path.endswith("/comments"):
            values = self.comments.get(number, [])
        elif path.endswith("/timeline"):
            values = self.timelines.get(number, [])
        else:
            raise AssertionError(path)
        return values[:item_limit] if item_limit is not None else values


def run_sealer_in_process(repo: Path, snapshot: Path, scope_inputs: Path, draft: Path) -> tuple[int, str]:
    import importlib.util as _ilu

    spec = _ilu.spec_from_file_location("seal_issue_plan_fresh", SKILL / "scripts" / "seal_issue_plan.py")
    assert spec and spec.loader
    mod = _ilu.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    argv = [
        str(SKILL / "scripts" / "seal_issue_plan.py"),
        "--repo-root",
        str(repo),
        "--issue-json",
        str(snapshot),
        "--scope-inputs",
        str(scope_inputs),
        "--draft",
        str(draft),
    ]
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with mock.patch.object(sys, "argv", argv):
        with redirect_stdout(buf):
            code = mod.main()
    return code, buf.getvalue()


def scope_path(repo: Path, inputs: dict, work_item: int | str) -> Path:
    return repo / ".first-four-hours" / "ticket-scopes" / scope_workspace.scope_slug(inputs, work_item) / "ticket-scope.md"


MARKER = "<!-- ticket-item: "


def record(store: Path, rid: str, kind: str, *, parent=None, depends_on=(), state="open", body="Prose.\n", name=None):
    meta = {
        "version": "1.0.0",
        "id": rid,
        "kind": kind,
        "state": state,
        "parent": parent,
        "depends_on": list(depends_on),
        "package": "a" * 64,
        "payload_sha256": "b" * 64,
    }
    text = MARKER + json.dumps(meta, sort_keys=True) + " -->\n# " + rid + "\n\n" + body
    (store / (name or f"{rid}.md")).write_text(text, encoding="utf-8", newline="\n")


def write_draft(
    path: Path,
    metadata: dict,
    *,
    narrowed: bool = True,
    evidence: str = "`src/names.py:1` | anchor: `normalize_name` | observation: normalization is owned here",
) -> Path:
    sections = (
        "\n## Observable outcome\n- names are normalized through the public API\n\n"
        "## Current evidence\n- " + evidence + "\n"
    )
    path.write_text(
        "# Ticket Scope\n\n<!-- ticket-scope-metadata -->\n```json\n"
        + json.dumps(metadata, sort_keys=True)
        + "\n```\n"
        + (sections if narrowed else ""),
        encoding="utf-8",
    )
    return path


def shape(metadata: dict) -> tuple:
    return (
        metadata["status"],
        metadata["mode"],
        [candidate["readiness"] for candidate in metadata["selection"]["candidates"]],
    )


def test_select_seals_equivalent_github_and_local_scope(tmp_path: Path, monkeypatch) -> None:
    repo = init_repo(tmp_path)
    fixture = ROOT / "tests/skills/ticket/fixtures/v3/plan-ready-one-child"
    snapshot = json.loads((fixture / "snapshot.json").read_text(encoding="utf-8"))
    issues = {item["number"]: dict(item) for item in snapshot["issues"]}
    # This snapshot derives its children from the issue body, not native links.
    live = FakeClient(issues)
    monkeypatch.setattr(common, "GitHubClient", lambda **kwargs: live)
    draft = tmp_path / "draft.md"
    draft.write_text((fixture / "draft.md").read_text(encoding="utf-8"), encoding="utf-8")

    # Select never assumes a backend: scope inputs without one fail before any GitHub read.
    github_inputs = json.loads((fixture / "scope-inputs.json").read_text(encoding="utf-8"))
    assert github_inputs["backend"] == "github"
    no_backend = tmp_path / "no-backend.json"
    no_backend.write_text(json.dumps({k: v for k, v in github_inputs.items() if k != "backend"}), encoding="utf-8")
    code, result = run_sealer_in_process(repo, fixture / "snapshot.json", no_backend, draft)
    assert code == 1 and "scope_inputs.backend must be github or local" in result, result
    assert live.methods == [] and not (repo / ".first-four-hours").exists()
    live.preflight.assert_not_called()
    assert "scope_inputs.backend must be github or local" in check._validate_scope_inputs(
        {k: v for k, v in github_inputs.items() if k != "backend"}
    )
    import fetch_github_issues as github_fetch

    with pytest.raises(common.ConfigError, match="requires backend=github"):
        github_fetch.verify_readset(live, snapshot, {**github_inputs, "backend": "local"})
    assert live.methods == []

    code, result = run_sealer_in_process(repo, fixture / "snapshot.json", fixture / "scope-inputs.json", draft)
    assert code == 0, result
    sealed = json.loads(result)
    github_scope = scope_path(repo, github_inputs, 209)
    # Each backend locator and work item owns its own handoff path, even where normalizing collides.
    assert github_scope.parent.name.startswith("github-acme-widget-209-")
    slug = scope_workspace.scope_slug
    assert slug({"backend": "local", "local_store": "backlog-a"}, "b") != slug({"backend": "local", "local_store": "backlog"}, "a-b")
    assert slug({"backend": "github", "repository": "a-b/c"}, 1) != slug({"backend": "github", "repository": "a/b-c"}, 1)
    assert sealed["status"] == "sealed" and sealed["ignored"] is True, result
    assert Path(sealed["path"]).resolve() == github_scope.resolve()
    github_meta = check.parse_metadata(github_scope.read_text(encoding="utf-8"))
    # The scope opens with its selection metadata; only the sealer's bindings footer and the receipt follow the sections.
    sealed_scope = github_scope.read_text(encoding="utf-8")
    assert sealed_scope.startswith("# Ticket Scope\n\n<!-- ticket-scope-metadata -->\n")
    assert (github_meta["status"], github_meta["work_item"]) == ("plan-ready", 209)
    assert not {"inputs", "source", "checkout"} & set(github_meta)
    footer = check.BINDINGS_RE.search(sealed_scope)
    assert footer is not None and set(json.loads(footer.group("json"))) == {"inputs", "source", "checkout"}
    assert footer.start() > sealed_scope.index("<!-- ticket: untrusted-end -->")
    assert sealed_scope[footer.end() :].strip().startswith("<!-- ticket-scope: 1.0.0; sha256: ")
    assert sealed_scope.splitlines()[-1].startswith("<!-- ticket-scope: 1.0.0; sha256: ")
    # Metadata after a section, authored bindings, or stray text after the untrusted fence is refused.
    scope_text = draft.read_text(encoding="utf-8")
    meta_block = check.METADATA_RE.search(scope_text).group(0)
    misplaced = tmp_path / "misplaced.md"
    misplaced.write_text(scope_text.replace(meta_block + "\n", "", 1) + "\n" + meta_block + "\n", encoding="utf-8")
    misplaced_errors = check.validate_plan(misplaced, fixture / "snapshot.json", repo, fixture / "scope-inputs.json")
    assert "ticket-scope metadata must precede any content section" in misplaced_errors
    forged = tmp_path / "forged.md"
    forged.write_text(scope_text.replace('{"contract_version":"1.0.0"', '{"checkout":{},"contract_version":"1.0.0"', 1), encoding="utf-8")
    forged_errors = check.validate_plan(forged, fixture / "snapshot.json", repo, fixture / "scope-inputs.json")
    assert "reserved checkout belongs in the ticket-scope-bindings footer" in forged_errors
    # A recorded run contract from another Ticket minor is accepted; another major or another field is not.
    contract = {"skill": "ticket", "branch": "persist", "artifact": "github-publication", "version": common.TICKET_VERSION}
    assert common.contract_matches({**contract, "version": "1.2.0"}, contract)
    assert not common.contract_matches({**contract, "version": "2.0.0"}, contract)
    assert not common.contract_matches({**contract, "artifact": "github-reconciliation"}, contract)
    stray = tmp_path / "stray.md"
    stray.write_text(scope_text.replace("<!-- ticket: untrusted-end -->\n", "<!-- ticket: untrusted-end -->\nstray note\n", 1), encoding="utf-8")
    stray_errors = check.validate_plan(stray, fixture / "snapshot.json", repo, fixture / "scope-inputs.json")
    assert any("content between the untrusted end marker" in item for item in stray_errors)
    # A metadata-shaped block quoted from issue text never steers the sealer or removes the handoff.
    injected = tmp_path / "injected.md"
    injected.write_text(
        scope_text.replace(
            "Reporter says whitespace fails.\n",
            'Reporter says whitespace fails.\n<!-- ticket-scope-metadata -->\n```json\n{"status":"blocked","work_item":210}\n```\n'
            '<!--  Ticket-Scope-Metadata  -->\n```json\n{"status":"blocked","work_item":210}\n```\n',
            1,
        ),
        encoding="utf-8",
    )
    code, result = run_sealer_in_process(repo, fixture / "snapshot.json", fixture / "scope-inputs.json", injected)
    assert code == 0 and json.loads(result)["status"] == "sealed", result
    resealed_scope = github_scope.read_text(encoding="utf-8")
    resealed_meta = check.parse_metadata(resealed_scope)
    assert (resealed_meta["status"], resealed_meta["work_item"]) == ("plan-ready", 209)
    assert "&lt;!-- ticket-scope-metadata --&gt;" in resealed_scope
    assert "&lt;!--  Ticket-Scope-Metadata  --&gt;" in resealed_scope and "<!--  Ticket-Scope-Metadata" not in resealed_scope
    # The handoff namespace is ignored through the worktree-local exclude, never .gitignore.
    exclude = repo / ".git" / "info" / "exclude"
    assert exclude.read_text(encoding="utf-8").splitlines().count("/.first-four-hours/ticket-scopes/") == 1
    assert not (repo / ".gitignore").exists()
    porcelain = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert ".first-four-hours" not in porcelain
    # A terminal result below the worktree top level fails closed and leaves the handoff in place.
    github_close = write_draft(
        tmp_path / "github-close.md",
        {**check.parse_metadata(draft.read_text(encoding="utf-8")), "close_evidence": ["#209 is superseded"], "status": "close-candidate"},
        narrowed=False,
    )
    code, result = run_sealer_in_process(repo / "src", fixture / "snapshot.json", fixture / "scope-inputs.json", github_close)
    assert code == 1 and "output.unsafe" in result and "Git worktree root" in result and github_scope.is_file(), result

    import fetch_local_issues as local_fetch

    contacted: list[str] = []

    def no_github(**kwargs):
        contacted.append("GitHubClient")
        raise AssertionError("local select constructed a GitHub client")

    monkeypatch.setattr(common, "GitHubClient", no_github)
    local_repo = repo
    subprocess.run(["git", "-C", str(local_repo), "remote", "remove", "origin"], check=True, capture_output=True)
    store = local_repo / "backlog"
    store.mkdir()
    record(store, "auth", "epic")
    record(store, "login", "issue", parent="auth")
    record(store, "logout", "issue", parent="auth", depends_on=["login"])
    record(store, "other", "issue")
    # A managed-looking scope handoff inside the store must never become a candidate.
    record(store, "decoy", "issue", parent="auth", name="ticket-scope.md")
    # The backlog store can never live inside the ignored handoff namespace.
    with pytest.raises(common.ConfigError, match=r"outside the \.first-four-hours/ artifact folder"):
        local_fetch.build_snapshot(local_repo, ".first-four-hours/ticket-scopes/backlog", "single", "login")
    # A linked artifact root is refused before anything is written through it.
    rooted = tmp_path / "rooted"
    seed_git(rooted, {"seed.txt": "seed\n"})
    rooted_outside = tmp_path / "rooted-outside"
    rooted_outside.mkdir()
    if sys.platform == "win32":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(rooted / ".first-four-hours"), str(rooted_outside)], capture_output=True, check=True)
    else:
        (rooted / ".first-four-hours").symlink_to(rooted_outside, target_is_directory=True)
    with pytest.raises(scope_workspace.WorkspaceError, match="is not a real directory"):
        scope_workspace.prepare_workspace(rooted, "rooted")
    assert list(rooted_outside.iterdir()) == []

    run = tmp_path / "local-run"
    run.mkdir()
    epic_snapshot = run / "snapshot.json"
    fetch = ["fetch", "--repo-root", str(local_repo), "--local-store", "backlog", "--output"]
    assert local_fetch.main([*fetch, str(epic_snapshot), "--mode", "epic", "--epic-id", "auth"]) == 0
    task = {"constraints": [], "text": "Select and narrow the next implementation ticket for epic auth."}
    inputs = {
        "task": task,
        "backend": "local",
        "local_store": "backlog",
        "mode": "index",
        "epic": {"number": "auth"},
        "override": None,
        "exclusions": [],
    }
    scope = run / "scope-inputs.json"
    scope.write_text(json.dumps(inputs), encoding="utf-8")
    selection = {
        "candidates": [
            {"basis": "login is open with no dependencies", "issue": "login", "readiness": "ready"},
            {"basis": "logout depends on login, which is still open", "issue": "logout", "readiness": "blocked"},
        ],
        "rationale": "task needs normalization; login is the only ready child",
    }
    local_draft = write_draft(
        run / "draft.md",
        {"contract_version": "1.0.0", "mode": "index", "selection": selection, "status": "plan-ready", "task": task, "work_item": "login"},
    )
    verify = ["verify", "--repo-root", str(local_repo), "--snapshot", str(epic_snapshot), "--scope-inputs", str(scope)]
    assert local_fetch.main([*verify, "--selected-issue-id", "login"]) == 0

    # Unrelated record and unmanaged-file churn does not invalidate the decision.
    record(store, "other", "issue", body="Edited elsewhere.\n")
    (store / "notes.md").write_text("Unmanaged notes.\n", encoding="utf-8")
    code, result = run_sealer_in_process(local_repo, epic_snapshot, scope, local_draft)
    assert code == 0, result
    local_scope = scope_path(local_repo, inputs, "login")
    local_meta = check.parse_metadata(local_scope.read_text(encoding="utf-8"))
    assert shape(local_meta) == shape(github_meta)
    assert local_meta["work_item"] == "login"
    local_bindings = json.loads(check.BINDINGS_RE.search(local_scope.read_text(encoding="utf-8")).group("json"))
    assert local_bindings["source"]["backend"] == "local"
    assert local_bindings["source"]["work_item"]["url"] == "backlog/login.md"
    assert local_bindings["checkout"]["remote_repo"] == ""
    sealed_login = local_scope.read_bytes()

    # A sealed handoff is never evidence for another scope.
    self_cite = write_draft(
        run / "self-cite.md",
        check.parse_metadata(local_draft.read_text(encoding="utf-8")),
        evidence=f"`{github_scope.relative_to(repo).as_posix()}:1` | anchor: `ticket-scope` | observation: earlier handoff",
    )
    errors = check.validate_plan(self_cite, epic_snapshot, local_repo, scope)
    assert any(".first-four-hours/ticket-scopes/ handoff namespace" in error for error in errors), errors

    # Membership drift is stale, and a hand-patched snapshot is never current.
    record(store, "signup", "issue", parent="auth")
    assert local_fetch.main([*verify, "--selected-issue-id", "login"]) == 3
    (store / "signup.md").unlink()
    patched = json.loads(epic_snapshot.read_text(encoding="utf-8"))
    patched["edges"] = [edge for edge in patched["edges"] if edge["type"] not in {"depends_on", "blocks"}]
    patched["graph_receipt"] = common.graph_receipt(patched)
    patched["digest"] = common.snapshot_digest(patched)
    assert local_fetch.verify_local(local_repo, patched, inputs, "login")["fresh"] is False
    closed = json.loads(epic_snapshot.read_text(encoding="utf-8"))
    for issue in closed["issues"]:
        if issue["number"] == "login":
            issue["state"], issue["state_reason"] = "closed", "completed"
    closed["graph_receipt"] = common.graph_receipt(closed)
    closed["digest"] = common.snapshot_digest(closed)
    assert local_fetch.verify_local(local_repo, closed, inputs, "login")["fresh"] is False

    # An explicit override seals an honest terminal result without a file.
    override_scope = run / "override-scope.json"
    override_scope.write_text(json.dumps({**inputs, "override": {"issue": "logout"}}), encoding="utf-8")
    blocked_draft = write_draft(
        run / "blocked-draft.md",
        {
            "blockers": ["logout depends on login, which is still open"],
            "contract_version": "1.0.0",
            "mode": "index",
            "status": "blocked",
            "task": task,
            "work_item": "logout",
        },
        narrowed=False,
    )
    code, result = run_sealer_in_process(local_repo, epic_snapshot, override_scope, blocked_draft)
    assert code == 0, result
    blocked = json.loads(result)
    assert blocked["status"] == "blocked" and blocked["removed"] is None, result
    assert not scope_path(local_repo, inputs, "logout").exists()

    # A local snapshot and GitHub scope inputs, or the reverse, never reach verification.
    for mismatch_snapshot, mismatch_scope in ((fixture / "snapshot.json", scope), (epic_snapshot, fixture / "scope-inputs.json")):
        code, result = run_sealer_in_process(local_repo, mismatch_snapshot, mismatch_scope, local_draft)
        assert code == 1 and "snapshot backend does not match scope_inputs.backend" in result, result

    # Material drift of a decision record is stale and leaves the sealed handoff untouched.
    record(store, "login", "issue", parent="auth", body="Scope changed.\n")
    code, result = run_sealer_in_process(local_repo, epic_snapshot, scope, local_draft)
    assert code == 1 and "handoff.stale" in result, result
    assert local_scope.read_bytes() == sealed_login

    # A direct single record needs no epic; a closed record is a completed prerequisite.
    record(store, "login", "issue", parent="auth", state="closed", body="Scope changed.\n")
    before = {path.name: path.read_bytes() for path in store.iterdir()}
    single_snapshot = run / "single.json"
    assert local_fetch.main([*fetch, str(single_snapshot), "--mode", "single", "--issue-id", "logout"]) == 0
    single_scope = run / "single-scope.json"
    single_inputs = {"task": task, "backend": "local", "local_store": "backlog", "mode": "single", "ticket": {"number": "logout"}}
    single_scope.write_text(json.dumps(single_inputs), encoding="utf-8")
    single_draft = write_draft(
        run / "single-draft.md",
        {"contract_version": "1.0.0", "mode": "single", "status": "plan-ready", "task": task, "work_item": "logout"},
    )
    code, result = run_sealer_in_process(local_repo, single_snapshot, single_scope, single_draft)
    assert code == 0, result
    logout_scope = scope_path(local_repo, single_inputs, "logout")
    assert check.parse_metadata(logout_scope.read_text(encoding="utf-8"))["work_item"] == "logout"
    assert {path.name: path.read_bytes() for path in store.iterdir()} == before
    assert contacted == []

    # A terminal result removes that work item's earlier handoff, but never a tracked file.
    closing = write_draft(
        run / "close-draft.md",
        {
            "close_evidence": ["logout is superseded"],
            "contract_version": "1.0.0",
            "mode": "single",
            "status": "close-candidate",
            "task": task,
            "work_item": "logout",
        },
        narrowed=False,
    )
    tracked = logout_scope.relative_to(local_repo).as_posix()
    subprocess.run(["git", "-C", str(local_repo), "add", "-f", tracked], check=True, capture_output=True)
    code, result = run_sealer_in_process(local_repo, single_snapshot, single_scope, closing)
    assert code == 1 and "output.unsafe" in result and logout_scope.is_file(), result
    subprocess.run(["git", "-C", str(local_repo), "rm", "-q", "--cached", tracked], check=True, capture_output=True)
    code, result = run_sealer_in_process(local_repo, single_snapshot, single_scope, closing)
    assert code == 0, result
    removed = json.loads(result)
    assert removed["status"] == "close-candidate" and Path(removed["removed"]).resolve() == logout_scope.resolve(), result
    assert not logout_scope.exists() and local_scope.read_bytes() == sealed_login
    assert exclude.read_text(encoding="utf-8").splitlines().count("/.first-four-hours/ticket-scopes/") == 1

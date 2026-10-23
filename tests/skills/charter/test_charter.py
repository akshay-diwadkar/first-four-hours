"""Charter's workspace safety, confirmed publication, and verified revision."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tools.validation.python_test_support import run_python

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "workbench" / "charter" / "scripts"
CLI = SCRIPTS / "cli.py"
REPO = "acme/widget"
CHARTER = (
    "# Charter — Widget\n\n"
    "## Purpose\n\n"
    "Help small shops track stock without spreadsheets. Users: shop owners. Success: an owner sees "
    "today's stock on one screen. Out of scope: payments.\n\n"
    "## Agreed\n\n"
    "- Stock counts update when a sale is recorded. [user]\n\n"
    "## Unsettled\n\n"
    "### Open questions\n\n"
    "- Which point-of-sale systems matter first? owner: user\n\n"
    "## Revisions\n\n"
    "None yet.\n\n"
    "## Authority\n\n"
    "- Owner: this file owns this definition until a publication is verified.\n"
    "- State: ready\n"
)
AGREED = "- Stock counts update when a sale is recorded. [user]\n"


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(SCRIPTS))
workspace = _load("charter_workspace")
publish = _load("publish_charter")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, encoding="utf-8", check=True).stdout


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    return path


def _link_dir(link: Path, target: Path) -> None:
    """Create a directory link: a junction on Windows (no privilege needed), else a symlink."""
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=True)
    else:
        link.symlink_to(target, target_is_directory=True)


def _cli(root: Path, command: str, *inputs: str) -> tuple[int, dict[str, Any]]:
    argv = [sys.executable, str(CLI), "--repo-root", str(root)]
    for item in inputs:
        argv += ["--input", item]
    result = run_python([*argv, "--format", "json", command], capture_output=True, text=True, check=False)
    return result.returncode, json.loads(result.stdout)


def _codes(envelope: dict[str, Any]) -> list[str]:
    return [item["code"] for item in envelope.get("diagnostics", [])]


def _charter(root: Path, slug: str, text: str) -> Path:
    path = Path(workspace.prepare_workspace(root, slug)["path"])
    path.write_bytes(text.encode("utf-8"))
    return path


class FakeGitHub:
    """Serves the issue routes Charter uses; writes change what later reads return."""

    def __init__(self) -> None:
        self.issues: dict[int, dict[str, Any]] = {}
        self.writes: list[str] = []
        self.next_number = 7
        self.fail: str | None = None
        self.lose: str | None = None
        self.mangle = False

    def __call__(self, method: str, path: str, payload: dict[str, str] | None = None) -> Any:
        base = f"/repos/{REPO}/issues"
        if method == "GET" and path.startswith(base + "?"):
            match = re.search(r"[?&]page=(\d+)", path)
            assert match is not None, path
            page = int(match.group(1))
            listed = [copy.deepcopy(self.issues[number]) for number in sorted(self.issues, reverse=True)]
            return listed[(page - 1) * 100 : page * 100]
        if method == "GET":
            number = int(path.removeprefix(base + "/"))
            if number not in self.issues:
                raise publish.GitHubError(f"GitHub API GET {path} failed: HTTP 404", status=404)
            return copy.deepcopy(self.issues[number])
        self.writes.append(method)
        if self.fail == method:
            self.fail = None
            raise publish.GitHubError(f"GitHub API {method} {path} failed: HTTP 502", status=502)
        assert payload is not None and set(payload) == {"title", "body"}, payload
        if method == "POST":
            assert path == base, path
            number, self.next_number = self.next_number, self.next_number + 1
            self.issues[number] = {
                "number": number,
                "state": "open",
                "html_url": f"https://github.com/{REPO}/issues/{number}",
            }
        else:
            assert method == "PATCH", method
            number = int(path.removeprefix(base + "/"))
        body = payload["body"] + ("\n\nAltered by GitHub." if self.mangle else "")
        self.issues[number].update(title=payload["title"], body=body)
        if self.lose == method:
            self.lose = None
            raise publish.GitHubError(f"gh did not finish {method} {path} within 60 seconds")
        return copy.deepcopy(self.issues[number])


def _publish(
    capsys: pytest.CaptureFixture[str],
    root: Path,
    mode: str,
    *,
    slug: str = "widget",
    confirm: str | None = None,
    base: str | None = None,
) -> tuple[int, Any]:
    argv = [mode, "--repo-root", str(root), "--slug", slug, "--repo", REPO]
    if confirm is not None:
        argv += ["--confirm", confirm]
    if base is not None:
        argv += ["--base", base]
    code = publish.main(argv)
    return code, json.loads(capsys.readouterr().out)


def _diagnostic_codes(out: Any) -> list[str]:
    assert isinstance(out, list), out
    return [item["code"] for item in out]


def test_prepare_ignores_its_namespace_refuses_unsafe_paths_and_never_clobbers(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    exclude = repo / _git(repo, "rev-parse", "--git-path", "info/exclude").strip()
    before = exclude.read_bytes() if exclude.exists() else b""
    # An unsafe slug is refused, never rewritten into another project name, and nothing is written.
    for slug in ("../escape", ".hidden", "nested/name", "con", "Café", "a_b"):
        code, out = _cli(repo, "prepare", f"slug={slug}")
        assert code == 3 and _codes(out) == ["charter.slug_unsafe"], out
    code, out = _cli(repo, "check", "slug=../escape", f"repo={REPO}")
    assert code == 3 and _codes(out) == ["charter.slug_unsafe"], out
    assert not (repo / ".first-four-hours").exists()
    assert (exclude.read_bytes() if exclude.exists() else b"") == before

    code, out = _cli(repo, "prepare", "slug=Stock Tracker")
    assert code == 0, out
    destination = (repo / ".first-four-hours" / "charters" / "stock-tracker" / "charter.md").resolve()
    assert out["result"] == {"status": "created", "path": str(destination), "slug": "stock-tracker", "git_ignored": True}
    assert "/.first-four-hours/charters/" in exclude.read_text(encoding="utf-8").splitlines()
    assert _git(repo, "status", "--porcelain", "--untracked-files=all") == ""
    # The scaffold is a publishable charter in the settling state with no pointer yet.
    scaffold = destination.read_text(encoding="utf-8")
    rendered = publish.render(scaffold, "stock-tracker")
    assert rendered["state"] == "settling" and rendered["pointer"] is None, rendered

    # Resuming reuses the living draft instead of replacing it.
    edited = scaffold.replace("Unagreed.", "Help small shops track stock.")
    assert edited != scaffold
    destination.write_text(edited, encoding="utf-8")
    code, out = _cli(repo, "prepare", "slug=stock-tracker")
    assert code == 0 and out["result"]["status"] == "resumed", out
    assert destination.read_text(encoding="utf-8") == edited

    # A namespace Git already tracks is refused before any exclude rule is written.
    tracked = _repo(tmp_path / "tracked")
    (tracked / ".first-four-hours" / "charters").mkdir(parents=True)
    (tracked / ".first-four-hours" / "charters" / "notes.md").write_text("tracked\n", encoding="utf-8")
    _git(tracked, "add", ".")
    tracked_exclude = tracked / _git(tracked, "rev-parse", "--git-path", "info/exclude").strip()
    tracked_before = tracked_exclude.read_bytes() if tracked_exclude.exists() else b""
    code, out = _cli(tracked, "prepare", "slug=widget")
    assert code == 3 and _codes(out) == ["charter.namespace_tracked"], out
    assert not (tracked / ".first-four-hours" / "charters" / "widget").exists()
    assert (tracked_exclude.read_bytes() if tracked_exclude.exists() else b"") == tracked_before

    # A linked namespace is refused and nothing lands in the link's target.
    linked = _repo(tmp_path / "linked")
    outside = tmp_path / "outside"
    outside.mkdir()
    _link_dir(linked / ".first-four-hours", outside)
    code, out = _cli(linked, "prepare", "slug=widget")
    assert code == 3 and _codes(out) == ["charter.workspace_unsafe"], out
    assert list(outside.iterdir()) == []

    # In a linked worktree `.git` is a file: the rule lands where Git resolves the worktree's exclude path.
    main = _repo(tmp_path / "main")
    _git(main, "-c", "user.name=Charter", "-c", "user.email=charter@example.invalid", "commit", "-q", "--allow-empty", "-m", "init")
    worktree = tmp_path / "worktree"
    _git(main, "worktree", "add", "-q", str(worktree))
    assert (worktree / ".git").is_file()
    code, out = _cli(worktree, "prepare", "slug=widget")
    assert code == 0 and out["result"]["git_ignored"] is True, out
    resolved = Path(_git(worktree, "rev-parse", "--git-path", "info/exclude").strip())
    resolved = resolved if resolved.is_absolute() else worktree / resolved
    assert "/.first-four-hours/charters/" in resolved.read_text(encoding="utf-8").splitlines()
    assert _git(worktree, "status", "--porcelain", "--untracked-files=all") == ""


def test_create_binds_confirmation_and_adopts_instead_of_duplicating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path / "project")
    path = _charter(root, "widget", CHARTER)
    fake = FakeGitHub()
    monkeypatch.setattr(publish, "gh_api", fake)

    code, checked = _publish(capsys, root, "check")
    assert code == 0, checked
    assert checked["title"] == "Charter — Widget"
    assert checked["body"].startswith("## Purpose\n\nHelp small shops")
    assert checked["body"].endswith("- State: ready\n\n<!-- first-four-hours-charter: widget -->")
    assert checked["existing"] == [] and checked["pointer"] is None, checked
    digest = checked["content_sha256"]

    # Text the user did not confirm is never published, and the confirmation binds the title too.
    code, out = _publish(capsys, root, "create", confirm="0" * 64)
    assert code == 1 and _diagnostic_codes(out) == ["charter.unconfirmed"], out
    before = path.read_bytes()
    path.write_text(CHARTER.replace("# Charter — Widget", "# Charter — Widgets"), encoding="utf-8")
    code, out = _publish(capsys, root, "create", confirm=digest)
    assert code == 1 and _diagnostic_codes(out) == ["charter.unconfirmed"], out
    assert fake.writes == []
    path.write_bytes(before)

    # The create reaches GitHub but its result is lost: local authority stays exactly as it was.
    fake.lose = "POST"
    code, out = _publish(capsys, root, "create", confirm=digest)
    assert code == 1 and _diagnostic_codes(out) == ["charter.publish_uncertain"], out
    assert path.read_bytes() == before and list(fake.issues) == [7]

    # Over a hundred newer issues push the umbrella onto the second page of the listing.
    for number in range(8, 110):
        fake.issues[number] = {
            "number": number,
            "state": "open",
            "title": f"Unrelated {number}",
            "body": "Not a charter.",
            "html_url": f"https://github.com/{REPO}/issues/{number}",
        }
    fake.next_number = 110

    # The resumed publish finds the issue by its marker and adopts it instead of creating a second one.
    code, out = _publish(capsys, root, "create", confirm=digest)
    assert code == 0, out
    assert out["status"] == "adopted" and out["issue"]["number"] == 7, out
    assert fake.writes == ["POST"]
    text = path.read_text(encoding="utf-8")
    assert f"- Issue: {REPO}#7" in text and f"- Published content_sha256: {digest}" in text, text
    assert "non-authoritative" in text and "## Purpose\n\nHelp small shops" in text

    # The local sections stay as context that still renders the published text.
    code, again = _publish(capsys, root, "check")
    assert code == 0, again
    assert again["content_sha256"] == digest and again["local_matches_pointer"] is True, again
    assert again["pointer"] == {"repo": REPO, "number": 7, "content_sha256": digest}, again
    assert [item["content_sha256"] for item in again["existing"]] == [digest], again

    # A published charter is never created again.
    code, out = _publish(capsys, root, "create", confirm=digest)
    assert code == 1 and _diagnostic_codes(out) == ["charter.already_published"], out
    assert fake.writes == ["POST"]

    # Another project in the same repository has its own marker. Its create is read back: GitHub storing
    # other text than was sent leaves the local file untouched and no pointer.
    gadget = _charter(root, "gadget", CHARTER.replace("Widget", "Gadget"))
    gadget_before = gadget.read_bytes()
    code, checked = _publish(capsys, root, "check", slug="gadget")
    assert code == 0 and checked["existing"] == [], checked
    gadget_digest = checked["content_sha256"]
    fake.mangle = True
    code, out = _publish(capsys, root, "create", slug="gadget", confirm=gadget_digest)
    assert code == 1 and _diagnostic_codes(out) == ["charter.readback_mismatch"], out
    assert gadget.read_bytes() == gadget_before and fake.writes == ["POST", "POST"]
    fake.mangle = False

    # That marked umbrella now differs from the confirmed text: create refuses to replace it or add another.
    code, out = _publish(capsys, root, "create", slug="gadget", confirm=gadget_digest)
    assert code == 1 and _diagnostic_codes(out) == ["charter.umbrella_differs"], out
    assert fake.writes == ["POST", "POST"]

    # Revise replaces it only against the issue text check showed, then reads it back and writes the pointer.
    code, shown = _publish(capsys, root, "check", slug="gadget")
    assert code == 0 and [item["number"] for item in shown["existing"]] == [110], shown
    assert shown["existing"][0]["body"].endswith("Altered by GitHub."), shown
    code, out = _publish(capsys, root, "revise", slug="gadget", confirm=gadget_digest)
    assert code == 1 and _diagnostic_codes(out) == ["charter.issue_changed"], out
    code, out = _publish(
        capsys, root, "revise", slug="gadget", confirm=gadget_digest, base=shown["existing"][0]["content_sha256"]
    )
    assert code == 0, out
    assert out["status"] == "revised" and out["issue"]["number"] == 110, out
    assert fake.issues[110]["title"] == "Charter — Gadget" and fake.issues[110]["body"] == checked["body"]
    assert f"- Issue: {REPO}#110" in gadget.read_text(encoding="utf-8")
    assert fake.writes == ["POST", "POST", "PATCH"]


def test_revise_overwrites_only_a_seen_baseline_and_failures_keep_local_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path / "project")
    path = _charter(root, "widget", CHARTER)
    fake = FakeGitHub()
    monkeypatch.setattr(publish, "gh_api", fake)
    code, checked = _publish(capsys, root, "check")
    assert code == 0, checked
    digest = checked["content_sha256"]

    # A failed publish leaves local authority intact and creates nothing.
    before = path.read_bytes()
    fake.fail = "POST"
    code, out = _publish(capsys, root, "create", confirm=digest)
    assert code == 1 and _diagnostic_codes(out) == ["charter.publish_uncertain"], out
    assert path.read_bytes() == before and fake.issues == {}
    code, out = _publish(capsys, root, "create", confirm=digest)
    assert code == 0 and out["status"] == "created" and out["issue"]["number"] == 7, out

    # The user agrees a revision; the revise command's wiring refuses an unconfirmed hash first.
    revised = path.read_text(encoding="utf-8").replace(AGREED, AGREED + "- Owners see low-stock alerts. [confirmed]\n")
    path.write_text(revised, encoding="utf-8")
    code, checked = _publish(capsys, root, "check")
    assert code == 0 and checked["local_matches_pointer"] is False, checked
    new = checked["content_sha256"]
    code, envelope = _cli(root, "revise", "slug=widget", f"repo={REPO}", "confirm=" + "0" * 64)
    assert code == 3 and _codes(envelope) == ["charter.unconfirmed"], envelope

    # Someone edited the issue on GitHub: the pointer's baseline no longer holds, so nothing is overwritten.
    fake.issues[7]["body"] += "\n\nEdited on GitHub."
    code, out = _publish(capsys, root, "revise", confirm=new)
    assert code == 1 and _diagnostic_codes(out) == ["charter.issue_changed"], out
    assert "PATCH" not in fake.writes and path.read_text(encoding="utf-8") == revised

    # After the user saw that current text and chose to replace it, the revision is applied and verified.
    code, checked = _publish(capsys, root, "check")
    assert code == 0, checked
    current = checked["existing"][0]["content_sha256"]
    assert current not in (digest, new)
    code, out = _publish(capsys, root, "revise", confirm=new, base=current)
    assert code == 0, out
    assert out["status"] == "revised" and out["issue"]["number"] == 7, out
    assert fake.issues[7]["body"] == checked["body"]
    text = path.read_text(encoding="utf-8")
    assert f"- Published content_sha256: {new}" in text and "non-authoritative" in text, text
    assert "- Owners see low-stock alerts. [confirmed]" in text

    # A read-back that differs from what was sent never advances the pointer.
    path.write_text(text.replace(AGREED, AGREED + "- Alerts arrive by email. [user]\n"), encoding="utf-8")
    code, checked = _publish(capsys, root, "check")
    assert code == 0, checked
    fake.mangle = True
    code, out = _publish(capsys, root, "revise", confirm=checked["content_sha256"])
    assert code == 1 and _diagnostic_codes(out) == ["charter.readback_mismatch"], out
    assert f"- Published content_sha256: {new}" in path.read_text(encoding="utf-8")
    assert fake.writes.count("PATCH") == 2

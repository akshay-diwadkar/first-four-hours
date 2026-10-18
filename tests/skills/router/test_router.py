from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from tools.validation.python_test_support import run_python

REPO_ROOT = Path(__file__).resolve().parents[3]
CLI = REPO_ROOT / "skills" / "sensemaking" / "router" / "scripts" / "cli.py"

ROUTE = """# Route: ship the selected ticket

Repository: <repo>

Ticket 7 is selected and narrowed; no Blueprint exists yet.

## Steps

1. `blueprint`
   - Why: the change needs a decision-complete plan.
   - Input: the sealed `ticket-scope.md` for ticket 7.
   - Result: a sealed Blueprint for the change.
   - Prompt:
     ```text
     Use blueprint in <repo> to plan ticket 7 from its sealed ticket-scope.md.
     ```
2. `construct`
   - Why: the sealed Blueprint must be executed.
   - Input: the sealed Blueprint from step 1.
   - Result: the implemented change with its verification report.
   - Prompt:
     ````text
     Use construct in <repo> once step 1 has sealed its Blueprint.
     1. Execute .first-four-hours/blueprints/<task>/blueprint.md.
     - Input: that sealed Blueprint only.
     ```
     ````
3. `assess`
   - Why: the change must be checked against ticket 7.
   - Input: the change from step 2 and ticket 7.
   - Result: a sealed assessment of the change.
   - Prompt:
     ```text
     Use assess in <repo> to review the change from step 2 against ticket 7.
     ```
"""


def _route(repo: Path) -> str:
    return ROUTE.replace("<repo>", str(repo))


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, encoding="utf-8", check=True).stdout


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    return repo


def _link_dir(link: Path, target: Path) -> None:
    """Create a directory link: a junction on Windows (no privilege needed), else a symlink."""
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=True)
    else:
        link.symlink_to(target, target_is_directory=True)


def _seal(tmp_path: Path, repo: Path, slug: str, text: str) -> subprocess.CompletedProcess[str]:
    draft = tmp_path / f"{slug}-draft.md"
    draft.write_text(text, encoding="utf-8")
    return _run(repo, draft, slug)


def _run(repo: Path, draft: Path, slug: str) -> subprocess.CompletedProcess[str]:
    return run_python(
        [
            sys.executable, str(CLI),
            "--repo-root", str(repo),
            "--input", f"draft={draft}",
            "--input", f"slug={slug}",
            "--format", "json",
            "run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_route_seals_into_ignored_workspace(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    route = _route(repo)
    sealed = _seal(tmp_path, repo, "ship-ticket", route)
    assert sealed.returncode == 0, sealed.stdout + sealed.stderr
    destination = (repo / ".first-four-hours" / "routes" / "ship-ticket" / "route.md").resolve()
    assert json.loads(sealed.stdout)["result"] == {"status": "sealed", "path": str(destination), "git_ignored": True}
    assert destination.read_text(encoding="utf-8") == route
    assert _git(repo, "status", "--porcelain", "--untracked-files=all") == ""
    # An already-satisfied target seals an honest no-step route rather than an invented step,
    # its backticked Repository line still names the target, and a BOM-prefixed draft
    # (as Windows PowerShell 5.1 writes) is judged on its text.
    satisfied = (
        f"# Route: ship the selected ticket\n\nRepository: `{repo}`\n\n"
        "## Steps\n\nNone: the assessment of the change already reports clear.\n"
    )
    done = _seal(tmp_path, repo, "already-done", "\ufeff" + satisfied)
    assert done.returncode == 0, done.stdout + done.stderr
    assert (repo / ".first-four-hours" / "routes" / "already-done" / "route.md").read_text(encoding="utf-8") == satisfied


def test_non_manifest_capability_is_refused_without_writes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    # A domain is not a capability, an indented step cannot pass as wrapped field text,
    # a step missing one of its Why/Input/Result fields is refused, and so is a step whose
    # fenced prompt has no `Prompt:` field to hold it.
    domain_step = (
        _route(repo).replace("1. `blueprint`", "1. `workbench`", 1)
        .replace(
            "   - Result: a sealed Blueprint for the change.\n",
            "   - Result: a sealed Blueprint for the change.\n   2. `router`\n",
            1,
        )
        .replace("   - Why: the sealed Blueprint must be executed.\n", "", 1)
        .replace("   - Result: a sealed assessment of the change.\n   - Prompt:\n", "   - Result: a sealed assessment of the change.\n", 1)
    )
    refused = _seal(tmp_path, repo, "domain-node", domain_step)
    assert refused.returncode != 0, refused.stdout
    assert set(json.loads(refused.stdout)["blocking_reasons"]) == {
        "route.capability_unknown",
        "route.step_line",
        "route.step_field",
        "route.step_prompt",
    }, refused.stdout
    assert not (repo / ".first-four-hours").exists()
    # A `None:` completion claim cannot be mixed with steps.
    mixed = _seal(tmp_path, repo, "mixed-none", _route(repo) + "None: the change already exists.\n")
    assert mixed.returncode != 0, mixed.stdout
    assert json.loads(mixed.stdout)["blocking_reasons"] == ["route.none_mixed"], mixed.stdout
    assert not (repo / ".first-four-hours").exists()
    # A draft inside the target repository is refused before anything is sealed.
    inside = repo / "draft.md"
    inside.write_text(_route(repo), encoding="utf-8")
    refused = _run(repo, inside, "in-repo")
    assert refused.returncode != 0, refused.stdout
    assert json.loads(refused.stdout)["blocking_reasons"] == ["route.draft_location"], refused.stdout
    assert not (repo / ".first-four-hours").exists()
    # A route naming another repository is refused before anything is sealed in either one,
    # and so is a route that names no repository.
    other = tmp_path / "other"
    other.mkdir()
    elsewhere = _seal(tmp_path, repo, "elsewhere", _route(other))
    assert elsewhere.returncode != 0, elsewhere.stdout
    assert json.loads(elsewhere.stdout)["blocking_reasons"] == ["route.repository_mismatch"], elsewhere.stdout
    unnamed = _seal(tmp_path, repo, "unnamed", _route(repo).replace(f"Repository: {repo}\n\n", "", 1))
    assert unnamed.returncode != 0, unnamed.stdout
    assert json.loads(unnamed.stdout)["blocking_reasons"] == ["route.repository"], unnamed.stdout
    assert not (repo / ".first-four-hours").exists()
    assert not (other / ".first-four-hours").exists()
    # A relative Repository value names no target, a step with no Prompt field at all is
    # refused, and an unclosed prompt fence cannot swallow the rest of the route.
    relative = _seal(tmp_path, repo, "relative", _route(repo).replace(f"Repository: {repo}", "Repository: repo", 1))
    assert relative.returncode != 0, relative.stdout
    assert json.loads(relative.stdout)["blocking_reasons"] == ["route.repository"], relative.stdout
    step_3_prompt = f"   - Prompt:\n     ```text\n     Use assess in {repo} to review the change from step 2 against ticket 7.\n     ```\n"
    assert _route(repo).count(step_3_prompt) == 1
    bare = _seal(tmp_path, repo, "bare-step", _route(repo).replace(step_3_prompt, "", 1))
    assert bare.returncode != 0, bare.stdout
    assert json.loads(bare.stdout)["blocking_reasons"] == ["route.step_prompt"], bare.stdout
    unclosed = _seal(tmp_path, repo, "unclosed", _route(repo).replace("against ticket 7.\n     ```\n", "against ticket 7.\n", 1))
    assert unclosed.returncode != 0, unclosed.stdout
    assert json.loads(unclosed.stdout)["blocking_reasons"] == ["route.step_prompt"], unclosed.stdout
    assert not (repo / ".first-four-hours").exists()


def test_unsafe_route_namespace_is_refused_without_exclude_writes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    artifact_root = repo / ".first-four-hours"
    namespace = artifact_root / "routes"
    exclude = repo / ".git" / "info" / "exclude"

    def exclude_bytes() -> bytes:
        return exclude.read_bytes() if exclude.exists() else b""

    before = exclude_bytes()

    def refuse(slug: str) -> None:
        refused = _seal(tmp_path, repo, slug, _route(repo))
        assert refused.returncode != 0, refused.stdout
        assert json.loads(refused.stdout)["blocking_reasons"] == ["route.workspace_unsafe"], refused.stdout
        assert exclude_bytes() == before

    # Untracked files already in the namespace would be hidden by a new ignore rule.
    namespace.mkdir(parents=True)
    (namespace / "notes.md").write_text("mine\n", encoding="utf-8")
    refuse("untracked")
    assert _git(repo, "status", "--porcelain", "--untracked-files=all") == "?? .first-four-hours/routes/notes.md\n"
    # A linked artifact root is refused before a rule could hide what the link reaches.
    shutil.rmtree(artifact_root)
    outside = tmp_path / "outside"
    outside.mkdir()
    _link_dir(artifact_root, outside)
    refuse("linked")
    assert list(outside.iterdir()) == []
    # An already-ignored linked artifact root is still refused, so nothing is written through the link.
    gitignore = repo / ".gitignore"
    gitignore.write_text("/.first-four-hours/routes/\n", encoding="utf-8")
    refuse("ignored-link")
    assert list(outside.iterdir()) == []
    gitignore.unlink()
    if os.name == "nt":
        os.rmdir(artifact_root)
    else:
        artifact_root.unlink()
    # A linked namespace inside a real artifact root is refused too, including when it is already ignored.
    artifact_root.mkdir()
    _link_dir(namespace, outside)
    refuse("linked-namespace")
    assert list(outside.iterdir()) == []
    gitignore.write_text("/.first-four-hours/routes/\n", encoding="utf-8")
    refuse("ignored-linked-namespace")
    assert list(outside.iterdir()) == []
    gitignore.unlink()
    if os.name == "nt":
        os.rmdir(namespace)
    else:
        namespace.unlink()
    # A file in the namespace's place is refused before any rule is written.
    namespace.write_text("not a folder\n", encoding="utf-8")
    refuse("file-namespace")
    namespace.unlink()
    # A namespace tracked only in the index is a project conflict even with no folder on disk.
    namespace.mkdir()
    (namespace / "notes.md").write_text("tracked\n", encoding="utf-8")
    _git(repo, "add", ".first-four-hours/routes/notes.md")
    shutil.rmtree(namespace)
    refuse("tracked")
    assert _git(repo, "ls-files", ".first-four-hours/routes") == ".first-four-hours/routes/notes.md\n"
    assert not namespace.exists()
    # The installed skill, or any folder inside it, is never a route target, even when the
    # route's Repository line names it; nothing is written there.
    installed = tmp_path / "installed" / "router"
    shutil.copytree(CLI.parents[1], installed, ignore=shutil.ignore_patterns("__pycache__"))

    def refuse_installed(target: Path) -> None:
        draft = tmp_path / "installed-draft.md"
        draft.write_text(_route(target), encoding="utf-8")
        refused = run_python(
            [
                sys.executable, str(installed / "scripts" / "cli.py"),
                "--repo-root", str(target),
                "--input", f"draft={draft}",
                "--input", "slug=inside-skill",
                "--format", "json",
                "run",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert refused.returncode != 0, refused.stdout
        assert json.loads(refused.stdout)["blocking_reasons"] == ["route.workspace_unsafe"], refused.stdout
        assert not (target / ".first-four-hours").exists()

    refuse_installed(installed)
    refuse_installed(installed / "references")

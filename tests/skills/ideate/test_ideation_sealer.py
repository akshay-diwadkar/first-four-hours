from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from tools.validation.python_test_support import run_python

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills" / "sensemaking" / "ideate"


# ---------------------------------------------------------------------------
# Minimal valid draft factory
# ---------------------------------------------------------------------------


def _valid_draft() -> str:
    # A small two-option decision: only the required records, no filler fields.
    return (
        "# Ideation: Reduce Latency\n\n"
        "## What to do\n"
        "- Outcome: recommended direction\n"
        "- Final choice: yours to make\n\n"
        "Option 1 leads with the verified caching benchmark; Option 2 stays a viable choice.\n\n"
        "## Goal and research\n"
        "- Goal: reduce p99 query latency below 200ms\n"
        "- Decision criteria: latency reduction, effort\n"
        "- Scope / non-goals: API layer; no database hardware replacement\n"
        "- Research: settled — vendor docs, a web search, and one caching benchmark; no production traces\n\n"
        "## Evidence\n\n"
        "### External evidence\n\n"
        "| Finding | Source | Locator | Date/freshness | Relevance |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| Caching cuts latency | https://example.com | § 2 | 2026-07 | high |\n\n"
        "## Exploration\n\n"
        "Search shape: alternative\n"
        "- Obvious defaults: scale out the API servers\n"
        "- Simplify/eliminate: not applicable — every endpoint is required\n"
        "- Invert/relax an authorized constraint: not applicable — the latency target is the user's\n"
        "- Domain transfer: Option 1, response caching\n"
        "- Combine mechanisms: not applicable — one slow path, so nothing to pair\n"
        "- Actor/timing/control: not applicable — requests are already asynchronous\n"
        "- Failure recovery: not applicable — the target concerns the success path\n"
        "- Preserve baseline: Option 2, keep the current API layer\n\n"
        "### Option 1: Add In-memory Cache\n"
        "- Support basis: evidence-backed: the example.com caching benchmark\n\n"
        "## What would change the answer\n\n"
        "Option 2 wins if payload size, not lookups, drives latency.\n"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, encoding="utf-8", check=True
    ).stdout


def _link_dir(link: Path, target: Path) -> None:
    """Create a directory link: a junction on Windows (no privilege needed), else a symlink."""
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=True)
    else:
        link.symlink_to(target, target_is_directory=True)


def _seal(repo: Path, draft: Path, slug: str) -> subprocess.CompletedProcess[str]:
    return run_python(
        [
            sys.executable,
            str(SKILL / "scripts" / "cli.py"),
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


def test_cli_seals_into_ignored_workspace_and_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "répo"
    repo.mkdir()
    _git(repo, "init", "-q")
    draft = tmp_path / "draft.md"
    draft.write_text(_valid_draft(), encoding="utf-8")

    # The public CLI seals only the ignored workspace handoff and reports the ignore state.
    sealed = _seal(repo, draft, "Latency Options")
    assert sealed.returncode == 0, sealed.stdout + sealed.stderr
    destination = (repo / ".first-four-hours" / "ideations" / "latency-options" / "ideation.md").resolve()
    assert json.loads(sealed.stdout)["result"] == {
        "status": "sealed", "path": str(destination), "git_ignored": True,
    }
    sealed_bytes = destination.read_bytes()
    # The title opens the handoff; the receipt is its final line.
    assert sealed_bytes.startswith(b"# Ideation: ")
    assert sealed_bytes.splitlines()[-1].startswith(b"<!-- ideation-handoff: 2.0.2; sha256: ")
    # What to do opens the handoff, so a reader acts on it before any evidence.
    assert sealed_bytes.split(b"\n## ", 1)[1].startswith(b"What to do\n")
    assert b"- Final choice: yours to make\n" in sealed_bytes

    # Re-sealing the sealed handoff reproduces it and keeps one exclude rule;
    # the handoff never shows up as untracked noise.
    sealed_copy = tmp_path / "sealed-copy.md"
    sealed_copy.write_bytes(sealed_bytes)
    resealed = _seal(repo, sealed_copy, "latency-options")
    assert resealed.returncode == 0, resealed.stdout + resealed.stderr
    assert destination.read_bytes() == sealed_bytes
    exclude = (repo / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert exclude.splitlines().count("/.first-four-hours/ideations/") == 1
    assert _git(repo, "status", "--porcelain", "--untracked-files=all") == ""

    # Each missing required record or lens line is refused with a diagnostic naming
    # its repair, and nothing is written.
    research = "- Research: settled — vendor docs, a web search, and one caching benchmark; no production traces\n"
    baseline = "- Preserve baseline: Option 2, keep the current API layer\n\n"
    survivor = (
        "### Option 1: Add In-memory Cache\n"
        "- Support basis: evidence-backed: the example.com caching benchmark\n\n"
        "## What would change the answer\n\n"
    )
    choice = "- Final choice: yours to make\n"
    action_prose = "Option 1 leads with the verified caching benchmark; Option 2 stays a viable choice.\n\n"
    draft_text = _valid_draft()
    action_start = draft_text.index("## What to do\n")
    framing_start = draft_text.index("## Goal and research\n")
    change_start = draft_text.index("## What would change the answer\n")
    opening_onward = draft_text[action_start:change_start]
    action_last = draft_text[framing_start:change_start] + draft_text[action_start:framing_start]
    for slug, old, new, codes, repair in (
        ("missing", choice, "", ["ideation.field_empty"], "'- Final choice:'"),
        ("unowned", choice, "- Final choice: made by you\n", ["ideation.invalid_final_choice"], "<choice; source>"),
        ("undelegated", choice, "- Final choice: delegated\n", ["ideation.invalid_final_choice"], "<scope; source>"),
        # A 1.x state is refused, never kept as an alias.
        ("legacy-outcome", "- Outcome: recommended direction\n", "- Outcome: decision-ready\n", ["ideation.invalid_outcome"], "recommended direction"),
        # What to do must open the handoff and say what to do, not only carry its fields.
        ("action-last", opening_onward, action_last, ["ideation.heading_order"], "canonical order"),
        ("fields-only", action_prose, "", ["ideation.empty_what_to_do"], "plain language"),
        ("no-research", research, "", ["ideation.field_empty"], "'- Research:'"),
        ("bare-stop", research, "- Research: settled\n", ["ideation.invalid_research_record"], "<coverage searched; limitations>"),
        ("unknown-stop", research, "- Research: condition met — docs only\n", ["ideation.invalid_research_record"], "<coverage searched; limitations>"),
        ("no-shape", "Search shape: alternative\n", "", ["ideation.invalid_search_shape"], "'Search shape: alternative | path | path with a fork'"),
        ("skipped-lens", "- Domain transfer: Option 1, response caching\n", "", ["ideation.lens_unaccounted"], "'- Domain transfer: <candidate>'"),
        ("no-defaults", "- Obvious defaults: scale out the API servers\n", "", ["ideation.lens_unaccounted"], "'- Obvious defaults: <candidate>'"),
        ("misplaced-lens", baseline + survivor, survivor + baseline, ["ideation.lens_unaccounted"], "'- Preserve baseline: <candidate>'"),
        ("unordered-path", "Search shape: alternative\n", "Search shape: path\n", ["ideation.lens_unaccounted"] * 5, "'- Cheapest-learning-first: <candidate>'"),
        # Orderings hidden in an HTML comment are invisible to a reader, so they do not count.
        (
            "commented-orderings",
            "Search shape: alternative\n",
            "Search shape: path with a fork\n<!--\n- Risk-first: a\n- Value-first: b\n- Reversible-first: c\n"
            "- Dependency-forced: d\n- Cheapest-learning-first: e\n-->\n",
            ["ideation.lens_unaccounted"] * 5,
            "'- Risk-first: <candidate>'",
        ),
    ):
        variant = tmp_path / f"{slug}.md"
        variant.write_text(_valid_draft().replace(old, new), encoding="utf-8")
        refused = _seal(repo, variant, slug)
        assert refused.returncode != 0
        envelope = json.loads(refused.stdout)
        assert envelope["blocking_reasons"] == codes, refused.stdout
        assert any(repair in item["message"] for item in envelope["diagnostics"]), refused.stdout
        assert not (repo / ".first-four-hours" / "ideations" / slug).exists()

    # A sealed handoff is never evidence for the next ideation.
    self_cited = tmp_path / "self-cited.md"
    self_cited.write_text(
        _valid_draft().replace(
            "## Evidence\n\n",
            "## Evidence\n\n### Local evidence\n\n"
            "| Claim | Source path | Locator | Verification |\n"
            "| --- | --- | --- | --- |\n"
            "| Prior ideation handoff | .first-four-hours/ideations/latency-options/ideation.md | whole file | read |\n\n",
            1,
        ),
        encoding="utf-8",
    )
    refused = _seal(repo, self_cited, "self-cited")
    assert refused.returncode != 0
    assert json.loads(refused.stdout)["blocking_reasons"] == ["ideation.workspace_evidence"], refused.stdout
    assert not (repo / ".first-four-hours" / "ideations" / "self-cited").exists()

    # A linked slug directory is refused, so the handoff never lands outside the repository.
    outside = tmp_path / "outside"
    outside.mkdir()
    _link_dir(repo / ".first-four-hours" / "ideations" / "linked", outside)
    refused = _seal(repo, draft, "linked")
    assert refused.returncode != 0, refused.stdout
    assert json.loads(refused.stdout)["blocking_reasons"] == ["ideation.workspace_unsafe"], refused.stdout
    assert list(outside.iterdir()) == []
    # A linked artifact root is refused before anything is written through it.
    rooted = tmp_path / "rooted"
    rooted_outside = tmp_path / "rooted-outside"
    rooted.mkdir()
    rooted_outside.mkdir()
    _link_dir(rooted / ".first-four-hours", rooted_outside)
    refused = _seal(rooted, draft, "rooted")
    assert refused.returncode != 0, refused.stdout
    assert json.loads(refused.stdout)["blocking_reasons"] == ["ideation.workspace_unsafe"], refused.stdout
    assert list(rooted_outside.iterdir()) == []

    # A tracked namespace is a project conflict: refuse without touching the existing handoff.
    (repo / ".first-four-hours" / "ideations" / "notes.md").write_text("tracked\n", encoding="utf-8")
    _git(repo, "add", "-f", ".first-four-hours/ideations/notes.md")
    refused = _seal(repo, draft, "after-tracked")
    assert refused.returncode != 0
    assert json.loads(refused.stdout)["blocking_reasons"] == ["ideation.workspace_unsafe"], refused.stdout
    assert "already contains tracked project files" in refused.stdout
    assert not (repo / ".first-four-hours" / "ideations" / "after-tracked").exists()
    assert destination.read_bytes() == sealed_bytes

    # A linked Git metadata directory is refused before any exclude rule is written through it.
    info = repo / ".git" / "info"
    linked_info = tmp_path / "linked-info"
    shutil.copytree(info, linked_info)
    shutil.rmtree(info)
    _link_dir(info, linked_info)
    before = (linked_info / "exclude").read_bytes()
    refused = _seal(repo, draft, "via-linked-info")
    assert refused.returncode != 0, refused.stdout
    assert "Git exclude path is linked" in refused.stdout
    assert (linked_info / "exclude").read_bytes() == before

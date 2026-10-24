#!/usr/bin/env python3
"""Re-check a confirmed PR description, then open the pull request or update the branch's open one with gh."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pr_contract import GitError, Problem, check_description, emit, git  # noqa: E402


def run_gh(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=120,
    )


def _strip_remote(ref: str, remotes: list[str]) -> tuple[str | None, str]:
    for remote in remotes:
        if ref.startswith(f"{remote}/"):
            return remote, ref[len(remote) + 1 :]
    return None, ref


def _detail(completed: subprocess.CompletedProcess[str]) -> str:
    return (completed.stderr or "").strip() or (completed.stdout or "").strip()


def _update(repo: Path, draft: Path, base: str, base_branch: str, head_branch: str, title: str | None) -> int:
    fields = "number,state,url,baseRefName,headRefName,isCrossRepository"
    try:
        view = run_gh(["gh", "pr", "view", head_branch, "--json", fields], repo)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return emit([("pr.publish_failed", f"gh pr view did not complete: {exc}.", "Check gh installation and authentication, then rerun.")], draft)
    if view.returncode:
        return emit(
            [
                (
                    "pr.update_missing",
                    f"gh pr view found no pull request for branch `{head_branch}`: {_detail(view)}.",
                    "If gh reports no pull request for this branch, ask the user whether to open one instead; "
                    "otherwise repair the reported gh problem and rerun.",
                )
            ],
            draft,
        )
    try:
        data = json.loads(view.stdout or "")
    except ValueError:
        data = None
    if not isinstance(data, dict) or type(data.get("number")) is not int or not isinstance(data.get("url"), str):
        return emit([("pr.publish_failed", "gh pr view returned unreadable output.", "Check gh installation, then rerun.")], draft)
    number = data["number"]
    if data.get("headRefName") != head_branch or data.get("isCrossRepository") is not False:
        return emit(
            [
                (
                    "pr.update_missing",
                    f"pull request #{number} is not from branch `{head_branch}` of this repository.",
                    "Open a pull request for this branch with publish, or update that pull request from its own branch.",
                )
            ],
            draft,
        )
    state = data.get("state")
    if state != "OPEN":
        return emit(
            [
                (
                    "pr.update_not_open",
                    f"pull request #{number} for `{head_branch}` is {str(state).lower()}; only an open pull request is updated.",
                    "Open a new pull request with publish instead.",
                )
            ],
            draft,
        )
    if data.get("baseRefName") != base_branch:
        return emit(
            [
                (
                    "pr.update_base_mismatch",
                    f"pull request #{number} targets `{data.get('baseRefName')}`, but the draft was checked against `{base}`.",
                    "Check the draft against the pull request's base and rerun with that base.",
                )
            ],
            draft,
        )
    gh_argv = ["gh", "pr", "edit", str(number), "--body-file", str(draft)]
    if title is not None:
        gh_argv += ["--title", title]
    try:
        completed = run_gh(gh_argv, repo)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return emit([("pr.publish_failed", f"gh pr edit did not complete: {exc}.", "Check gh installation and authentication, then rerun.")], draft)
    if completed.returncode:
        return emit([("pr.publish_failed", f"gh pr edit failed: {_detail(completed)}.", "Repair the reported gh problem, then rerun.")], draft)
    print(json.dumps({"status": "updated", "url": data["url"]}, sort_keys=True, separators=(",", ":")))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("--repo-root", "--draft", "--runs", "--base", "--confirm"):
        parser.add_argument(name, required=True)
    parser.add_argument("--title")
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args(argv)
    repo = Path(args.repo_root).resolve()
    draft = Path(args.draft).resolve()
    runs = Path(args.runs).resolve()
    problems, result = check_description(repo, draft, runs, args.base)
    if problems:
        return emit(problems, draft)

    gates: list[Problem] = []
    if (args.title is None and not args.update) or (args.title is not None and not args.title.strip()):
        gates.append(("pr.title_missing", "the PR title is empty.", "Pass the title the user confirmed."))
    if args.confirm != result["body_sha256"]:
        gates.append(
            (
                "pr.publish_unconfirmed",
                "confirm does not match the current draft's body_sha256, so this is not the text the user confirmed.",
                "Show the user the current draft, obtain an explicit yes, and pass that draft's body_sha256 from check.",
            )
        )
    push = "Push the branch after the user's confirmation and rerun."
    upstream: str | None = None
    try:
        git(repo, "symbolic-ref", "--quiet", "--short", "HEAD")
    except GitError:
        gates.append(("pr.branch_unpushed", "HEAD is detached, so there is no branch to open a PR from.", "Check out the PR branch and rerun."))
    else:
        try:
            upstream = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").strip()
        except GitError:
            gates.append(("pr.branch_unpushed", "the branch has no upstream.", push))
        else:
            try:
                upstream_head = git(repo, "rev-parse", "@{u}").strip()
            except GitError:
                upstream_head = ""
            if upstream_head != result["head"]:
                gates.append(
                    (
                        "pr.branch_unpushed",
                        f"upstream `{upstream}` is at `{upstream_head}`, not at HEAD `{result['head']}`.",
                        push,
                    )
                )
    if gates or upstream is None:
        return emit(gates, draft)

    remotes = git(repo, "remote").split()
    base_remote, base_branch = _strip_remote(args.base, remotes)
    head_remote, head_branch = _strip_remote(upstream, remotes)
    if base_remote is not None and base_remote != head_remote:
        return emit(
            [
                (
                    "pr.branch_unpushed",
                    f"the upstream remote `{head_remote}` differs from the base remote `{base_remote}`; "
                    "fork PRs are not supported.",
                    "Push the branch to the base's remote and rerun.",
                )
            ],
            draft,
        )
    if args.update:
        return _update(repo, draft, args.base, base_branch, head_branch, args.title)
    gh_argv = ["gh", "pr", "create", "--base", base_branch, "--head", head_branch, "--title", args.title, "--body-file", str(draft)]
    try:
        completed = run_gh(gh_argv, repo)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return emit([("pr.publish_failed", f"gh pr create did not complete: {exc}.", "Check gh installation and authentication, then rerun.")], draft)
    if completed.returncode:
        detail = (completed.stderr or "").strip() or (completed.stdout or "").strip()
        return emit([("pr.publish_failed", f"gh pr create failed: {detail}.", "Repair the reported gh problem, then rerun.")], draft)
    lines = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    print(json.dumps({"status": "opened", "url": lines[-1] if lines else ""}, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

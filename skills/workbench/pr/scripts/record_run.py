#!/usr/bin/env python3
"""Run one verification command and append its real result to the run log."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pr_contract import SKILL_ROOT, GitError, emit, head_commit, inside, is_clean  # noqa: E402


def _parse(argv: list[str]) -> tuple[str, str, list[str]] | None:
    repo: str | None = None
    runs: str | None = None
    args: list[str] = []
    index = 0
    while index < len(argv):
        flag = argv[index]
        if index + 1 >= len(argv) or flag not in {"--repo-root", "--runs", "--arg"}:
            return None
        value = argv[index + 1]
        if flag == "--repo-root":
            repo = value
        elif flag == "--runs":
            runs = value
        else:
            args.append(value)
        index += 2
    if repo is None or runs is None:
        return None
    return repo, runs, args


def main(argv: list[str] | None = None) -> int:
    parsed = _parse(list(sys.argv[1:] if argv is None else argv))
    if parsed is None:
        return emit(
            [
                (
                    "pr.record_usage",
                    "record takes --repo-root, --runs, and zero or more --arg values.",
                    "Pass each argv element of the command as its own --input arg=<value>.",
                )
            ],
            SKILL_ROOT / "scripts" / "record_run.py",
        )
    repo = Path(parsed[0]).resolve()
    runs = Path(parsed[1]).resolve()
    args = parsed[2]
    if inside(runs, repo) or inside(runs, SKILL_ROOT) or not runs.parent.is_dir():
        return emit(
            [
                (
                    "pr.runs_location",
                    "the run log must be outside the target repository and the installed skill, in an existing directory.",
                    "Pass a run log path in an existing directory outside the repository.",
                )
            ],
            runs,
        )
    if not args:
        return emit(
            [("pr.record_empty", "no command was given to record.", "Pass the command's argv as --input arg=<value> items.")],
            runs,
        )
    try:
        head = head_commit(repo)
        clean = is_clean(repo)
    except GitError as exc:
        return emit(
            [
                (
                    "pr.repository_unreadable",
                    f"cannot read the repository state: {exc}.",
                    "Run from a Git repository with at least one commit.",
                )
            ],
            runs,
        )
    try:
        completed = subprocess.run(
            args,
            cwd=repo,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        return emit(
            [
                (
                    "pr.record_launch_failed",
                    f"cannot start `{args[0]}`: {exc}.",
                    "Pass an executable that exists on PATH or as an absolute path.",
                )
            ],
            runs,
        )
    command = shlex.join(args)
    record = {"command": command, "exit_code": completed.returncode, "head": head, "clean": clean}
    with runs.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    output = (completed.stdout or "") + (completed.stderr or "")
    print(
        json.dumps(
            {**record, "output_tail": "\n".join(output.splitlines()[-40:])},
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

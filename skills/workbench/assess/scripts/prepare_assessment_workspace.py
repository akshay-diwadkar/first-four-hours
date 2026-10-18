#!/usr/bin/env python3
"""Prepare the repository-local .first-four-hours/assessments/<slug>/assessment.md workspace."""

from __future__ import annotations

import argparse
from pathlib import Path

from _script_support import run_action
from assess_contract import prepare_assessment_workspace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--slug", required=True)
    args = parser.parse_args(argv)

    def prepare() -> dict[str, object]:
        workspace = prepare_assessment_workspace(args.repo_root, args.slug)
        return {
            "slug": workspace.slug,
            "output_path": str(workspace.output_path),
            "relative_output_path": workspace.relative_output_path,
            "git_exclude": str(workspace.git_exclude) if workspace.git_exclude is not None else None,
            "git_ignored": workspace.git_ignored,
        }

    return run_action(prepare, phase="prepare")


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Preview, or post after confirmation, a checked findings assessment as one pull request comment."""

from __future__ import annotations

import argparse
from pathlib import Path

from _script_support import run_action
from assess_contract import publish_findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm", default=None)
    args = parser.parse_args(argv)
    return run_action(lambda: publish_findings(args.repo_root, args.output, args.confirm), phase="publish")


if __name__ == "__main__":
    raise SystemExit(main())

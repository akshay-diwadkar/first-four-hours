#!/usr/bin/env python3
"""Validate a temporary Assess bundle and atomically seal assessment.md."""

from __future__ import annotations

import argparse
from pathlib import Path

from _script_support import run_action
from assess_contract import seal_result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    return run_action(lambda: seal_result(args.repo_root, args.bundle, args.output), phase="run")


if __name__ == "__main__":
    raise SystemExit(main())

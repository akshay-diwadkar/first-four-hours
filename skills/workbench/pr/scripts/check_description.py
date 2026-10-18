#!/usr/bin/env python3
"""Check a PR description draft against the branch diff and the run log."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pr_contract import check_description, emit  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--draft", required=True)
    parser.add_argument("--runs", required=True)
    parser.add_argument("--base", required=True)
    args = parser.parse_args(argv)
    repo = Path(args.repo_root).resolve()
    draft = Path(args.draft).resolve()
    runs = Path(args.runs).resolve()
    problems, result = check_description(repo, draft, runs, args.base)
    if problems:
        return emit(problems, draft)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

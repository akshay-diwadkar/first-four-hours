#!/usr/bin/env python3
"""Synchronize portable deterministic-classification runtimes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tools" / "classification" / "runtime.py"


def targets() -> tuple[Path, ...]:
    return tuple(
        path.parent / "_classification_runtime.py"
        for path in sorted((ROOT / "skills").glob("*/*/scripts/classify_workflow.py"))
    )


def check() -> list[str]:
    source = SOURCE.read_bytes()
    return [f"Stale runtime projection: {target.relative_to(ROOT)}" for target in targets()
            if not target.is_file() or target.read_bytes() != source]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source = SOURCE.read_bytes()
    stale = [target for target in targets() if not target.is_file() or target.read_bytes() != source]
    if args.check:
        for target in stale:
            print(f"Stale classification runtime: {target.relative_to(ROOT)}", file=sys.stderr)
        return int(bool(stale))
    for target in stale:
        target.write_bytes(source)
        print(target.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

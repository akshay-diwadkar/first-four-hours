#!/usr/bin/env python3
"""Derive Examiner's standalone link check from Tutor's."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEARNING = ROOT / 'skills/learning'


def projections():
    yield LEARNING / 'tutor/scripts/check_links.py', LEARNING / 'examiner/scripts/check_links.py'


def check() -> list[str]:
    return [f"Stale learning link check projection: {target.relative_to(ROOT)}"
            for source, target in projections()
            if not target.is_file() or target.read_bytes() != source.read_bytes()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    stale = False
    for source, target in projections():
        data = source.read_bytes()
        if target.is_file() and target.read_bytes() == data:
            continue
        stale = True
        if args.check:
            print(f'Stale learning link check projection: {target.relative_to(ROOT)}', file=sys.stderr)
        else:
            target.write_bytes(data)
    return int(stale and args.check)


if __name__ == '__main__':
    raise SystemExit(main())

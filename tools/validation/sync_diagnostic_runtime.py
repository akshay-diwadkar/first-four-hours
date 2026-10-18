#!/usr/bin/env python3
"""Synchronize the repair-ready diagnostic runtime into executable skills."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tools" / "diagnostics" / "runtime.py"


def targets() -> tuple[Path, ...]:
    return tuple(
        skill_dir / "scripts" / "_diagnostic_contract.py"
        for domain_dir in sorted((ROOT / "skills").iterdir())
        if domain_dir.is_dir()
        for skill_dir in sorted(domain_dir.iterdir())
        if skill_dir.is_dir() and (skill_dir / "skill-protocol.json").is_file()
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
            print(f"Stale diagnostic runtime: {target.relative_to(ROOT)}", file=sys.stderr)
        return int(bool(stale))
    for target in stale:
        target.write_bytes(source)
        print(target.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

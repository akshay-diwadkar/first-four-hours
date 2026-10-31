#!/usr/bin/env python3
"""Synchronize the canonical learning runtime and templates into Tutor and Examiner."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "tools" / "learning"
LEARNING = ROOT / "skills" / "learning"
MAPPING: tuple[tuple[str, str], ...] = (
    ("runtime.py", "tutor/scripts/learning_files.py"),
    ("runtime.py", "examiner/scripts/learning_files.py"),
    ("templates/start-here.html", "tutor/templates/start-here.html"),
    ("templates/start-here.html", "examiner/templates/start-here.html"),
    ("templates/lesson.html", "tutor/templates/lesson.html"),
    ("templates/tutor-study-plan.html", "tutor/templates/study-plan.html"),
    ("templates/examiner-study-plan.html", "examiner/templates/study-plan.html"),
    ("templates/paper.html", "examiner/templates/paper.html"),
    ("templates/answer-key.html", "examiner/templates/answer-key.html"),
    ("templates/marking-scheme.html", "examiner/templates/marking-scheme.html"),
    ("templates/source-notes.html", "examiner/templates/source-notes.html"),
)


def targets() -> tuple[tuple[Path, Path], ...]:
    return tuple((SOURCE_ROOT / source, LEARNING / target) for source, target in MAPPING)


def _stale() -> list[tuple[Path, Path]]:
    return [(source, target) for source, target in targets()
            if not target.is_file() or target.read_bytes() != source.read_bytes()]


def check() -> list[str]:
    return [f"Stale learning runtime projection: {target.relative_to(ROOT).as_posix()}" for _, target in _stale()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = _stale()
    if args.check:
        for _, target in stale:
            print(f"Stale learning runtime projection: {target.relative_to(ROOT).as_posix()}", file=sys.stderr)
        return int(bool(stale))
    for source, target in stale:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        print(target.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

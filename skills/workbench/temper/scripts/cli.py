#!/usr/bin/env python3
"""Run this installed skill through the common CLI protocol."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

SKILL_ROOT = Path(__file__).resolve().parent.parent


def _runtime_main():
    for parent in SKILL_ROOT.parents:
        if (parent / "tools" / "skill_protocol" / "runtime.py").is_file():
            sys.path.insert(0, str(parent))
            from tools.skill_protocol.runtime import main

            return main
    from _skill_protocol_runtime import main

    return main


def main(argv: Sequence[str] | None = None) -> int:
    values = list(argv if argv is not None else sys.argv[1:])
    if "--skill-dir" not in values and not any(value.startswith("--skill-dir=") for value in values):
        values[:0] = ["--skill-dir", str(SKILL_ROOT)]
    return _runtime_main()(values, cli_path=Path(__file__), expected_skill_dir=SKILL_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())

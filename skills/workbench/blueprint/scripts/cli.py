#!/usr/bin/env python3
"""Run blueprint through the common stateful skill CLI protocol."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

SKILL_ROOT = Path(__file__).resolve().parent.parent


def _runtime_main():
    for parent in SKILL_ROOT.parents:
        runtime = parent / "tools" / "skill_protocol" / "runtime.py"
        if runtime.is_file():
            sys.path.insert(0, str(parent))
            from tools.skill_protocol.runtime import main

            return main
    from _skill_protocol_runtime import main

    return main


def _arguments(argv: Sequence[str]) -> list[str]:
    values = list(argv)
    if "--skill-dir" not in values and not any(value.startswith("--skill-dir=") for value in values):
        values[:0] = ["--skill-dir", str(SKILL_ROOT)]
    return values


if __name__ == "__main__":
    raise SystemExit(
        _runtime_main()(
            _arguments(sys.argv[1:]),
            cli_path=Path(__file__),
            expected_skill_dir=SKILL_ROOT,
        )
    )

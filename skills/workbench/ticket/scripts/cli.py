#!/usr/bin/env python3
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent


def _runtime_main():
    for parent in SKILL_ROOT.parents:
        if (parent / "tools" / "skill_protocol" / "runtime.py").is_file():
            sys.path.insert(0, str(parent))
            from tools.skill_protocol.runtime import main

            return main
    from _skill_protocol_runtime import main

    return main


if __name__ == "__main__":
    raise SystemExit(
        _runtime_main()(
            ["--skill-dir", str(SKILL_ROOT), *sys.argv[1:]],
            cli_path=Path(__file__),
            expected_skill_dir=SKILL_ROOT,
        )
    )

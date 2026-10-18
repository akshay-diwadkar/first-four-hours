#!/usr/bin/env python3
"""Run Construct through the common stateless skill protocol."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Sequence

SKILL_ROOT = Path(__file__).resolve().parent.parent


def _help_rows(manifest: dict[str, object]) -> list[str]:
    inputs = manifest.get("inputs", [])
    commands = manifest.get("commands", {})
    definitions = [item for item in inputs if isinstance(item, dict)] if isinstance(inputs, list) else []
    rows: list[str] = []
    for command in sorted(commands if isinstance(commands, dict) else {}):
        accepted = [item for item in definitions if not item.get("accepted_for") or command in item["accepted_for"]]
        required = sorted(
            str(item["name"])
            for item in accepted
            if item.get("required") is True or command in item.get("required_for", [])
        )
        optional = sorted(str(item["name"]) for item in accepted if str(item["name"]) not in required)
        parts = []
        if required:
            parts.append("required: " + ", ".join(required))
        if optional:
            parts.append("optional: " + ", ".join(optional))
        rows.append(f"{command}  ({'; '.join(parts)})" if parts else command)
    return rows


def _print_help() -> None:
    manifest = json.loads((SKILL_ROOT / "skill-protocol.json").read_text(encoding="utf-8"))
    print("usage: cli.py --repo-root REPO [--input NAME=VALUE] [--format human|json] COMMAND")
    print("\nConstruct stateless actions:")
    for row in _help_rows(manifest):
        print(f"  {row}")
    print("\nEach action is stateless; no run state is reconstructed or persisted.")
    print("Status accepts paired instruction/attempt context; the caller retains attempt history.")


def _runtime_main():
    for parent in SKILL_ROOT.parents:
        if (parent / "tools" / "skill_protocol" / "runtime.py").is_file():
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
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        _print_help()
        raise SystemExit(0)
    raise SystemExit(_runtime_main()(_arguments(sys.argv[1:]), cli_path=Path(__file__), expected_skill_dir=SKILL_ROOT))

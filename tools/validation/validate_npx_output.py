#!/usr/bin/env python3
"""Validate the grouped output produced by `npx skills add --list`."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import validate_repository as repository_validator

ANSI_ESCAPE_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
def expected_groups() -> dict[str, set[str]]:
    return {
        "First Four Hours": {
            skill.name
            for skill in repository_validator.discover_skills()
        },
    }


EXPECTED_GROUPS = expected_groups()


def read_output_text(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    return data.decode("utf-8-sig")


def normalized_lines(text: str) -> list[str]:
    clean = ANSI_ESCAPE_RE.sub("", text).replace("\r", "\n")
    return [line.strip().lstrip("|│").strip() for line in clean.splitlines() if line.strip()]


def validate_output(text: str) -> list[str]:
    lines = normalized_lines(text)
    groups = expected_groups()
    errors: list[str] = []
    expected_skill_count = sum(len(skills) for skills in groups.values())
    if not any(f"Found {expected_skill_count} skills" in line for line in lines):
        errors.append(f"npx output must report exactly {expected_skill_count} discovered skills")

    forbidden_groups = {"General", "Other", "Others", "Workbench Skills", "Sensemaking Skills", "Learning Skills"}
    present_forbidden = forbidden_groups.intersection(lines)
    if present_forbidden:
        errors.append(f"npx output contains fallback groups: {sorted(present_forbidden)}")

    group_positions: dict[str, int] = {}
    for group in groups:
        matches = [index for index, line in enumerate(lines) if line == group]
        if len(matches) != 1:
            errors.append(f"npx output must contain the {group!r} heading exactly once")
        else:
            group_positions[group] = matches[0]

    if len(group_positions) != len(EXPECTED_GROUPS):
        return errors

    ordered_groups = sorted(EXPECTED_GROUPS, key=lambda group: group_positions[group])
    for index, group in enumerate(ordered_groups):
        start = group_positions[group]
        end = group_positions[ordered_groups[index + 1]] if index + 1 < len(ordered_groups) else len(lines)
        for skill in groups[group]:
            positions = [position for position, line in enumerate(lines) if line == skill]
            if len(positions) != 1:
                errors.append(f"npx output must contain skill {skill!r} exactly once")
            elif not start < positions[0] < end:
                errors.append(f"npx output places {skill!r} outside {group!r}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Captured npx list output")
    args = parser.parse_args()
    errors = validate_output(read_output_text(args.output))
    if errors:
        print("npx output validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    groups = expected_groups()
    count = sum(len(skills) for skills in groups.values())
    print(f"npx output validation passed for {count} skills in {len(groups)} groups.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

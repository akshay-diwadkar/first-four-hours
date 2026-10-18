#!/usr/bin/env python3
"""Validate delegation dispositions and sync projected protocols to shared doctrine."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "SKILL_PHILOSOPHY.md"
DISPOSITIONS = Path(__file__).with_name("delegation-dispositions.json")
SPAN_START = "### Delegation: preserve authority, bound labor"
SPAN_END = "## Design Doctrine"
BEGIN_MARKER = "<!-- delegation-projection:begin -->"
END_MARKER = "<!-- delegation-projection:end -->"
REQUIRED_FIELDS = {
    "skill",
    "mode",
    "owner",
    "lifecycle",
    "workers",
    "specialists",
    "writes",
    "rationale",
}


def canonical_text(text):
    return " ".join(text.split())


def doctrine_span():
    text = SOURCE.read_text(encoding="utf-8")
    start = text.index(SPAN_START)
    end = text.index(SPAN_END)
    return text[start:end].rstrip() + "\n"


def load_dispositions():
    payload = json.loads(DISPOSITIONS.read_text(encoding="utf-8"))
    entries = payload.get("dispositions")
    if not isinstance(entries, list):
        raise ValueError("delegation dispositions must contain a dispositions list")

    by_skill = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("each delegation disposition must be an object")
        missing = REQUIRED_FIELDS - set(entry)
        if missing:
            raise ValueError(f"delegation disposition is missing {', '.join(sorted(missing))}: {entry.get('skill')}")
        skill = entry["skill"]
        if not isinstance(skill, str) or not skill:
            raise ValueError("each delegation disposition requires a non-empty skill")
        if skill in by_skill:
            raise ValueError(f"duplicate delegation disposition: {skill}")
        if "pointer_contract" in entry:
            raise ValueError(
                f"delegation disposition must not declare retired pointer_contract receipts; remove the pointer_contract object: {skill}"
            )
        if entry["mode"] not in {"projected", "direct"}:
            raise ValueError(f"unsupported delegation disposition for {skill}: {entry['mode']}")
        if entry["mode"] == "projected":
            if not isinstance(entry.get("protocol"), str):
                raise ValueError(f"projected delegation disposition requires protocol: {skill}")
        if entry["mode"] == "direct":
            if "protocol" in entry:
                raise ValueError(f"direct delegation disposition must not declare protocol: {skill}")
        by_skill[skill] = entry

    public_skills = {path.parent.name for path in (ROOT / "skills").glob("*/*/SKILL.md")}
    if set(by_skill) != public_skills:
        missing = sorted(public_skills - set(by_skill))
        stale = sorted(set(by_skill) - public_skills)
        raise ValueError(f"delegation disposition inventory mismatch; missing={missing}, stale={stale}")
    return by_skill


def projected_dispositions():
    return {name: entry for name, entry in load_dispositions().items() if entry["mode"] == "projected"}


def marker_bounds(text: str, path: Path):
    begin = text.find(BEGIN_MARKER)
    end = text.find(END_MARKER)
    if (
        begin < 0
        or end < 0
        or end < begin
        or text.find(BEGIN_MARKER, begin + 1) >= 0
        or text.find(END_MARKER, end + 1) >= 0
    ):
        raise ValueError(f"delegation protocol must carry exactly one ordered marker pair: {path}")
    return begin, end


def projection_region(path: Path):
    text = path.read_text(encoding="utf-8")
    begin, end = marker_bounds(text, path)
    return text[begin + len(BEGIN_MARKER) : end].strip()


def projected(path: Path):
    """Return the file with the marker region refreshed, or None when unchanged."""
    text = path.read_text(encoding="utf-8")
    begin, end = marker_bounds(text, path)
    head = text[: begin + len(BEGIN_MARKER)]
    tail = text[end:]
    updated = f"{head}\n{doctrine_span()}{tail}"
    if updated == text:
        return None
    return updated


def check() -> list[str]:
    errors = []
    try:
        dispositions = load_dispositions()
        for name, entry in dispositions.items():
            if entry["mode"] == "direct":
                continue
            path = ROOT / entry["protocol"]
            if not path.is_file():
                errors.append(f"missing delegation protocol for {name}: {entry['protocol']}")
            elif projected(path) is not None:
                errors.append(f"stale delegation projection: {entry['protocol']}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    try:
        dispositions = load_dispositions()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    stale = False
    invalid = False
    for name, entry in dispositions.items():
        if entry["mode"] == "direct":
            continue
        relative = entry["protocol"]
        path = ROOT / relative
        if not path.is_file():
            print(f"missing delegation protocol for {name}: {relative}", file=sys.stderr)
            invalid = True
            continue
        try:
            updated = projected(path)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            invalid = True
            continue
        if updated is None:
            continue
        stale = True
        if args.check:
            print(f"stale delegation projection: {relative}", file=sys.stderr)
        else:
            path.write_text(updated.replace("\r\n", "\n"), encoding="utf-8", newline="")
            print(relative)
    if invalid or (stale and args.check):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

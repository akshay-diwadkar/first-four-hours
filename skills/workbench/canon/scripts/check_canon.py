#!/usr/bin/env python3
"""Check that one canon.md holds every agreed part, printing each missing or malformed part."""

from __future__ import annotations

import argparse
import datetime
import json
import re
from pathlib import Path

REQUIRED: list[tuple[str, list[str]]] = [
    ("Character", ["Thesis", "Personality", "Voice"]),
    ("Media", ["Website", "App", "Document", "Slide deck"]),
    ("System", ["Type", "Colour", "Spacing", "Components", "Motion", "Imagery"]),
    ("Viewing contexts", []),
    ("States", ["Empty", "Error", "Loading", "Dense data", "Long tables", "Charts", "Footnotes"]),
    ("Banned", []),
    ("Samples", []),
    ("Governs", []),
    ("Change log", []),
]
RULE_LEAVES = {"Viewing contexts", "Banned"}
HEADING_RE = re.compile(r"^(#{1,6}) (.*\S)\s*$")
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]*)\)")
SPAN_RE = re.compile(r"`([^`]*)`")
CHANGE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}): (.*?) Reason:(.*)$")

SAMPLES_MESSAGE = "Samples: entry {n} must be one relative link to a file inside the canon folder"
GOVERNS_MESSAGE = "Governs: entry {n} must be one relative path or glob in backticks"
CHANGE_MESSAGE = 'Change log: entry {n} must read "YYYY-MM-DD: what changed Reason: why"'
RULE_MESSAGE = '{path}: entry {n} must state a rule and then "Reason: why"'

Line = tuple[str | None, str | None, str]


def visible_lines(text: str) -> list[Line]:
    """Return each visible non-heading line with its section and subsection, plus heading markers."""
    rows: list[Line] = []
    fence: str | None = None
    section: str | None = None
    subsection: str | None = None
    for line in re.split(r"\r\n|\r|\n", text):
        stripped = line.lstrip()
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            continue
        match = HEADING_RE.match(line)
        if match:
            level = len(match.group(1))
            name = match.group(2).rstrip()
            if level == 1:
                section, subsection = None, None
            elif level == 2:
                section, subsection = name, None
                rows.append(("#2", name, ""))
            elif level == 3:
                subsection = name
                rows.append(("#3", name, section or ""))
            continue
        rows.append((section, subsection, line))
    return rows


def entries(lines: list[str]) -> list[str]:
    found: list[str] = []
    current: list[str] | None = None
    for line in lines:
        if line.startswith("- "):
            current = [line[2:].strip()]
            found.append("")
        elif current is not None and line.strip() and line[:1] in (" ", "\t"):
            current.append(line.strip())
        else:
            current = None
            continue
        found[-1] = " ".join(part for part in current if part)
    return found


def _safe_relative(target: str) -> bool:
    return bool(target) and not target.startswith("/") and "\\" not in target and ":" not in target and ".." not in target.split("/")


def check_content(path: str, kind: str, lines: list[str], canon_dir: Path) -> list[str]:
    if kind == "thesis":
        return [] if any(line.strip() for line in lines) else [f"{path}: has no text"]
    items = entries(lines)
    if not items:
        return [f"{path}: has no entries"]
    problems: list[str] = []
    for number, text in enumerate(items, start=1):
        if kind == "rule":
            rule, marker, reason = text.partition("Reason:")
            if not marker or not rule.strip() or not reason.strip():
                problems.append(RULE_MESSAGE.format(path=path, n=number))
        elif kind == "samples":
            links = LINK_RE.findall(text)
            ok = len(links) == 1 and _safe_relative(links[0])
            if ok:
                try:
                    resolved = (canon_dir / links[0]).resolve()
                    ok = resolved.is_file() and resolved.is_relative_to(canon_dir)
                except (OSError, ValueError):
                    ok = False
            if not ok:
                problems.append(SAMPLES_MESSAGE.format(n=number))
        elif kind == "governs":
            spans = SPAN_RE.findall(text)
            if len(spans) != 1 or not _safe_relative(spans[0].strip()):
                problems.append(GOVERNS_MESSAGE.format(n=number))
        elif kind == "changes":
            match = CHANGE_RE.match(text)
            ok = match is not None and bool(match.group(2).strip()) and bool(match.group(3).strip())
            if ok and match is not None:
                try:
                    datetime.date.fromisoformat(match.group(1))
                except ValueError:
                    ok = False
            if not ok:
                problems.append(CHANGE_MESSAGE.format(n=number))
    return problems


def kind_of(section: str, subsection: str | None) -> str:
    if subsection == "Thesis":
        return "thesis"
    if subsection == "Personality":
        return "text"
    if subsection is not None or section in RULE_LEAVES:
        return "rule"
    return {"Samples": "samples", "Governs": "governs", "Change log": "changes"}[section]


def check(text: str, canon_dir: Path) -> list[str]:
    rows = visible_lines(text)
    section_counts: dict[str, int] = {}
    subsection_counts: dict[tuple[str, str], int] = {}
    for marker, name, parent in rows:
        if marker == "#2" and name is not None:
            section_counts[name] = section_counts.get(name, 0) + 1
        elif marker == "#3" and name is not None and parent:
            subsection_counts[(parent, name)] = subsection_counts.get((parent, name), 0) + 1
    content = [(section, subsection, line) for section, subsection, line in rows if section not in ("#2", "#3")]
    problems: list[str] = []
    for section, children in REQUIRED:
        count = section_counts.get(section, 0)
        if count == 0:
            problems.append(f"missing section: {section}")
            problems.extend(f"missing section: {section} > {child}" for child in children)
            continue
        if count > 1:
            problems.append(f"duplicate section: {section}")
            continue
        if not children:
            lines = [line for owner, _sub, line in content if owner == section]
            problems.extend(check_content(section, kind_of(section, None), lines, canon_dir))
            continue
        for child in children:
            path = f"{section} > {child}"
            child_count = subsection_counts.get((section, child), 0)
            if child_count == 0:
                problems.append(f"missing section: {path}")
            elif child_count > 1:
                problems.append(f"duplicate section: {path}")
            else:
                lines = [line for owner, sub, line in content if owner == section and sub == child]
                problems.extend(check_content(path, kind_of(section, child), lines, canon_dir))
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canon", required=True)
    args = parser.parse_args()
    path = Path(args.canon)
    try:
        if not path.is_file():
            raise ValueError
        text = path.read_bytes().decode("utf-8")
    except (OSError, ValueError):
        print(f"canon must be a UTF-8 text file: {args.canon}")
        return 1
    text = text.removeprefix("﻿")
    resolved = path.resolve()
    problems = check(text, resolved.parent)
    if problems:
        print("\n".join(problems))
        return 1
    print(json.dumps({"canon": str(resolved), "valid": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

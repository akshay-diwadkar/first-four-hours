#!/usr/bin/env python3
"""Project the filesystem-owned skill domains into distribution metadata."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "validation"))

import validate_repository as repository_validator  # noqa: E402


def groups() -> dict[str, list[str]]:
    discovered = repository_validator.discover_skills()
    return {
        f"{domain}-skills": [
            f"./skills/{skill.parent.name}/{skill.name}"
            for skill in discovered
            if skill.parent.name == domain
        ]
        for domain in ("workbench", "sensemaking", "learning")
    }


def _projected_marketplace(payload: dict[str, object]) -> dict[str, object]:
    projected = dict(payload)
    raw_plugins = cast(list[object], payload.get("plugins", []))
    existing = {
        str(plugin.get("name")): plugin
        for plugin in raw_plugins
        if isinstance(plugin, dict) and isinstance(plugin.get("name"), str)
    }
    descriptions = {
        "workbench-skills": "Skills for understanding, designing, planning, implementing, and auditing codebases.",
        "sensemaking-skills": "Skills for reasoning, exploration, communication, and coordination.",
        "learning-skills": "Skills for building a person's own knowledge and ability in any subject.",
    }
    plugins: list[dict[str, object]] = []
    for name, paths in groups().items():
        base = dict(existing.get(name, {}))
        base.update({"name": name, "source": "./", "description": descriptions[name], "skills": paths})
        plugins.append(base)
    projected["description"] = "Skills for repository-grounded project work and decision readiness, and for learning any subject."
    projected["plugins"] = plugins
    return projected


def validate(readme: Path, marketplace: Path) -> list[str]:
    errors: list[str] = []
    try:
        payload = json.loads(marketplace.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"marketplace unreadable: {exc}"]
    if payload != _projected_marketplace(payload):
        errors.append(".claude-plugin/marketplace.json is not derived from the current domain tree")
    try:
        text = readme.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"README unreadable: {exc}"]
    if "### Workbench" not in text or "### Sensemaking" not in text or "### Learning" not in text:
        errors.append("README.md must explain Workbench, Sensemaking, and Learning")
    for path in sum(groups().values(), []):
        link = path.removeprefix("./")
        if f"{link}/SKILL.md" not in text:
            errors.append(f"README.md is missing the active skill link {link}/SKILL.md")
    return errors


def check() -> list[str]:
    return validate(ROOT / "README.md", ROOT / ".claude-plugin" / "marketplace.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.write and not args.check:
        parser.error("choose --write or --check")
    marketplace = ROOT / ".claude-plugin" / "marketplace.json"
    readme = ROOT / "README.md"
    if args.write:
        payload = json.loads(marketplace.read_text(encoding="utf-8"))
        marketplace.write_text(json.dumps(_projected_marketplace(payload), indent=2) + "\n", encoding="utf-8")
    errors = validate(readme, marketplace)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("skill catalog projection: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

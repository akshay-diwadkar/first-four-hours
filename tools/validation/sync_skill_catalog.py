#!/usr/bin/env python3
"""Project the filesystem-owned skill domains into distribution metadata and check the README and docs skill catalogs against them."""

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


def validate_skill_pages(index_text: str, page_stems: set[str], domains: dict[str, list[str]]) -> list[str]:
    errors: list[str] = []
    text = "\n" + index_text.replace("\r\n", "\n")
    for domain, names in domains.items():
        heading = f"\n## {domain}\n"
        start = text.find(heading)
        if start < 0:
            errors.append(f"docs/skills/README.md must have a '## {domain}' section")
        else:
            body_start = start + len(heading)
            end = text.find("\n## ", body_start - 1)
            section = text[body_start:end] if end >= 0 else text[body_start:]
            for name in names:
                if f"]({name}.md)" not in section:
                    errors.append(f"docs/skills/README.md is missing the {domain} skill page link {name}.md")
        for name in names:
            if name not in page_stems:
                errors.append(f"docs/skills/{name}.md is missing for the active skill {name}")
    active = {name for names in domains.values() for name in names}
    for stem in sorted(page_stems - active):
        errors.append(f"docs/skills/{stem}.md documents no active skill")
    return errors


def check() -> list[str]:
    errors = validate(ROOT / "README.md", ROOT / ".claude-plugin" / "marketplace.json")
    pages_dir = ROOT / "docs" / "skills"
    try:
        index_text = (pages_dir / "README.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return errors + [f"docs/skills/README.md unreadable: {exc}"]
    page_stems = {page.stem for page in pages_dir.glob("*.md") if page.name != "README.md"}
    domains = {
        key.removesuffix("-skills").title(): [path.rsplit("/", 1)[1] for path in paths]
        for key, paths in groups().items()
    }
    return errors + validate_skill_pages(index_text, page_stems, domains)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.write and not args.check:
        parser.error("choose --write or --check")
    marketplace = ROOT / ".claude-plugin" / "marketplace.json"
    if args.write:
        payload = json.loads(marketplace.read_text(encoding="utf-8"))
        marketplace.write_text(json.dumps(_projected_marketplace(payload), indent=2) + "\n", encoding="utf-8")
    errors = check()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("skill catalog projection: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

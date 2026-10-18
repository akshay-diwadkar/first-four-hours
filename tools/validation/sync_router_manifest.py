#!/usr/bin/env python3
"""Project surviving skills' SKILL.md frontmatter into Router's capability manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "skills" / "sensemaking" / "router" / "assets" / "capabilities.json"


def projection() -> str:
    import validate_repository as repository  # lazy: validate_repository.main imports this module

    capabilities: list[dict[str, str]] = []
    for skill_dir in repository.discover_skills():
        if skill_dir.name == "router":
            continue
        frontmatter = repository._frontmatter(skill_dir) or ""
        description = repository._frontmatter_description(frontmatter) or ""
        entry = {
            "name": skill_dir.name,
            "invocation": repository._frontmatter_invocation_mode(frontmatter) or "",
            "description": description,
        }
        authority = repository._metadata_field(frontmatter, "implicit-authority")
        if authority is not None:
            entry["implicit_authority"] = authority
        capabilities.append(entry)
    capabilities.sort(key=lambda entry: entry["name"])
    payload = {"generated_by": "tools/validation/sync_router_manifest.py", "capabilities": capabilities}
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def check() -> list[str]:
    current = TARGET.read_text(encoding="utf-8") if TARGET.is_file() else None
    if current != projection():
        return [
            f"Stale router capability manifest: {TARGET.relative_to(ROOT).as_posix()}; "
            "run python tools/validation/sync_router_manifest.py"
        ]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail instead of rewriting a stale manifest.")
    args = parser.parse_args()
    if args.check:
        errors = check()
        for error in errors:
            print(error, file=sys.stderr)
        if errors:
            return 1
        print("router capability manifest: ok")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_bytes(projection().encode("utf-8"))
    print("router capability manifest: written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

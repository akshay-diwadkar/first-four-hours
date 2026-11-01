#!/usr/bin/env python3
"""Reject scripted repository discovery from skill runtimes.

This is development tooling and may inspect the repository.  Runtime code is
allowed to validate only paths explicitly supplied in an artifact or command.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills"
EXCEPTIONS = ROOT / "tools" / "validation" / "runtime-discovery-exceptions.json"
FORBIDDEN = {
    "path.rglob": re.compile(r"\.rglob\s*\("),
    "recursive-glob": re.compile(r"\.glob\s*\(\s*['\"]\*\*/"),
    "os.walk": re.compile(r"\bos\.walk\s*\("),
    "git-ls-files": re.compile(r"(?:git[\s'\",]+ls-files|[\"']ls-files[\"'])"),
    "git-grep": re.compile(r"(?:git[\s'\",]+grep|[\"']grep[\"'])"),
    "recursive-rg": re.compile(r"(?:rg|grep)\s+(?:-[A-Za-z]*r|--recursive)"),
}


def _exceptions() -> set[str]:
    if not EXCEPTIONS.exists():
        return set()
    data = json.loads(EXCEPTIONS.read_text(encoding="utf-8"))
    return set(data.get("approved", []))


def validate() -> list[str]:
    approved = _exceptions()
    violations: list[str] = []
    for path in SKILLS.glob("*/*/scripts/*.py"):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT).as_posix()
        for name, pattern in FORBIDDEN.items():
            if pattern.search(text) and f"{relative}:{name}" not in approved:
                violations.append(f"{relative}: forbidden runtime discovery ({name})")
    return violations


def main() -> int:
    violations = validate()
    if violations:
        print("\n".join(violations), file=sys.stderr)
        return 1
    print("runtime discovery policy: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

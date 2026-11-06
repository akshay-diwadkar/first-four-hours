"""Canonical Scribe artifact names and path checks."""

from __future__ import annotations

import re
from pathlib import Path

BUNDLE_FILENAME = "document-bundle.json"
AUDIT_FILENAME = "scribe-audit.md"
ARTIFACT_ROOT = ".first-four-hours"
INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
WORKSPACE_PARTS = (ARTIFACT_ROOT, "scribes")
WORKSPACE_DIR = "/".join(WORKSPACE_PARTS)
GAP_MARKER = re.compile(r"\[GAP:[ \t]*(?P<missing>[^;\]\n]*[^\s;\]])[ \t]*;[ \t]*owner:[ \t]*(?P<owner>[^\]\n]*[^\s\]])[ \t]*\]", re.IGNORECASE)
GAP_OPENING = re.compile(r"\[GAP:", re.IGNORECASE)


def require_canonical_name(path: Path, expected: str) -> Path:
    """Reject retired or alternate artifact names instead of translating them."""
    if path.name != expected:
        raise ValueError(f"Scribe requires {expected}; received {path.name}")
    return path

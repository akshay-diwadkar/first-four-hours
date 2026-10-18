"""Canonical Scribe document artifact names and path checks."""

from __future__ import annotations

from pathlib import Path

DOCUMENT_FILENAME = "document.md"
BUNDLE_FILENAME = "document-bundle.json"
ARTIFACT_ROOT = ".first-four-hours"
WORKSPACE_PARTS = (ARTIFACT_ROOT, "document-bundles")
WORKSPACE_DIR = "/".join(WORKSPACE_PARTS)


def require_canonical_name(path: Path, expected: str) -> Path:
    """Reject retired or alternate artifact names instead of translating them."""
    if path.name != expected:
        raise ValueError(f"Scribe requires {expected}; received {path.name}")
    return path

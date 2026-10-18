"""Canonical repair-ready diagnostic contract."""

from .runtime import (
    CATEGORIES,
    REQUIRED_FIELDS,
    SEVERITIES,
    Diagnostic,
    canonical_json,
    command,
    is_canonical,
    normalize_diagnostic,
    sorted_diagnostics,
)

__all__ = [
    "CATEGORIES",
    "REQUIRED_FIELDS",
    "SEVERITIES",
    "Diagnostic",
    "canonical_json",
    "command",
    "is_canonical",
    "normalize_diagnostic",
    "sorted_diagnostics",
]

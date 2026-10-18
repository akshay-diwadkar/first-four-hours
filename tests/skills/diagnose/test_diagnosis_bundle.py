#!/usr/bin/env python3
"""Tests for the minimal versioned diagnosis bundle contract."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

DEV_DIR = Path(__file__).resolve().parent
REPO_ROOT = DEV_DIR.parents[2]
RUNTIME_SCRIPTS = REPO_ROOT / "skills" / "workbench" / "diagnose" / "scripts"
for import_path in (RUNTIME_SCRIPTS, DEV_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

import diagnosis_bundle  # noqa: E402

TEMPLATE_PATH = REPO_ROOT / "skills" / "workbench" / "diagnose" / "templates" / "diagnosis-bundle.json"


def valid_bundle() -> dict[str, Any]:
    raw = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


class DiagnosisBundleTests(unittest.TestCase):
    def assert_error_contains(self, bundle: dict[str, Any], expected: str) -> None:
        errors = diagnosis_bundle.validate_diagnosis_bundle(bundle)
        self.assertTrue(any(expected in error for error in errors), errors)


    def test_demonstrated_cause_requires_executed_evidence(self):
        bundle = valid_bundle()
        bundle["findings"][0]["cause_status"] = "demonstrated"
        self.assert_error_contains(bundle, "requires a ran command or capture evidence record")


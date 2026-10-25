from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

import pytest

from tools.validation.git_test_support import seed_git

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "sensemaking" / "scribe" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


CHECKS = ("required_facts", "integrity_literals", "procedures", "warnings", "recovery_steps", "prerequisites", "branches")


@pytest.fixture
def document_case(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    """A committed source in a Git target, two documents outside it, and a bundle binding both to that source."""
    repo = tmp_path / "repo"
    seed_git(repo, {"source.txt": "The service starts with port 8080.\n"})
    documents = tmp_path / "documents"
    documents.mkdir()
    for name in ("runbook.md", "reference.md"):
        (documents / name).write_text("# Procedure\n\nRun the service.\n", encoding="utf-8")
    bundle = {
        "contract_version": "1.0.0",
        "glossary": {
            "terms": [],
            "abbreviations": {},
            "action_verbs": [],
            "phrasal_verbs": [],
            "hazardous_actions": [],
        },
        "sources": [
            {
                "id": "SRC-1",
                "path": "source.txt",
                "sha256": hashlib.sha256((repo / "source.txt").read_bytes()).hexdigest(),
                "authority": "service contract",
            }
        ],
        "documents": [
            {"path": str(documents / name), "profile": "strict", **{check: [] for check in CHECKS}}
            for name in ("runbook.md", "reference.md")
        ],
    }
    return repo, documents, bundle

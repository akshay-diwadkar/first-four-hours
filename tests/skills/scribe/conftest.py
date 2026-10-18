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


@pytest.fixture
def document_case(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    """A committed source in a Git target, a document outside it, and a source-bound bundle."""
    repo = tmp_path / "repo"
    seed_git(repo, {"source.txt": "The service starts with port 8080.\n"})
    document = tmp_path / "document.md"
    document.write_text("# Procedure\n\nRun the service.\n", encoding="utf-8")
    bundle = {
        "contract_version": "1.0.0",
        "profile": "strict",
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
        "required_facts": [],
        "integrity_literals": [],
        "procedures": [],
        "warnings": [],
        "recovery_steps": [],
        "prerequisites": [],
        "branches": [],
    }
    return repo, document, bundle

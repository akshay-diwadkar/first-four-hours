from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from check_document import validate_document


def types(text: str, bundle: dict[str, Any], repo: Path) -> set[str]:
    return {item["type"] for item in validate_document(text, bundle, repo)}


def test_stale_or_support_namespace_source_is_rejected(document_case: tuple[Path, Path, dict[str, Any]]) -> None:
    repo, document, base = document_case
    text = document.read_text(encoding="utf-8")
    assert types(text, base, repo) == set()
    stale = copy.deepcopy(base)
    stale["sources"][0]["sha256"] = "0" * 64
    assert "source_hash_mismatch" in types(text, stale, repo)
    support = copy.deepcopy(base)
    support["sources"].append(
        {"id": "SRC-2", "path": ".first-four-hours/document-bundles/runbook/notes.md", "sha256": "0" * 64, "authority": "support state"}
    )
    assert "namespace_source" in types(text, support, repo)
    undeclared = copy.deepcopy(base)
    undeclared["required_facts"] = [{"id": "FACT-1", "claim": "Run the service.", "source_ids": ["SRC-1", "SRC-9"]}]
    undeclared["integrity_literals"] = [{"id": "LIT-1", "kind": "value", "literal": "service", "source_ids": ["SRC-1"]}]
    errors = validate_document(text, undeclared, repo)
    assert [(item["type"], item["location"]) for item in errors] == [("undeclared_source", "source SRC-9")]

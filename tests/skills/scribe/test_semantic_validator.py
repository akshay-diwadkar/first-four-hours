from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from check_document import validate_document, validate_sources


def types(bundle: dict[str, Any], repo: Path) -> set[str]:
    return {item["type"] for item in validate_sources(bundle, repo)}


def test_stale_or_audit_namespace_source_is_rejected(document_case: tuple[Path, Path, dict[str, Any]]) -> None:
    repo, documents, base = document_case
    text = (documents / "runbook.md").read_text(encoding="utf-8")
    assert types(base, repo) == set()
    assert validate_document(text, base["documents"][0]) == []
    stale = copy.deepcopy(base)
    stale["sources"][0]["sha256"] = "0" * 64
    assert "source_hash_mismatch" in types(stale, repo)
    report = copy.deepcopy(base)
    report["sources"].append(
        {"id": "SRC-2", "path": ".first-four-hours/scribes/runbook/scribe-audit.md", "sha256": "0" * 64, "authority": "audit report"}
    )
    assert "namespace_source" in types(report, repo)
    # A fact in the second document citing an undeclared source is still found.
    undeclared = copy.deepcopy(base)
    undeclared["documents"][1]["required_facts"] = [
        {"id": "FACT-1", "claim": "Run the service.", "source_ids": ["SRC-1", "SRC-9"]}
    ]
    undeclared["documents"][1]["integrity_literals"] = [
        {"id": "LIT-1", "kind": "value", "literal": "service", "source_ids": ["SRC-1"]}
    ]
    errors = validate_sources(undeclared, repo)
    assert [(item["type"], item["location"]) for item in errors] == [("undeclared_source", "source SRC-9")]

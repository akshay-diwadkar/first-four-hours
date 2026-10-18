#!/usr/bin/env python3
"""Audit document.md read-only against its source-bound bundle; unusable source evidence blocks the audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from _diagnostic_contract import normalize_diagnostic
from _document_contract import DOCUMENT_FILENAME, WORKSPACE_DIR, require_canonical_name
from bundle_workspace import WorkspaceError, in_namespace, locate_bundle
from check_document import load_bundle, repair_diagnostics, validate_document
from check_document_language import collect_diagnostics


def audit(repo_root: Path, slug: str, document: Path) -> tuple[int, dict[str, Any]]:
    root = repo_root.resolve()
    require_canonical_name(document, DOCUMENT_FILENAME)
    bundle_path, ignored = locate_bundle(root, slug)
    target = document.resolve()
    if in_namespace(root, target):
        raise WorkspaceError("namespace_document", f"{DOCUMENT_FILENAME} is the deliverable; keep it outside {WORKSPACE_DIR}/")
    bundle = load_bundle(bundle_path)
    data = target.read_bytes()
    text = data.decode("utf-8")
    semantic = validate_document(text, bundle, root)
    integrity = [item for item in semantic if item["location"].startswith("source ")]
    if integrity:
        return 1, {"status": "blocked", "diagnostics": repair_diagnostics([], integrity, phase="audit", document=target)}
    language = collect_diagnostics(text, bundle["profile"], bundle["glossary"])
    findings = repair_diagnostics(language, semantic, phase="audit", document=target)
    return 0, {
        "status": "complete",
        "document_sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
        "material_findings": any(item["severity"] in {"error", "critical"} for item in findings),
        "findings": findings,
        "namespace_ignored": ignored,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("document", type=Path)
    args = parser.parse_args(argv)
    try:
        status, payload = audit(args.repo_root, args.slug, args.document)
    except WorkspaceError as exc:
        status, payload = 2, {
            "status": "blocked",
            "diagnostics": [
                normalize_diagnostic(
                    {"code": exc.code, "category": "unsafe_state", "message": str(exc), "required_action": str(exc)},
                    skill="scribe",
                    phase="audit",
                    artifact=WORKSPACE_DIR,
                    path=args.repo_root,
                )
            ],
        }
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as exc:
        status, payload = 2, {
            "status": "blocked",
            "diagnostics": [
                normalize_diagnostic(
                    {"code": "invalid_input", "category": "malformed_input", "message": str(exc), "required_action": str(exc)},
                    skill="scribe",
                    phase="audit",
                    artifact="input",
                    path=args.document,
                )
            ],
        }
    print(json.dumps(payload, indent=2))
    return status


if __name__ == "__main__":
    raise SystemExit(main())

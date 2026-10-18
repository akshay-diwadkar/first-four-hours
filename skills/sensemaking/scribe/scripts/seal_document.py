#!/usr/bin/env python3
"""Check document.md against its source-bound bundle without writing any file."""

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


def check(repo_root: Path, slug: str, document: Path) -> tuple[int, dict[str, Any]]:
    root = repo_root.resolve()
    require_canonical_name(document, DOCUMENT_FILENAME)
    bundle_path, ignored = locate_bundle(root, slug)
    target = document.resolve()
    if in_namespace(root, target):
        raise WorkspaceError("namespace_document", f"{DOCUMENT_FILENAME} is the deliverable; keep it outside {WORKSPACE_DIR}/")
    bundle = load_bundle(bundle_path)
    data = target.read_bytes()
    text = data.decode("utf-8")
    language = collect_diagnostics(text, bundle["profile"], bundle["glossary"])
    semantic = validate_document(text, bundle, root)
    blocking = [item for item in language if item["severity"] == "error"]
    warnings = repair_diagnostics(
        [item for item in language if item["severity"] != "error"], [], phase="write", document=target
    )
    common = {"bundle": str(bundle_path), "namespace_ignored": ignored, "warnings": warnings}
    if blocking or semantic:
        return 1, {
            "status": "blocked",
            "diagnostics": repair_diagnostics(blocking, semantic, phase="write", document=target),
            **common,
        }
    return 0, {
        "status": "complete",
        "document": str(target),
        "document_sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
        **common,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("document", type=Path)
    args = parser.parse_args(argv)
    try:
        status, payload = check(args.repo_root, args.slug, args.document)
    except WorkspaceError as exc:
        status, payload = 2, {
            "status": "blocked",
            "diagnostics": [
                normalize_diagnostic(
                    {"code": exc.code, "category": "unsafe_state", "message": str(exc), "required_action": str(exc)},
                    skill="scribe",
                    phase="write",
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
                    phase="write",
                    artifact="input",
                    path=args.document,
                )
            ],
        }
    print(json.dumps(payload, indent=2))
    return status


if __name__ == "__main__":
    raise SystemExit(main())

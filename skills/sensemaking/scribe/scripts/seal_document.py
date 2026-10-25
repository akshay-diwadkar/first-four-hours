#!/usr/bin/env python3
"""Check every document a source-bound bundle lists without writing any file."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from _diagnostic_contract import normalize_diagnostic
from bundle_workspace import WorkspaceError
from check_document import inspect_bundle, repair_diagnostics


def check(repo_root: Path, bundle_path: Path) -> tuple[int, dict[str, Any]]:
    sources, records = inspect_bundle(repo_root, bundle_path)
    diagnostics = repair_diagnostics([], sources, phase="write", path=bundle_path)
    warnings: list[dict[str, Any]] = []
    documents = []
    for record in records:
        blocking = [item for item in record["language"] if item["severity"] == "error"]
        others = [item for item in record["language"] if item["severity"] != "error"]
        diagnostics += repair_diagnostics(
            blocking, record["semantic"], phase="write", path=record["path"], document=record["path"]
        )
        warnings += repair_diagnostics(others, [], phase="write", path=record["path"], document=record["path"])
        documents.append({"path": str(record["path"]), "document_sha256": record["document_sha256"]})
    if diagnostics:
        return 1, {"status": "blocked", "diagnostics": diagnostics, "warnings": warnings}
    return 0, {"status": "complete", "documents": documents, "warnings": warnings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        status, payload = check(args.repo_root, args.bundle)
    except WorkspaceError as exc:
        status, payload = 2, {
            "status": "blocked",
            "diagnostics": [
                normalize_diagnostic(
                    {"code": exc.code, "category": "unsafe_state", "message": str(exc), "required_action": str(exc)},
                    skill="scribe",
                    phase="write",
                    artifact="document-bundle",
                    path=args.bundle,
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
                    path=args.bundle,
                )
            ],
        }
    print(json.dumps(payload, indent=2))
    return status


if __name__ == "__main__":
    raise SystemExit(main())

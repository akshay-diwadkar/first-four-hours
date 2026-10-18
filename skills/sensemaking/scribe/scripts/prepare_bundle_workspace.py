#!/usr/bin/env python3
"""Prepare the ignored .first-four-hours/document-bundles/<slug>/ support namespace for one document."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from _diagnostic_contract import normalize_diagnostic
from _document_contract import WORKSPACE_DIR
from bundle_workspace import WorkspaceError, prepare_workspace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--slug", required=True)
    args = parser.parse_args(argv)
    try:
        bundle, ignored = prepare_workspace(args.repo_root, args.slug)
    except (WorkspaceError, OSError, UnicodeError, subprocess.SubprocessError) as exc:
        code = exc.code if isinstance(exc, WorkspaceError) else "namespace_unsafe"
        message = str(exc) if isinstance(exc, WorkspaceError) else (
            f"cannot prepare the {WORKSPACE_DIR}/ namespace or its Git exclude: {exc}; repair the reported path or Git metadata and retry"
        )
        payload = {
            "status": "blocked",
            "diagnostics": [
                normalize_diagnostic(
                    {"code": code, "category": "unsafe_state", "message": message, "required_action": message},
                    skill="scribe",
                    phase="prepare",
                    artifact=WORKSPACE_DIR,
                    path=args.repo_root,
                )
            ],
        }
        print(json.dumps(payload, indent=2))
        return 2
    print(
        json.dumps(
            {"status": "complete", "slug": bundle.parent.name, "bundle": str(bundle), "namespace_ignored": ignored},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

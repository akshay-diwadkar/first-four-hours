#!/usr/bin/env python3
"""Prepare one safe, task-scoped Blueprint request and Blueprint workspace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from blueprint_runtime import Diagnostic, prepare_blueprint_workspace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--request-file", type=Path, required=True)
    parser.add_argument("--task-name", required=True)
    args = parser.parse_args()
    try:
        reservation = prepare_blueprint_workspace(args.repo_root, args.task_name, args.request_file)
    except (OSError, UnicodeError, ValueError) as exc:
        diagnostics = getattr(exc, "diagnostics", None)
        if not diagnostics:
            diagnostics = (
                Diagnostic(
                    "workspace.invalid",
                    str(exc),
                    "Repair the named repository, request, task name, or workspace conflict and retry.",
                ),
            )
        print(json.dumps({"valid": False, "diagnostics": [item.to_dict(artifact=".first-four-hours/blueprints") for item in diagnostics]}, sort_keys=True, separators=(",", ":")))
        return 1
    print(
        json.dumps(
            {
                "valid": True,
                "slug": reservation.slug,
                "request_path": str(reservation.request_path),
                "blueprint_path": str(reservation.blueprint_path),
                "relative_request_path": reservation.relative_request_path,
                "relative_blueprint_path": reservation.relative_blueprint_path,
                "git_exclude": str(reservation.git_exclude) if reservation.git_exclude else None,
                "git_ignored": reservation.git_ignored,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

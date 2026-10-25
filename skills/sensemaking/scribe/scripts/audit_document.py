#!/usr/bin/env python3
"""Audit every document a source-bound bundle lists and write one ignored scribe-audit.md report; unusable source evidence blocks the audit."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from _diagnostic_contract import normalize_diagnostic
from _document_contract import WORKSPACE_DIR
from bundle_workspace import WorkspaceError, prepare_workspace
from check_document import inspect_bundle, repair_diagnostics

PREAMBLE = (
    "Each section names one audited document and the SHA-256 of the bytes audited; a later change to that document "
    "makes its section stale. Findings come from the `audit` checks. Reader judgment is the auditing agent's, "
    "recorded in the bundle, and is not a check result."
)


def _line(value: Any) -> str:
    return " ".join(str(value).split())


def render(slug: str, reports: list[dict[str, Any]]) -> str:
    lines = [f"# Scribe audit: {_line(slug)}", "", PREAMBLE]
    for report in reports:
        lines += [
            "",
            f"## `{_line(report['path'])}`",
            "",
            f"- Document SHA-256: `{_line(report['document_sha256'])}`",
            f"- Profile: `{_line(report['profile'])}`",
            f"- Material findings: {'yes' if report['material_findings'] else 'no'}",
            "",
            "### Findings",
            "",
        ]
        lines += [
            f"- `{_line(item['code'])}` ({_line(item['severity'])}, {_line(item.get('record') or 'document')}): "
            f"{_line(item['message'])} Required action: {_line(item['required_action'])}"
            for item in report["findings"]
        ] or ["None."]
        lines += ["", "### Reader judgment", ""]
        lines += [
            f"- {_line(item['location'])}: {_line(item['issue'])} Consequence: {_line(item['consequence'])}"
            for item in report["reader_findings"]
        ] or ["None recorded."]
    return "\n".join(lines) + "\n"


def publish(destination: Path, content: str) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=destination.parent, delete=False
        ) as temp:
            temp.write(content)
            temporary_path = Path(temp.name)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def audit(repo_root: Path, bundle_path: Path, slug: str) -> tuple[int, dict[str, Any]]:
    root = repo_root.resolve()
    sources, records = inspect_bundle(root, bundle_path)
    if sources:
        return 1, {"status": "blocked", "diagnostics": repair_diagnostics([], sources, phase="audit", path=bundle_path)}
    reports = []
    for record in records:
        findings = repair_diagnostics(
            record["language"], record["semantic"], phase="audit", path=record["path"], document=record["path"]
        )
        reports.append(
            {
                "path": str(record["path"]),
                "profile": record["profile"],
                "document_sha256": record["document_sha256"],
                "findings": findings,
                "material_findings": any(item["severity"] in {"error", "critical"} for item in findings),
                "reader_findings": record["reader_findings"],
            }
        )
    try:
        destination, ignored = prepare_workspace(root, slug)
        publish(destination, render(destination.parent.name, reports))
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkspaceError(
            "namespace_unsafe",
            f"cannot prepare the {WORKSPACE_DIR}/ namespace or its Git exclude: {exc}; "
            "repair the reported path or Git metadata and retry",
        ) from exc
    return 0, {
        "status": "complete",
        "audit": str(destination),
        "material_findings": any(report["material_findings"] for report in reports),
        "documents": [
            {key: report[key] for key in ("path", "document_sha256", "material_findings", "findings")}
            for report in reports
        ],
        "namespace_ignored": ignored,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--slug", required=True)
    args = parser.parse_args(argv)
    try:
        status, payload = audit(args.repo_root, args.bundle, args.slug)
    except WorkspaceError as exc:
        bundle_error = exc.code.startswith("bundle_")
        status, payload = 2, {
            "status": "blocked",
            "diagnostics": [
                normalize_diagnostic(
                    {"code": exc.code, "category": "unsafe_state", "message": str(exc), "required_action": str(exc)},
                    skill="scribe",
                    phase="audit",
                    artifact="document-bundle" if bundle_error else WORKSPACE_DIR,
                    path=args.bundle if bundle_error else args.repo_root,
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
                    path=args.bundle,
                )
            ],
        }
    print(json.dumps(payload, indent=2))
    return status


if __name__ == "__main__":
    raise SystemExit(main())

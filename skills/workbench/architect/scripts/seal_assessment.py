#!/usr/bin/env python3
"""Validate and atomically seal .first-four-hours/architectures/<slug>/architecture.md, the sole architect handoff."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from architecture_contract import Diagnostic, seal_handoff
from architecture_handoff import _receipt_free, _with_receipt
from architecture_workspace import WorkspaceError, prepare_workspace

SKILL_ROOT = Path(__file__).resolve().parent.parent

RETIRED_HANDOFF_ARTIFACTS = frozenset(
    {
        "audit-handoff.md",
        "optimization-handoff.md",
        "design-handoff.md",
        "ticket-handoff.md",
        "issue-handoff.md",
    }
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("draft", type=Path)
    return parser


def _retry_command() -> dict[str, Any]:
    return {
        "argv": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        "cwd": str(Path.cwd()),
    }


def _emit_json_diagnostics(diagnostics: list[Diagnostic], path: Path) -> None:
    retry = _retry_command()
    print(
        json.dumps(
            [diagnostic.as_dict(path=path, next_command=retry) for diagnostic in diagnostics],
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _write_atomic(destination: Path, text: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(text)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.replace(temporary_name, destination)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    if not args.repo_root.is_absolute() or not args.repo_root.is_dir():
        parser.error("--repo-root must be an absolute repository directory")
    if not args.draft.is_file():
        parser.error("draft must be a Markdown file")
    repo_root = args.repo_root.resolve(strict=True)
    draft_path = args.draft.resolve(strict=True)
    if _within(draft_path, SKILL_ROOT.resolve(strict=True)):
        message = "draft must be outside the installed skill directory"
        if args.format == "json":
            _emit_json_diagnostics([Diagnostic("path.unsafe", message)], args.draft)
        else:
            print(message, file=sys.stderr)
        return 1
    if draft_path.name in RETIRED_HANDOFF_ARTIFACTS:
        message = f"Retired handoff artifact filename is not accepted: {args.draft.name}."
        if args.format == "json":
            _emit_json_diagnostics([Diagnostic("handoff.path.retired", message)], draft_path)
        else:
            print(message, file=sys.stderr)
        return 1

    try:
        draft = _receipt_free(draft_path.read_text(encoding="utf-8"), repo_root)
    except ValueError as exc:
        if args.format == "json":
            _emit_json_diagnostics([Diagnostic("receipt.invalid", str(exc))], draft_path)
        else:
            print(str(exc), file=sys.stderr)
        return 1
    parsed, diagnostics, final_text = seal_handoff(draft, repo_root)
    del parsed
    if diagnostics:
        if args.format == "json":
            _emit_json_diagnostics(diagnostics, draft_path)
        else:
            print("Cannot seal invalid architecture decision:", file=sys.stderr)
            for diagnostic in diagnostics:
                print(f"  - {diagnostic}", file=sys.stderr)
        return 1

    try:
        destination, git_ignored = prepare_workspace(repo_root, args.slug)
    except (WorkspaceError, OSError, subprocess.SubprocessError) as exc:
        if args.format == "json":
            _emit_json_diagnostics([Diagnostic("workspace.unsafe", str(exc))], draft_path)
        else:
            print(str(exc), file=sys.stderr)
        return 1
    extras = [path for path in destination.parent.iterdir() if path.resolve() != destination.resolve()]
    if extras:
        message = f"{destination.parent} contains artifacts other than architecture.md; remove them or choose a fresh slug"
        if args.format == "json":
            _emit_json_diagnostics([Diagnostic("output.artifacts.extra", message)], destination)
        else:
            print(message, file=sys.stderr)
        return 1
    try:
        final_receipt = _with_receipt(final_text, repo_root)
        if _receipt_free(final_receipt, repo_root) != final_text:
            raise ValueError("architecture proof revalidation changed the handoff body")
    except ValueError as exc:
        if args.format == "json":
            _emit_json_diagnostics([Diagnostic("proof.snapshot", str(exc))], draft_path)
        else:
            print(str(exc), file=sys.stderr)
        return 1
    _write_atomic(destination, final_receipt)
    if args.format == "json":
        print(json.dumps({"git_ignored": git_ignored, "path": str(destination)}, sort_keys=True, separators=(",", ":")))
    else:
        print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

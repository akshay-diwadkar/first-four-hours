#!/usr/bin/env python3
"""Atomically validate and seal the sole ideation handoff artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _skill_protocol_runtime import compatible_version_pattern  # noqa: E402
from ideation_contract import (  # noqa: E402
    IDEATE_VERSION,
    Diagnostic,
    compute_digest,
    seal_body,
    validate_ideation,
)
from ideation_workspace import WorkspaceError, prepare_workspace  # noqa: E402

RECEIPT_PREFIX = "<!-- ideation-handoff:"
RECEIPT_RE = re.compile(rf"^<!-- ideation-handoff: {compatible_version_pattern(IDEATE_VERSION)}; sha256: ([0-9a-f]{{64}}) -->$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _receipt_free(text: str) -> str:
    """Strip a valid receipt line and return the body, or raise ValueError on tampered receipt."""
    head, separator, final = text.removesuffix("\n").rpartition("\n")
    if final.startswith(RECEIPT_PREFIX):
        match = RECEIPT_RE.fullmatch(final)
        if match is None or not separator:
            raise ValueError("ideation handoff receipt format is invalid")
        body = head + "\n"
        if hashlib.sha256(body.encode("utf-8")).hexdigest() != match.group(1):
            raise ValueError("ideation handoff receipt digest does not match content")
    else:
        body = text
    if any(line.startswith(RECEIPT_PREFIX) for line in body.splitlines()):
        raise ValueError("ideation handoff receipt must appear once, as the final line")
    return body


def _with_receipt(body: str) -> str:
    digest = compute_digest(body)
    return body + f"<!-- ideation-handoff: {IDEATE_VERSION}; sha256: {digest} -->\n"


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
        ) as tmp:
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
            temporary_name = tmp.name
        os.replace(temporary_name, destination)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def _retry_command() -> dict[str, Any]:
    return {
        "argv": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        "cwd": str(Path.cwd()),
    }


def _emit_errors(diagnostics: list[Diagnostic], draft_path: Path) -> None:
    retry = _retry_command()
    print(
        json.dumps(
            [d.as_dict(path=draft_path, next_command=retry) for d in diagnostics],
            sort_keys=True,
            separators=(",", ":"),
        )
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--slug", required=True)
    args = parser.parse_args(argv)

    # --- Validate paths ---
    if not args.repo_root.is_absolute() or not args.repo_root.exists():
        parser.error("--repo-root must be an absolute existing directory")
    if not args.draft.is_file():
        parser.error("--draft must be a readable Markdown file")

    repo_resolved = args.repo_root.resolve()
    skill_resolved = SKILL_ROOT.resolve()
    draft_resolved = args.draft.resolve()

    # The draft must be outside the skill dir
    try:
        draft_resolved.relative_to(skill_resolved)
        parser.error("--draft must be outside the installed skill directory")
    except ValueError:
        pass

    # The draft must stay outside the target repository; only the sealer writes .first-four-hours/ideations/.
    try:
        draft_resolved.relative_to(repo_resolved)
        print(
            json.dumps(
                {
                    "valid": False,
                    "diagnostics": [
                        {
                            "code": "ideation.draft_in_workspace",
                            "message": f"draft path {args.draft} resolves inside the target repository {args.repo_root}",
                        }
                    ],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1
    except ValueError:
        pass

    # --- Read and strip receipt ---
    try:
        raw = args.draft.read_text(encoding="utf-8")
        body = _receipt_free(raw)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(
            json.dumps(
                {"valid": False, "diagnostics": [{"code": "ideation.receipt_invalid", "message": str(exc)}]},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1

    # --- Validate ---
    diagnostics = validate_ideation(body, repo_root=args.repo_root)
    if diagnostics:
        _emit_errors(diagnostics, args.draft)
        return 1

    # --- Normalize and seal ---
    normalized = seal_body(body)
    sealed = _with_receipt(normalized)

    # --- Prepare the ignored workspace ---
    try:
        destination, git_ignored = prepare_workspace(repo_resolved, args.slug)
    except (WorkspaceError, OSError, subprocess.SubprocessError) as exc:
        _emit_errors([Diagnostic("ideation.workspace_unsafe", str(exc))], args.draft)
        return 1
    extras = [p.name for p in destination.parent.iterdir() if p.resolve() != destination.resolve()]
    if extras:
        _emit_errors(
            [
                Diagnostic(
                    "ideation.output_not_exclusive",
                    f"{destination.parent} contains files other than ideation.md: {extras}; remove them or choose a fresh slug",
                )
            ],
            args.draft,
        )
        return 1

    # --- Atomic write ---
    _write_atomic(destination, sealed)
    print(
        json.dumps(
            {"status": "sealed", "path": str(destination), "git_ignored": git_ignored},
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

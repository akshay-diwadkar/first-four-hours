#!/usr/bin/env python3
"""Validate and seal, or only check, one agent-authored plain Blueprint draft."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from blueprint_runtime import (
    PROOF_RE,
    VALIDATION_RE,
    Diagnostic,
    replace_canonical_blueprint,
    verify_sealed_blueprint,
    write_utf8,
)


def _print_diagnostics(diagnostics: list[Diagnostic], artifact: str) -> None:
    payload = {
        "valid": False,
        "diagnostics": [item.to_dict(artifact=artifact) for item in diagnostics],
    }
    write_utf8(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def _is_sealed(text: str) -> bool:
    return len(PROOF_RE.findall(text)) == 1 and len(VALIDATION_RE.findall(text)) == 1


def _sealed_payload(path: str, valid: bool, already_sealed: bool, check_only: bool = False) -> dict[str, object]:
    payload: dict[str, object] = {
        "valid": valid,
        "already_sealed": already_sealed,
        "blueprint_path": path,
    }
    if check_only:
        payload["check_only"] = True
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--request-file", type=Path, required=True)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--handoff-item")
    parser.add_argument("--report-json", action="store_true")
    parser.add_argument("--check", action="store_true", help="validate exactly as sealing would and write nothing")
    args = parser.parse_args(argv)

    try:
        draft_before = args.draft.read_bytes()
        draft_text = draft_before.decode("utf-8")

        if _is_sealed(draft_text):
            # A previous run may have sealed successfully but failed to report it.
            # Verify against the current request and report honestly; any drift
            # fails closed instead of resealing over evidence.
            blueprint, diagnostics, _view = verify_sealed_blueprint(
                draft_text,
                args.repo_root,
                request_bytes=args.request_file.read_bytes(),
                handoff_item=args.handoff_item,
            )
            if diagnostics or blueprint is None:
                stale = Diagnostic(
                    "receipt.stale",
                    "The draft already contains a sealed receipt that no longer matches the current request or sources.",
                    "Restore the plain agent-authored draft, or run scripts/verify_blueprint.py to inspect the mismatch.",
                    path=str(args.draft),
                    category="stale_evidence",
                )
                _print_diagnostics([stale, *diagnostics], str(args.draft))
                return 1
            write_utf8(
                json.dumps(
                    _sealed_payload(str(args.draft.resolve()), True, True, args.check),
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
            return 0

        from blueprint_runtime import seal_blueprint as runtime_seal

        result = runtime_seal(
            args.repo_root,
            args.request_file,
            args.draft,
            handoff_item=args.handoff_item,
        )
        if not args.check:
            replace_canonical_blueprint(
                args.repo_root,
                args.draft,
                result.text,
                expected_sha256=hashlib.sha256(draft_before).hexdigest(),
            )
    except (OSError, UnicodeError, ValueError) as exc:
        exc_diagnostics = getattr(exc, "diagnostics", None)
        if not exc_diagnostics:
            exc_diagnostics = (
                Diagnostic(
                    "blueprint.invalid",
                    str(exc),
                    "Correct the named input file or draft and rerun the same seal command.",
                ),
            )
        _print_diagnostics(list(exc_diagnostics), str(args.draft))
        return 1
    if args.check:
        write_utf8(
            json.dumps(
                _sealed_payload(str(args.draft.resolve()), True, False, True),
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
    elif args.report_json:
        write_utf8(
            json.dumps(
                _sealed_payload(str(args.draft.resolve()), True, False),
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
    else:
        write_utf8(result.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

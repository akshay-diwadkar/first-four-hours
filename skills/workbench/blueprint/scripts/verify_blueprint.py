#!/usr/bin/env python3
"""Verify one sealed Blueprint bundle without sealing or writing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from blueprint_runtime import verify_sealed_blueprint, write_utf8


def _emit(payload: dict[str, object]) -> None:
    write_utf8(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--blueprint", type=Path, required=True)
    parser.add_argument(
        "--request-file",
        type=Path,
        help="Defaults to the sibling request.md of the sealed blueprint.",
    )
    parser.add_argument("--handoff-item")
    args = parser.parse_args(argv)

    try:
        text = args.blueprint.read_bytes().decode("utf-8")
        request_file = args.request_file or args.blueprint.parent / "request.md"
        request_bytes = request_file.read_bytes()
    except OSError as exc:
        _emit({"valid": False, "error": str(exc)})
        return 1

    blueprint, diagnostics, _view = verify_sealed_blueprint(
        text,
        args.repo_root,
        request_bytes=request_bytes,
        handoff_item=args.handoff_item,
    )
    valid = blueprint is not None and not diagnostics
    payload: dict[str, object] = {"valid": valid}
    if diagnostics:
        payload["diagnostics"] = [
            item.to_dict(artifact=str(args.blueprint)) for item in diagnostics
        ]
    _emit(payload)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())

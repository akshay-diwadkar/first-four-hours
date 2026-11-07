#!/usr/bin/env python3
"""Report which files an earlier sealed Blueprint bound are unchanged in the current worktree."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from blueprint_runtime import (
    PROOF_RE,
    VALIDATION_RE,
    Diagnostic,
    RepositoryView,
    _canonical_json,
    _workspace_binding,
    canonical_blueprint_path,
    canonical_request_path,
    _error,
    _proof_schema_diagnostics,
    _raise,
    _receipt_pair_diagnostics,
    _sha256,
    canonical_body,
    plan_sha256,
    sealed_contract_diagnostic,
    write_utf8,
)
from seal_blueprint import _print_diagnostics


def _proven_proof(text: str) -> dict[str, Any]:
    retired = sealed_contract_diagnostic(text)
    if retired is not None:
        _raise([retired])
    receipt_pair = _receipt_pair_diagnostics(text)
    if receipt_pair is not None:
        _raise(receipt_pair)
    proof_match = PROOF_RE.search(text)
    validation = VALIDATION_RE.search(text)
    try:
        proof = json.loads(proof_match.group("json")) if proof_match else None
    except json.JSONDecodeError:
        proof = None
    if proof is None or validation is None:
        _raise([
            _error(
                "proof.malformed",
                "Blueprint proof is not valid JSON.",
                "Use the exact output from seal_blueprint.py.",
                category="stale_evidence",
            )
        ])
    try:
        current_plan: str | None = plan_sha256(canonical_body(text))
    except ValueError:
        current_plan = None
    if (
        current_plan is None
        or validation.group("plan") != current_plan
        or validation.group("proof") != _sha256(_canonical_json(proof).encode("utf-8"))
    ):
        _raise([
            _error(
                "proof.stale",
                "Blueprint plan or proof digest does not match the validation receipt.",
                "Pass an unedited sealed blueprint.md.",
                category="stale_evidence",
            )
        ])
    schema = _proof_schema_diagnostics(proof)
    if schema:
        _raise(schema)
    return proof


def implemented_locations(predecessor: Path, architecture_sha256: str, repo_root: Path) -> frozenset[str]:
    """Return the Location paths of a sealed plan built on the declared architecture.

    The plan must be unedited, bound to its frozen sibling request and this
    repository, and that request must bind the same architecture bytes.
    """
    plan = canonical_blueprint_path(repo_root, predecessor, require_existing=True)
    request = canonical_request_path(repo_root, plan.parent / "request.md", require_existing=True)
    proof = _proven_proof(plan.read_bytes().decode("utf-8"))
    request_bytes = request.read_bytes()
    if {key: proof["binding"][key] for key in ("repository_id", "request_sha256")} != _workspace_binding(
        repo_root, request_bytes
    ):
        raise ValueError("Architecture source predecessor is not bound to its request.md in this repository.")
    declared = [
        json.loads(match).get("sha256")
        for match in re.findall(r"(?m)^<!-- architecture-source: (\{.*\}) -->$", request_bytes.decode("utf-8").replace("\r\n", "\n"))
    ]
    if _sha256(request_bytes) != architecture_sha256 and declared != [architecture_sha256]:
        raise ValueError("Architecture source predecessor was not planned from this architecture.")
    return frozenset(record["path"] for record in proof["locations"])


def _status(view: RepositoryView, path: str, recorded: str) -> str:
    try:
        if view.entry_path(path).is_symlink():
            return "missing"
        data = view.read(path)
    except (OSError, ValueError):
        return "missing"
    return "unchanged" if _sha256(data) == recorded else "changed"


def carryover(repo_root: Path, text: str) -> list[dict[str, str]]:
    proof = _proven_proof(text)
    view = RepositoryView(repo_root)
    entries: list[dict[str, str]] = []
    for role, records in (("source", proof["sources"]), ("location", proof["locations"])):
        for record in records:
            if "sha256" not in record:
                continue
            entries.append({"path": record["path"], "role": role, "status": _status(view, record["path"], record["sha256"])})
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--predecessor", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        text = args.predecessor.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        _print_diagnostics(
            [
                Diagnostic(
                    "carryover.predecessor_unreadable",
                    f"Cannot read predecessor {str(args.predecessor)!r}: {exc}.",
                    "Pass an existing UTF-8 sealed blueprint.md.",
                    path=str(args.predecessor),
                )
            ],
            str(args.predecessor),
        )
        return 1
    try:
        entries = carryover(args.repo_root, text)
    except ValueError as exc:
        diagnostics = getattr(exc, "diagnostics", None)
        if not diagnostics:
            raise
        _print_diagnostics(list(diagnostics), str(args.predecessor))
        return 1
    write_utf8(
        json.dumps(
            {"predecessor": str(args.predecessor.resolve()), "entries": entries},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

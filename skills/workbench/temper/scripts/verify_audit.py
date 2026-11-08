#!/usr/bin/env python3
"""Verify a sealed test audit against the current tree: kills still hold and the suite is not slower."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from audit_contract import read_sealed, select_findings, validate_bundle
from replay import ReplayError, RepositoryCopy, mutated, outcome, run_selection

SLOW_KINDS = {"redundant", "vacuous", "rework"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--item")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()

    def fail(*messages: str) -> int:
        print("\n".join(messages))
        return 1

    if not args.audit.is_file():
        return fail(f"audit must be an existing regular file: {args.audit}")
    try:
        sealed = read_sealed(args.audit.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return fail(str(exc))
    bundle: Any = sealed["bundle"]
    results: Any = sealed["results"]
    errors = validate_bundle(bundle, repo_root)
    if errors:
        return fail(*errors)
    findings = bundle["findings"]
    if not findings:
        return fail("audit has no findings to verify")
    try:
        numbers = select_findings(len(findings), args.item)
    except ValueError as exc:
        return fail(str(exc))
    selected = [(number, findings[number - 1]) for number in numbers]
    selections = bundle["selections"]
    guards = sorted({finding["guard"] for _, finding in selected if finding["guard"] != "suite"})

    kills: list[dict[str, Any]] = []
    failures: list[str] = []
    suite_seconds = 0.0
    try:
        with RepositoryCopy(repo_root, bundle["copy_git"], bundle["copy_exclude"]) as copy_root:
            for name in ["suite", *guards]:
                status, seconds, tail = run_selection(copy_root, name, selections[name])
                if name == "suite":
                    suite_seconds = seconds
                if status != "passed":
                    failures.append(f"selection `{name}` did not pass unmutated ({status}): {tail}")
            if failures:
                return fail(*failures)
            pairs: dict[tuple[str, str], int] = {}
            for number, finding in selected:
                for mid in finding["mutants"]:
                    pairs.setdefault((mid, finding["guard"]), number)
            for (mid, guard), number in sorted(pairs.items(), key=lambda pair: (int(pair[0][0][1:]), pair[0][1])):
                mutant = bundle["mutants"][mid]
                with mutated(copy_root, mutant):
                    status, _seconds, _tail = run_selection(copy_root, guard, selections[guard])
                observed = outcome(status)
                if observed != "killed":
                    failures.append(
                        f"finding {number} ({findings[number - 1]['kind']}): guard `{guard}` no longer kills "
                        f"mutant {mid} ({mutant['behavior']})"
                    )
                kills.append({"finding": number, "mutant": mid, "guard": guard, "observed": observed})
    except ReplayError as exc:
        failures.append(str(exc))
    if failures:
        return fail(*failures)

    baseline_seconds = float(results["baseline"]["suite"])
    if any(finding["kind"] in SLOW_KINDS for _, finding in selected) and suite_seconds > baseline_seconds * 1.1 + 1.0:
        return fail(
            f"suite took {suite_seconds:.1f} seconds, more than 10% plus one second over "
            f"the audited baseline of {baseline_seconds:.1f} seconds"
        )
    budget = bundle["budget"]
    budget_seconds = budget["seconds"]
    within = None if budget_seconds is None or budget["kind"] == "ci" else suite_seconds <= budget_seconds
    print(
        json.dumps(
            {
                "audit": str(args.audit),
                "findings": numbers,
                "suite_seconds": round(suite_seconds, 3),
                "baseline_seconds": baseline_seconds,
                "saved_seconds": round(baseline_seconds - suite_seconds, 3),
                "budget_seconds": budget_seconds,
                "within_budget": within,
                "kills": kills,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

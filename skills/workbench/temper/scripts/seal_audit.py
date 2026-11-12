#!/usr/bin/env python3
"""Replay one agent-authored test-audit bundle in a throwaway copy and atomically seal test-audit.md."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from audit_contract import claims_of, expectations, render, validate_bundle
from audit_workspace import RESULT_FILENAME, WorkspaceError, prepare_workspace
from replay import ReplayError, RepositoryCopy, mutated, outcome, run_selection


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--slug", required=True)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    skill_root = Path(__file__).resolve().parent.parent

    def fail(*messages: str) -> int:
        print("\n".join(messages))
        return 1

    if not args.bundle.is_file():
        return fail(f"bundle must be an existing regular JSON file: {args.bundle}")
    bundle_path = args.bundle.resolve(strict=True)
    for protected, label in ((skill_root, "installed skill"), (repo_root, "target repository")):
        if bundle_path == protected or protected in bundle_path.parents:
            return fail(f"bundle must be outside the {label}")
    try:
        bundle: Any = json.loads(bundle_path.read_bytes().decode("utf-8"))
    except (OSError, ValueError) as exc:
        return fail(f"bundle is not readable UTF-8 JSON: {exc}")
    errors = validate_bundle(bundle, repo_root)
    if errors:
        return fail(*errors)

    selections = bundle["selections"]
    expected = expectations(bundle)
    baseline: dict[str, float] = {}
    outcomes: list[dict[str, Any]] = []
    failures: list[str] = []
    try:
        with RepositoryCopy(repo_root, bundle["copy_git"], bundle["copy_exclude"]) as copy_root:
            for name in sorted(selections):
                status, seconds, tail = run_selection(copy_root, name, selections[name])
                baseline[name] = round(seconds, 3)
                if status != "passed":
                    failures.append(f"selection `{name}` did not pass unmutated ({status}): {tail}")
            if not failures:
                by_mutant: dict[str, list[str]] = {}
                for mid, name in expected:
                    by_mutant.setdefault(mid, []).append(name)
                for mid in sorted(by_mutant, key=lambda value: int(value[1:])):
                    with mutated(copy_root, bundle["mutants"][mid]):
                        for name in sorted(by_mutant[mid]):
                            status, seconds, _tail = run_selection(copy_root, name, selections[name])
                            outcomes.append(
                                {
                                    "mutant": mid,
                                    "selection": name,
                                    "expected": expected[(mid, name)],
                                    "observed": outcome(status),
                                    "seconds": round(seconds, 3),
                                }
                            )
                for item in outcomes:
                    if item["observed"] == item["expected"]:
                        continue
                    for number, finding in enumerate(bundle["findings"], 1):
                        if item["mutant"] not in finding["mutants"]:
                            continue
                        for role, name, _outcome in claims_of(finding):
                            if name == item["selection"]:
                                verb = "kill" if item["expected"] == "killed" else "survive"
                                failures.append(
                                    f"finding {number} ({finding['kind']}): mutant {item['mutant']} expected {role} "
                                    f"`{item['selection']}` to {verb}, observed {item['observed']}"
                                )
    except ReplayError as exc:
        failures.append(str(exc))
    if failures:
        return fail(*failures)

    outcomes.sort(key=lambda item: (int(item["mutant"][1:]), item["selection"]))
    results = {"baseline": baseline, "outcomes": outcomes}
    try:
        destination, git_ignored = prepare_workspace(repo_root, args.slug)
    except (WorkspaceError, OSError, subprocess.SubprocessError) as exc:
        return fail(str(exc))
    if any(path != destination for path in destination.parent.iterdir()):
        return fail(f"{destination.parent} contains artifacts other than {RESULT_FILENAME}; remove them or choose a fresh slug")
    count = len(bundle["findings"])
    verify_argv = [
        "python",
        (skill_root / "scripts" / "cli.py").as_posix(),
        "--repo-root",
        repo_root.as_posix(),
        "--input",
        f"audit={destination.as_posix()}",
        "--input",
        f"item={','.join(str(n) for n in range(1, count + 1)) or '1'}",
        "--format",
        "json",
        "verify",
    ]
    content = render(bundle, results, verify_argv)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=destination.parent, delete=False) as temp:
            temp.write(content.encode("utf-8"))
            temporary_path = Path(temp.name)
        os.replace(temporary_path, destination)
    except OSError as exc:
        print(f"publication failed: {exc}")
        return 1
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    print(
        json.dumps(
            {"path": str(destination), "git_ignored": git_ignored, "findings": count, "baseline_seconds": baseline["suite"]}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

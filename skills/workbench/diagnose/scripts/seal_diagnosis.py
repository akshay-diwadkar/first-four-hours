#!/usr/bin/env python3
"""Validate one agent-owned diagnosis bundle and atomically seal diagnosis.md."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from diagnosis import render
from diagnosis_bundle import DiagnosisBundleError, read_json, revalidate_diagnosis_bindings, validate_diagnosis_bindings
from diagnosis_workspace import WorkspaceError, prepare_workspace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--slug", required=True)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    skill_root = Path(__file__).resolve().parent.parent

    def fail(message: str) -> int:
        print(message)
        return 1

    def protected_root(path: Path) -> str | None:
        if path == skill_root or skill_root in path.parents:
            return "installed skill"
        if path == repo_root or repo_root in path.parents:
            return "target repository"
        return None

    if not args.bundle.is_file():
        return fail(f"bundle must be an existing regular JSON file: {args.bundle}")
    bundle_path = args.bundle.resolve(strict=True)
    bundle_boundary = protected_root(bundle_path)
    if bundle_boundary is not None:
        return fail(f"bundle must be outside the {bundle_boundary}")
    try:
        bundle = read_json(bundle_path)
    except (DiagnosisBundleError, OSError) as exc:
        return fail(str(exc))
    context = bundle.get("diagnosis_context") if isinstance(bundle, dict) else None
    evidence_root = context.get("evidence_root") if isinstance(context, dict) else None
    if isinstance(evidence_root, str) and Path(evidence_root).is_absolute():
        evidence_path = Path(evidence_root).resolve()
        evidence_boundary = protected_root(evidence_path)
        if evidence_boundary is not None:
            return fail(f"evidence_root must be outside the {evidence_boundary}")
        for contained, name in ((repo_root, "target repository"), (skill_root, "installed skill")):
            if evidence_path in contained.parents:
                return fail(f"evidence_root must not contain the {name}")

    errors, proof = validate_diagnosis_bindings(bundle, repo_root)
    if errors:
        print("\n".join(errors))
        return 1
    assert proof is not None and isinstance(bundle, dict)
    try:
        destination, git_ignored = prepare_workspace(repo_root, args.slug)
    except (WorkspaceError, OSError, subprocess.SubprocessError) as exc:
        return fail(str(exc))
    content = render(bundle)
    if any(path != destination for path in destination.parent.iterdir()):
        return fail(f"{destination.parent} contains artifacts other than diagnosis.md; remove them or choose a fresh slug")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            delete=False,
        ) as temp:
            temp.write(content)
            temporary_path = Path(temp.name)
        errors = revalidate_diagnosis_bindings(bundle, repo_root, proof)
        if errors:
            print("\n".join(errors))
            return 1
        os.replace(temporary_path, destination)
    except OSError as exc:
        print(f"publication failed: {exc}")
        return 1
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    print(json.dumps({"path": str(destination), "git_ignored": git_ignored}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

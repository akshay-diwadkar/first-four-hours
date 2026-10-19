#!/usr/bin/env python3
"""Check this checkout's Skills CLI listing and isolated Diagnose install, plus collection installs for selected roots."""

from __future__ import annotations


# Public command execution starts in a contained worker before project imports.
import sys as _sys
import time as _time

_VALIDATION_START = _time.monotonic()
from pathlib import Path as _Path
from validation_budget import bounded_main as _bounded_main

if __name__ == "__main__":
    raise SystemExit(_bounded_main(_Path(__file__), _sys.argv[1:], _Path(__file__).resolve().parents[2], started_at=_VALIDATION_START))

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import validate_repository as repository_validator
import validate_npx_output
from validation_budget import run_capture

CLI_VERSION = repository_validator.SKILLS_CLI_VERSION
INSTALL_ROOTS = {
    "claude-code": Path(".claude/skills"),
    "codex": Path(".agents/skills"),
    "github-copilot": Path(".agents/skills"),
}


def _snapshot(path: Path) -> dict[str, str]:
    return {
        file.relative_to(path).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in sorted(path.rglob("*"))
        if file.is_file() and "__pycache__" not in file.parts
    }


def _run_install(npx: str, repo_root: Path, consumer: Path, agent: str, skill: str) -> None:
    consumer.mkdir(parents=True)
    env = os.environ.copy()
    env.update({"DISABLE_TELEMETRY": "1", "FORCE_COLOR": "0", "NO_COLOR": "1"})
    result = run_capture(
        [
            npx,
            "--yes",
            f"skills@{CLI_VERSION}",
            "add",
            str(repo_root),
            "--skill",
            skill,
            "--agent",
            agent,
            "--copy",
            "--yes",
        ],
        cwd=consumer,
        env=env,
    )
    if result.returncode:
        raise RuntimeError((result.stdout + result.stderr).decode("utf-8", errors="replace"))


def _assert_install(
    repo_root: Path,
    consumer: Path,
    agent: str,
    expected_names: set[str],
    modes: dict[str, str],
) -> None:
    install_root = consumer / INSTALL_ROOTS[agent]
    actual_names = {path.name for path in install_root.iterdir() if path.is_dir()}
    if actual_names != expected_names:
        raise AssertionError(
            f"{agent}: expected installed skills {sorted(expected_names)}, got {sorted(actual_names)}"
        )
    source_by_name = {skill.name: skill for skill in repository_validator.discover_skills()}
    for name in sorted(expected_names):
        installed = install_root / name
        if _snapshot(installed) != _snapshot(source_by_name[name]):
            raise AssertionError(f"{agent}: installed package differs from source for {name}")
        errors = repository_validator.validate_skill_invocation_metadata(installed, modes[name])
        if errors:
            raise AssertionError(f"{agent}: invalid installed metadata for {name}: {errors}")
    lock = json.loads((consumer / "skills-lock.json").read_text(encoding="utf-8"))
    if not isinstance(lock, dict):
        raise AssertionError(f"{agent}: skills-lock.json must contain an object")


def validate_installs(repo_root: Path, agent: str) -> None:
    if agent not in INSTALL_ROOTS:
        raise ValueError(f"unsupported certified agent: {agent}")
    npx = shutil.which("npx")
    if npx is None:
        raise RuntimeError("npx is required")
    registry = json.loads((repo_root / "invocation-policy.json").read_text(encoding="utf-8"))
    modes = registry["skills"]
    names = set(modes)
    canonical_root = repo_root.resolve() == repository_validator.ROOT
    with tempfile.TemporaryDirectory(prefix=f"skills-install-{agent}-") as temporary:
        root = Path(temporary)
        complete = root / "complete"
        if canonical_root:
            env = os.environ.copy()
            env.update({"DISABLE_TELEMETRY": "1", "FORCE_COLOR": "0", "NO_COLOR": "1"})
            listing = run_capture(
                [npx, "--yes", f"skills@{CLI_VERSION}", "add", str(repo_root), "--list"],
                cwd=root,
                env=env,
            )
            if listing.returncode:
                raise RuntimeError((listing.stdout + listing.stderr).decode("utf-8", errors="replace"))
            errors = validate_npx_output.validate_output(listing.stdout.decode("utf-8", errors="replace"))
            if errors:
                raise AssertionError(f"invalid Skills CLI listing: {errors}")
        _run_install(npx, repo_root, complete, agent, "*")
        _assert_install(repo_root, complete, agent, names, modes)
        if canonical_root:
            single = root / "single"
            _run_install(npx, repo_root, single, agent, "diagnose")
            _assert_install(repo_root, single, agent, {"diagnose"}, modes)



def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=repository_validator.ROOT)
    parser.add_argument("--agent", required=True, choices=sorted(INSTALL_ROOTS))
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    validate_installs(repo_root, args.agent)
    if repo_root == repository_validator.ROOT:
        print(f"Skills CLI {CLI_VERSION} listing and installation passed for {args.agent}.")
    else:
        print(f"Skills CLI {CLI_VERSION} installation passed for {args.agent}.")
    return 0

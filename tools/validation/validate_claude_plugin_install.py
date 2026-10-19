#!/usr/bin/env python3
"""Install every First Four Hours plugin through Claude Code into a temporary configuration and check it against source."""

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
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

import sync_skill_catalog
import validate_repository as repository_validator
from validate_skills_cli_install import _snapshot
from validation_budget import run_capture

CLAUDE_ENV = {"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "FORCE_COLOR": "0", "NO_COLOR": "1"}
SKILLS_LINE_RE = re.compile(r"^\s*Skills \((\d+)\)[ \t]*(.*)$", re.MULTILINE)


def _claude(claude: str, config: Path, *args: str) -> str:
    env = os.environ.copy()
    env.pop("SKILLS_VALIDATION_ACTIVE", None)
    env.pop("SKILLS_CASE_REPORT", None)
    env.update(CLAUDE_ENV)
    env["CLAUDE_CONFIG_DIR"] = str(config)
    result = run_capture([claude, *args], cwd=repository_validator.ROOT, env=env)
    if result.returncode:
        raise RuntimeError(
            f"claude {' '.join(args)} failed: "
            + (result.stdout + result.stderr).decode("utf-8", errors="replace")
        )
    return result.stdout.decode("utf-8", errors="replace")


def validate_plugin_install() -> tuple[int, int]:
    root = repository_validator.ROOT
    claude = shutil.which("claude")
    if claude is None:
        raise RuntimeError("claude (Claude Code) is required")
    market = json.loads((root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))["name"]
    modes = json.loads((root / "invocation-policy.json").read_text(encoding="utf-8"))["skills"]
    groups = sync_skill_catalog.groups()
    with tempfile.TemporaryDirectory(prefix="claude-plugin-install-", ignore_cleanup_errors=True) as temporary:
        export = Path(temporary) / "marketplace"
        config = Path(temporary) / "config"
        config.mkdir()
        listing = run_capture(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root)
        if listing.returncode:
            raise RuntimeError("git ls-files failed: " + listing.stderr.decode("utf-8", errors="replace"))
        for relative in listing.stdout.decode("utf-8").split("\0"):
            if not relative:
                continue
            source = root / relative
            if not source.is_file():
                continue
            target = export / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        report = json.loads(_claude(claude, config, "plugin", "validate", str(export), "--strict", "--json"))
        if report.get("success") is not True:
            raise AssertionError(f"claude plugin validate failed: {report.get('manifest')}")
        for plugin in groups:
            _claude(claude, config, "plugin", "install", plugin, "--marketplace", str(export))
        listed = {item["id"]: item for item in json.loads(_claude(claude, config, "plugin", "list", "--json"))}
        expected_ids = {f"{plugin}@{market}" for plugin in groups}
        if set(listed) != expected_ids:
            raise AssertionError(f"installed plugins {sorted(listed)} differ from {sorted(expected_ids)}")
        for plugin, paths in groups.items():
            plugin_id = f"{plugin}@{market}"
            if listed[plugin_id].get("enabled") is not True:
                raise AssertionError(f"{plugin_id} is not enabled")
            match = SKILLS_LINE_RE.search(_claude(claude, config, "plugin", "details", plugin_id))
            if match is None:
                raise AssertionError(f"{plugin_id}: claude plugin details printed no Skills inventory")
            discovered = sorted(name.strip() for name in match.group(2).split(",") if name.strip())
            expected = sorted(path.rsplit("/", 1)[1] for path in paths)
            if discovered != expected:
                raise AssertionError(f"{plugin_id}: Claude Code discovered {discovered}, expected {expected}")
            install_root = Path(listed[plugin_id]["installPath"])
            for path in paths:
                relative = path.removeprefix("./")
                installed = install_root / relative
                if _snapshot(installed) != _snapshot(root / relative):
                    raise AssertionError(f"{plugin_id}: installed {relative} differs from source")
                errors = repository_validator.validate_skill_invocation_metadata(installed, modes[installed.name])
                if errors:
                    raise AssertionError(f"{plugin_id}: invalid installed metadata for {installed.name}: {errors}")
    return len(groups), sum(len(paths) for paths in groups.values())


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    plugins, skills = validate_plugin_install()
    print(f"Claude Code plugin installation passed for {plugins} plugin and {skills} skills.")
    return 0

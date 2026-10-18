#!/usr/bin/env python3
"""Run mypy in isolated skill scopes discovered from the filesystem."""

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
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = ROOT / "skills"


def _contains_python(path: Path) -> bool:
    if path.is_file():
        return path.suffix in {".py", ".pyi"}
    return path.is_dir() and any(
        candidate.suffix in {".py", ".pyi"} and "__pycache__" not in candidate.parts
        for candidate in path.rglob("*")
    )


def run_mypy_group(label: str, targets: list[Path], extra_paths: list[Path] | None = None) -> bool:
    existing = [str(path.relative_to(ROOT)) for path in targets if _contains_python(path)]
    if not existing:
        return True
    env = dict(os.environ)
    if extra_paths:
        env["MYPYPATH"] = os.pathsep.join(str(path) for path in extra_paths)
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--no-incremental", "--cache-dir", os.devnull, *existing],
        cwd=ROOT,
        env=env,
    )
    if result.returncode:
        print(f"Mypy check failed for {label}", file=sys.stderr)
        return False
    return True


def discover_skill_scopes(
    excluded_skills: set[str] | None = None,
) -> list[tuple[str, list[Path], list[Path]]]:
    excluded = excluded_skills or set()
    return [
        (
            f"{skill_dir.parent.name}/{skill_dir.name}",
            [skill_dir, ROOT / "tests" / "skills" / skill_dir.name],
            [skill_dir / "scripts"],
        )
        for domain_dir in sorted(path for path in SKILLS_ROOT.iterdir() if path.is_dir())
        for skill_dir in sorted(
            path for path in domain_dir.iterdir() if path.is_dir() and (path / "SKILL.md").is_file()
        )
        if skill_dir.name not in excluded
    ]


def discover_selected_skill_scopes(
    selected: set[str], excluded_skills: set[str] | None = None
) -> list[tuple[str, list[Path], list[Path]]]:
    return _selected_skill_scopes(discover_skill_scopes(excluded_skills), selected)


def _test_target_path(target: str) -> Path:
    candidate = (ROOT / target.replace("\\", "/")).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"test target escapes repository: {target}") from exc
    if not _contains_python(candidate):
        raise ValueError(
            f"test target is missing or contains no Python: {target}; "
            "use the owner's surviving test target for deleted or non-Python fixtures"
        )
    return candidate


def discover_selected_test_scopes(selected: list[str]) -> list[tuple[str, list[Path], list[Path]]]:
    """Group explicit test paths while preserving skill-local import isolation."""
    grouped: dict[str, tuple[list[Path], list[Path]]] = {}
    all_script_paths = [
        skill_dir / "scripts"
        for domain_dir in sorted(path for path in SKILLS_ROOT.iterdir() if path.is_dir())
        for skill_dir in sorted(path for path in domain_dir.iterdir() if path.is_dir())
        if (skill_dir / "SKILL.md").is_file() and (skill_dir / "scripts").is_dir()
    ]
    for raw_target in selected:
        target = raw_target.replace("\\", "/")
        path = _test_target_path(target)
        parts = target.split("/")
        if len(parts) >= 3 and parts[:2] == ["tests", "skills"]:
            name = f"tests/skills/{parts[2]}"
            extras = [ROOT / "skills" / domain / parts[2] / "scripts" for domain in ("workbench", "sensemaking")]
            extras = [item for item in extras if item.is_dir()]
        else:
            name = "repository-tests"
            extras = all_script_paths
        paths, existing_extras = grouped.setdefault(name, ([], extras))
        if path not in paths:
            paths.append(path)
        grouped[name] = (paths, existing_extras)
    return [(name, _dedupe_contained_paths(paths), extras) for name, (paths, extras) in sorted(grouped.items())]


def _dedupe_contained_paths(paths: list[Path]) -> list[Path]:
    """Drop paths already covered by a directory target in the same scope.

    Passing both a directory and one of its files to mypy discovers the same
    module twice and fails with a duplicate-module error; the directory alone
    covers the same files.
    """
    return [
        path
        for path in paths
        if not any(path != other and path.is_relative_to(other) for other in paths)
    ]


def discover_selected_path_scopes(selected: list[str]) -> list[tuple[str, list[Path], list[Path]]]:
    """Group explicit production source paths with their skill import roots."""
    grouped: dict[str, tuple[list[Path], list[Path]]] = {}
    for raw_target in selected:
        target = raw_target.replace("\\", "/")
        path = _test_target_path(target)
        parts = target.split("/")
        if len(parts) >= 3 and parts[0] == "skills":
            name = f"paths/{parts[1]}/{parts[2]}"
            extras = [ROOT / "skills" / parts[1] / parts[2] / "scripts"]
        else:
            name = "paths/repository"
            extras = []
        paths, existing_extras = grouped.setdefault(name, ([], extras))
        if path not in paths:
            paths.append(path)
        grouped[name] = (paths, existing_extras)
    return [(name, paths, extras) for name, (paths, extras) in sorted(grouped.items())]


def _selected_skill_scopes(
    available: list[tuple[str, list[Path], list[Path]]], selected: set[str]
) -> list[tuple[str, list[Path], list[Path]]]:
    return [
        scope
        for scope in available
        if _scope_matches(scope[0], selected)
    ]


def _scope_matches(scope_name: str, selected: set[str]) -> bool:
    return scope_name in selected or scope_name.split("/", 1)[-1] in selected


def main() -> int:
    parser = argparse.ArgumentParser(description="Run mypy in discovered repository scopes.")
    parser.add_argument(
        "--exclude-skill",
        action="append",
        default=[],
        dest="excluded_skills",
        metavar="NAME",
        help="Skip a skill and its tests; may be supplied more than once.",
    )
    parser.add_argument(
        "--skill",
        action="append",
        default=[],
        dest="selected_skills",
        metavar="NAME",
        help="Check only the named skill and its tests; use NAME or DOMAIN/NAME and repeat as needed.",
    )
    parser.add_argument(
        "--repository-tooling",
        action="store_true",
        help="Check only repository tooling and repository/integration test scopes.",
    )
    parser.add_argument(
        "--test",
        action="append",
        default=[],
        dest="selected_tests",
        metavar="PATH",
        help="Check only the explicit repository-relative test file or directory; repeat as needed.",
    )
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        dest="selected_paths",
        metavar="PATH",
        help="Check only the explicit repository-relative production source file; repeat as needed.",
    )
    args = parser.parse_args()
    positive_scope = bool(args.selected_paths or args.selected_tests or args.selected_skills or args.repository_tooling)
    if not positive_scope:
        parser.error("an explicit --skill, --test, --path, or --repository-tooling scope is required")
    if args.excluded_skills and not args.selected_skills:
        parser.error("--exclude-skill requires at least one explicit --skill scope")
    if args.excluded_skills and (args.selected_tests or args.selected_paths or args.repository_tooling):
        parser.error("--exclude-skill can only accompany --skill scopes")
    selected_bare = {name.rsplit("/", 1)[-1] for name in args.selected_skills}
    excluded_bare = {name.rsplit("/", 1)[-1] for name in args.excluded_skills}
    if args.excluded_skills and selected_bare <= excluded_bare:
        parser.error("--exclude-skill leaves no selected skill scope")
    failures: list[str] = []
    if args.selected_paths:
        if args.selected_skills or args.selected_tests or args.repository_tooling:
            failures.append("--path cannot be combined with --skill, --test, or --repository-tooling")
            scopes = []
        else:
            try:
                scopes = discover_selected_path_scopes(args.selected_paths)
            except ValueError as exc:
                failures.append(str(exc))
                scopes = []
    elif args.selected_tests:
        if args.selected_skills or args.repository_tooling:
            failures.append("--test cannot be combined with --skill or --repository-tooling")
            scopes = []
        else:
            try:
                scopes = discover_selected_test_scopes(args.selected_tests)
            except ValueError as exc:
                failures.append(str(exc))
                scopes = []
    elif args.selected_skills:
        available = discover_skill_scopes(excluded_bare)
        selected_names = set(args.selected_skills)
        matches_by_name = {
            name: _selected_skill_scopes(available, {name}) for name in sorted(selected_names)
        }
        scopes = []
        seen_scopes: set[str] = set()
        for matches in matches_by_name.values():
            for scope in matches:
                if scope[0] not in seen_scopes:
                    scopes.append(scope)
                    seen_scopes.add(scope[0])
        for name in sorted(set(args.selected_skills)):
            matches = matches_by_name[name]
            if not matches:
                failures.append(f"skill scope not found: {name}")
            elif "/" not in name and len(matches) > 1:
                failures.append(
                    f"skill scope is ambiguous: {name}; use one of {', '.join(scope[0] for scope in matches)}"
                )
        if failures:
            scopes = []
        elif not scopes:
            failures.append("scope selection is empty after exclusions")
    elif args.repository_tooling:
        scopes = []
    else:
        scopes = []
    for name, targets, extra_paths in scopes:
        label = f"tests: {name}" if name.startswith("tests/") or name == "repository-tests" else f"skill: {name}"
        if not run_mypy_group(label, targets, extra_paths):
            failures.append(name)
    if args.repository_tooling:
        tooling = [
            ROOT / "tools" / "validation",
            ROOT / "tools" / "diagnostics",
            ROOT / "tools" / "skill_protocol",
            ROOT / "tools" / "skill_cli.py",
            ROOT / "tests" / "repository",
            ROOT / "tests" / "integration",
            ROOT / "tests" / "skill_protocol",
        ]
        if not run_mypy_group("repository tooling", tooling):
            failures.append("repository tooling")
    if failures:
        print("Mypy failures: " + ", ".join(failures), file=sys.stderr)
        return 1
    print("All mypy checks passed.")
    return 0

#!/usr/bin/env python3
"""Check, report, or estimate from a Blueprint draft the skill instruction and reference token budgets."""

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
import importlib
import json
import os
import sys
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from context_tokenizer import count_tokens
else:
    try:
        from context_tokenizer import count_tokens
    except ImportError:  # package import from repository tests
        from tools.validation.context_tokenizer import count_tokens

ROOT = Path(__file__).resolve().parents[2]
BUDGETS_PATH = Path("tools", "validation", "context-load-budgets.json")
METRICS = {"top_level", "references"}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_limits(path: Path = ROOT / BUDGETS_PATH, root: Path = ROOT) -> dict[str, dict[str, int]]:
    """Read the budget config and require one positive pair for every current skill."""
    payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "limits"} or payload.get("schema_version") != "1.0.0":
        raise ValueError("context budget config must use schema_version '1.0.0'")
    limits = payload.get("limits")
    if not isinstance(limits, dict):
        raise ValueError("context budget config must contain a limits object")
    skills_root = root / "skills"
    discovered = {
        path.parent.name
        for path in skills_root.glob("*/*/SKILL.md")
        if path.is_file()
    }
    if set(limits) != discovered:
        missing, unknown = sorted(discovered - set(limits)), sorted(set(limits) - discovered)
        raise ValueError(f"context budget skill inventory mismatch; missing={missing}, unknown={unknown}")
    result: dict[str, dict[str, int]] = {}
    for skill, row in limits.items():
        if not isinstance(row, dict) or set(row) != METRICS:
            raise ValueError(f"{skill}: limits must contain exactly top_level and references")
        if any(type(row[name]) is not int or row[name] <= 0 for name in METRICS):
            raise ValueError(f"{skill}: token limits must be positive integers")
        result[skill] = {name: row[name] for name in sorted(METRICS)}
    return result


def _reference_files(skill_dir: Path) -> list[Path]:
    references = skill_dir / "references"
    if not references.exists() or references.is_symlink():
        return []
    resolved_skill = skill_dir.resolve()
    files: list[Path] = []
    for current, dirs, names in os.walk(references, followlinks=False):
        here = Path(current)
        kept: list[str] = []
        for name in dirs:
            child = here / name
            if name == "__pycache__" or child.is_symlink():
                continue
            kept.append(name)
        dirs[:] = kept
        for name in names:
            candidate = here / name
            if candidate.is_symlink():
                try:
                    candidate.resolve().relative_to(resolved_skill)
                except ValueError as exc:
                    raise ValueError(f"reference file symlink escapes skill: {candidate}") from exc
                if candidate.is_file():
                    files.append(candidate)
            elif candidate.is_file() and "__pycache__" not in candidate.parts:
                files.append(candidate)
    return sorted(files)


def measure(root: Path = ROOT) -> dict[str, dict[str, int]]:
    """Count current skill and reference bytes once using the vendored tokenizer."""
    rows: dict[str, dict[str, int]] = {}
    for skill_file in sorted((root / "skills").glob("*/*/SKILL.md")):
        if not skill_file.is_file():
            continue
        references = _reference_files(skill_file.parent)
        rows[skill_file.parent.name] = {
            "top_level": count_tokens(skill_file.read_text(encoding="utf-8")),
            "references": sum(count_tokens(path.read_text(encoding="utf-8")) for path in references),
        }
    return rows


def validate_guidance(root: Path = ROOT) -> list[str]:
    """Return sorted missing inventory, path, and token-limit errors."""
    try:
        limits = load_limits(root / BUDGETS_PATH, root)
        measured = measure(root)
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        return [str(exc)]
    errors: list[str] = []
    for skill in sorted(limits):
        for metric in sorted(METRICS):
            actual, maximum = measured[skill][metric], limits[skill][metric]
            if actual > maximum:
                errors.append(f"{skill}: {metric} measured {actual} tokens; limit {maximum}")
    return errors


def report(root: Path = ROOT) -> dict[str, dict[str, dict[str, int]]]:
    """Return measured tokens, limit, and headroom for every skill and metric."""
    limits = load_limits(root / BUDGETS_PATH, root)
    measured = measure(root)
    return {
        skill: {
            metric: {
                "measured": measured[skill][metric],
                "limit": limits[skill][metric],
                "headroom": limits[skill][metric] - measured[skill][metric],
            }
            for metric in sorted(METRICS)
        }
        for skill in sorted(limits)
    }


def _blueprint_runtime() -> ModuleType:
    """Import Blueprint's runtime, whose step parser owns the declared-text grammar."""
    scripts = str(ROOT / "skills" / "workbench" / "blueprint" / "scripts")
    sys.path.insert(0, scripts)
    try:
        return importlib.import_module("blueprint_runtime")
    finally:
        sys.path.remove(scripts)


def estimate_draft(text: str, root: Path = ROOT) -> dict[str, dict[str, dict[str, dict[str, int | bool]]]]:
    """Estimate budgets after a Blueprint draft's Exact blocks on agent-loaded guidance."""
    runtime = _blueprint_runtime()
    lines = text.replace("\r\n", "\n").split("\n")
    fenced = runtime._fenced_indexes(lines)
    # Section-shape diagnostics flag the empty sections every partial draft has.
    _names, spans, _shape = runtime._section_spans(lines, fenced)
    if "Implementation" not in spans:
        raise ValueError("draft has no ## Implementation section")
    start, end = spans["Implementation"]
    diagnostics: list[Any] = []
    headings = runtime._step_headings(lines, start=start, end=end, fenced=fenced, diagnostics=diagnostics)
    steps = runtime._parse_steps(lines, headings=headings, end=end, fenced=fenced, diagnostics=diagnostics)
    if diagnostics:
        raise ValueError(
            "draft instructions do not parse; repair with Blueprint check: "
            + "; ".join(str(diagnostic) for diagnostic in diagnostics)
        )
    limits = load_limits(root / BUDGETS_PATH, root)
    measured = measure(root)
    deltas: dict[tuple[str, str], int] = {}
    counts: dict[tuple[str, str], int] = {}
    for step in steps:
        for block in step.blocks:
            if block.kind != "exact":
                continue
            parts = PurePosixPath(block.path).parts
            if len(parts) == 4 and parts[0] == "skills" and parts[3] == "SKILL.md":
                metric = "top_level"
            elif len(parts) >= 5 and parts[0] == "skills" and parts[3] == "references" and "__pycache__" not in parts:
                metric = "references"
            else:
                continue
            skill = parts[2]
            if skill not in limits:
                raise ValueError(f"{block.path}: skill {skill!r} has no recorded context budget")
            replaced = 0 if block.old is None else count_tokens(block.old)
            key = (skill, metric)
            deltas[key] = deltas.get(key, 0) + count_tokens(block.text) - replaced
            counts[key] = counts.get(key, 0) + 1
    rows: dict[str, dict[str, dict[str, int | bool]]] = {}
    for skill in sorted({skill for skill, _metric in counts}):
        rows[skill] = {}
        for metric in sorted(METRICS):
            delta, spans_counted = deltas.get((skill, metric), 0), counts.get((skill, metric), 0)
            estimated = measured[skill][metric] + delta
            headroom = limits[skill][metric] - estimated
            rows[skill][metric] = {
                "measured": measured[skill][metric],
                "delta": delta,
                "estimated": estimated,
                "limit": limits[skill][metric],
                "headroom": headroom,
                "spans": spans_counted,
                "fits": headroom >= 4 * spans_counted,
            }
    return {"skills": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="measure live guidance against the committed limits")
    parser.add_argument("--format", choices=["json"], help="print per-skill measured tokens, limit, and headroom as one JSON object; exits 0 even when a limit is exceeded")
    parser.add_argument("--blueprint", metavar="DRAFT", help="estimate each skill's budgets after a Blueprint draft's Exact blocks on SKILL.md and references/ files; prints one JSON object and exits 0 even when an estimate does not fit")
    parser.add_argument("--write", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--compare-ref", help=argparse.SUPPRESS)
    parser.add_argument("--exclude-skill", action="append", default=[], help=argparse.SUPPRESS)
    args = parser.parse_args()
    modes = [args.check, args.format is not None, args.blueprint is not None]
    if args.write or args.compare_ref is not None or args.exclude_skill or sum(modes) != 1:
        parser.error("use exactly one of --check (verdict), --format json (per-skill usage report), or --blueprint DRAFT (draft estimate); write, comparison, and exclusions are retired")
    if args.blueprint is not None:
        try:
            result = estimate_draft(Path(args.blueprint).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    if args.format == "json":
        try:
            rows = report()
        except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps({"skills": rows}, sort_keys=True, separators=(",", ":")))
        return 0
    errors = validate_guidance()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("Guidance token budgets passed for all skills.")
    return 0

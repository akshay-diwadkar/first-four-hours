"""Read-only validation of discoverable, whitespace-normalized safety clauses."""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

INVENTORY = ROOT / "tests/repository/mandatory_skill_rules.json"
LINK_RE = re.compile(r"!?\[[^\]]*\]\((?:<([^>]+)>|([^)\s]+))")


def _skill_dirs(root: Path) -> dict[str, Path]:
    return {path.name: path for path in (root / "skills").glob("*/*") if (path / "SKILL.md").is_file()}


def _phase_roots(skill: Path, surface: str) -> set[Path]:
    if surface == "doctor":
        return {(skill / "SKILL.md").resolve()}
    manifest = json.loads((skill / "skill-protocol.json").read_text(encoding="utf-8"))
    phase = manifest["phases"][surface]
    templates = list(phase["required_reads"])
    for conditional in phase.get("conditional_reads", []):
        templates.extend(conditional["paths"])
    roots = set()
    for template in templates:
        prefix = "{skill_dir}/"
        if template.startswith(prefix):
            roots.add((skill / template[len(prefix) :]).resolve())
    return roots


def _reachable_markdown(roots: set[Path], skill: Path) -> set[Path]:
    reachable = set(roots)
    pending = list(roots)
    while pending:
        source = pending.pop()
        if source.suffix != ".md" or not source.is_file():
            continue
        for match in LINK_RE.finditer(source.read_text(encoding="utf-8")):
            target_text = match.group(1) or match.group(2)
            if target_text.startswith(("#", "http://", "https://", "mailto:")):
                continue
            target = (source.parent / target_text.split("#", 1)[0]).resolve()
            if target.is_relative_to(skill.resolve()) and target not in reachable:
                reachable.add(target)
                pending.append(target)
    return reachable


def inventory_errors(payload: list[dict[str, str]], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    skills = _skill_dirs(root)
    ids = [rule.get("id", "") for rule in payload]
    if len(ids) != len(set(ids)):
        errors.append("rule IDs must be unique")
    covered = {rule.get("skill") for rule in payload}
    if covered != set(skills):
        errors.append("inventory must cover every skill")
    for rule in payload:
        skill = skills.get(rule.get("skill", ""))
        if skill is None:
            errors.append(f"{rule.get('id')}: unknown skill")
            continue
        source = (skill / rule.get("source", "")).resolve()
        if not source.is_file() or not source.is_relative_to(skill.resolve()):
            errors.append(f"{rule.get('id')}: invalid source")
            continue
        text = " ".join(rule.get("text", "").split())
        if not text or text not in " ".join(source.read_text(encoding="utf-8").split()):
            errors.append(f"{rule.get('id')}: rule text is missing")
        try:
            roots = _phase_roots(skill, rule.get("surface", ""))
        except (KeyError, json.JSONDecodeError):
            errors.append(f"{rule.get('id')}: invalid required-read surface")
            continue
        if source not in _reachable_markdown(roots, skill):
            errors.append(f"{rule.get('id')}: source is not discoverable from required_reads")
    return errors



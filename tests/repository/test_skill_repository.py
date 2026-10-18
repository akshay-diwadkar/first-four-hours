from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "validation"))

import validate_repository as validator  # noqa: E402

def test_invocation_metadata_rejects_unsafe_or_contradictory_declarations(tmp_path: Path) -> None:
    source = REPO_ROOT / "skills" / "workbench" / "ticket"
    skill = tmp_path / "ticket"
    shutil.copytree(source, skill)
    assert validator.validate_frontmatter(skill) == []
    assert validator.validate_skill_invocation_metadata(skill, "user-invoked") == []

    errors = validator.validate_skill_invocation_metadata(skill, "both")
    assert any("authority-required capabilities" in error for error in errors)
    assert any("invocation controls must be absent for both" in error for error in errors)
    assert any("omit policy for both" in error for error in errors)

    sidecar = skill / "agents" / "openai.yaml"
    canonical = sidecar.read_text(encoding="utf-8")
    sidecar.write_text(canonical.replace("invocation: false", "invocation: true"), encoding="utf-8")
    errors = validator.validate_skill_invocation_metadata(skill, "user-invoked")
    assert any("allow_implicit_invocation must be false for user-invoked" in error for error in errors)

    sidecar.write_text(canonical.replace("policy:\n  allow_implicit_invocation: false\n", ""), encoding="utf-8")
    errors = validator.validate_skill_invocation_metadata(skill, "user-invoked")
    assert any("allow_implicit_invocation must be false for user-invoked" in error for error in errors)

    sidecar.write_text(canonical.replace('"Ticket"', '"Planner"'), encoding="utf-8")
    errors = validator.validate_skill_invocation_metadata(skill, "user-invoked")
    assert any("display_name must name the skill" in error for error in errors)

    sidecar.write_text(canonical.replace("interface:\n", 'interface:\n  icon_small: "./icon.svg"\n'), encoding="utf-8")
    errors = validator.validate_skill_invocation_metadata(skill, "user-invoked")
    assert any("unsupported or malformed sidecar" in error for error in errors)

    sidecar.write_text(re.sub(r'short_description: "[^"]*"', 'short_description: " "', canonical), encoding="utf-8")
    errors = validator.validate_skill_invocation_metadata(skill, "user-invoked")
    assert any("unsupported or malformed sidecar" in error for error in errors)

    skill_md = skill / "SKILL.md"
    original = skill_md.read_text(encoding="utf-8")
    skill_md.write_text(re.sub(r'version: "([^"]+)"', r"version: \1", original), encoding="utf-8")
    assert any("quoted Semantic Versioning string" in error for error in validator.validate_frontmatter(skill))

    skill_md.write_text(original.replace("\nmetadata:\n", "\nversion: 1.0.0\nmetadata:\n"), encoding="utf-8")
    assert any("frontmatter keys must be" in error for error in validator.validate_frontmatter(skill))

    skill_md.write_text(original.replace("\nmetadata:\n", '\nmetadata:\n  finalizer: "scripts/seal.py"\n'), encoding="utf-8")
    assert any("metadata keys must be version" in error for error in validator.validate_frontmatter(skill))

    # Published Agent Skills format limits on name and the decoded description.
    skill_md.write_text(re.sub(r"^name: .*$", "name: " + "t" * 65, original, count=1, flags=re.M), encoding="utf-8")
    assert any("at most 64 lowercase letters, digits, and hyphens" in error for error in validator.validate_frontmatter(skill))

    skill_md.write_text(re.sub(r"^name: .*$", "name: claude-ticket", original, count=1, flags=re.M), encoding="utf-8")
    assert any("reserved word 'claude'" in error for error in validator.validate_frontmatter(skill))

    skill_md.write_text(re.sub(r"^description: .*$", "description: " + "x" * 1025, original, count=1, flags=re.M), encoding="utf-8")
    assert any("at most 1024 characters" in error for error in validator.validate_frontmatter(skill))

    tagged = 'description: "Save records under `.learning/<subject>/`."'
    skill_md.write_text(re.sub(r"^description: .*$", lambda _: tagged, original, count=1, flags=re.M), encoding="utf-8")
    assert any("must not contain XML tags" in error for error in validator.validate_frontmatter(skill))

    undecodable = 'description: "Bad \\q escape"'
    skill_md.write_text(re.sub(r"^description: .*$", lambda _: undecodable, original, count=1, flags=re.M), encoding="utf-8")
    assert any("valid double-quoted string" in error for error in validator.validate_frontmatter(skill))

    folded = "description: >\n  Save records under `.learning/<subject>/`."
    skill_md.write_text(re.sub(r"^description: .*$", lambda _: folded, original, count=1, flags=re.M), encoding="utf-8")
    assert any("must be a single line" in error for error in validator.validate_frontmatter(skill))

    continued = "description: Save records\n  under `.learning/<subject>/`."
    skill_md.write_text(re.sub(r"^description: .*$", lambda _: continued, original, count=1, flags=re.M), encoding="utf-8")
    assert any("must be a single line" in error for error in validator.validate_frontmatter(skill))

    unindented = "description: 'Save records\nunder `.learning/<subject>/`.'"
    skill_md.write_text(re.sub(r"^description: .*$", lambda _: unindented, original, count=1, flags=re.M), encoding="utf-8")
    assert any("must be a single line" in error for error in validator.validate_frontmatter(skill))

    # Skill-owned contract versions follow their owning skill: an exact declaration
    # drifts on any bump, a consumer's built-against version only on a major one.
    parity_root = tmp_path / "parity"
    shutil.copytree(REPO_ROOT / "skills", parity_root / "skills", ignore=shutil.ignore_patterns("__pycache__"))
    assert validator.validate_contract_versions(parity_root) == []
    ticket_md = parity_root / "skills" / "workbench" / "ticket" / "SKILL.md"
    ticket_md.write_text(ticket_md.read_text(encoding="utf-8").replace('version: "1.0.0"', 'version: "1.1.0"', 1), encoding="utf-8")
    drifted = validator.validate_contract_versions(parity_root)
    assert any(error.startswith("skills/workbench/ticket/scripts/github_common.py:") for error in drifted), drifted
    assert not any("blueprint_runtime.py" in error for error in drifted), drifted
    ticket_md.write_text(ticket_md.read_text(encoding="utf-8").replace('version: "1.1.0"', 'version: "2.0.0"', 1), encoding="utf-8")
    broken = validator.validate_contract_versions(parity_root)
    assert sum("blueprint_runtime.py" in error for error in broken) == 2, broken
    # A skill version contract consumers cannot accept fails parity even when its exact declaration matches it.
    github_common = parity_root / "skills" / "workbench" / "ticket" / "scripts" / "github_common.py"
    ticket_md.write_text(ticket_md.read_text(encoding="utf-8").replace('version: "2.0.0"', 'version: "1.0.0-rc.1"', 1), encoding="utf-8")
    github_common.write_text(github_common.read_text(encoding="utf-8").replace('TICKET_VERSION = "1.0.0"', 'TICKET_VERSION = "1.0.0-rc.1"', 1), encoding="utf-8")
    assert 'TICKET_VERSION = "1.0.0-rc.1"' in github_common.read_text(encoding="utf-8")
    prerelease = validator.validate_contract_versions(parity_root)
    assert any(error.startswith("skills/workbench/ticket/scripts/github_common.py:") for error in prerelease), prerelease

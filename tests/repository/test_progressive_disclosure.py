from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "validation"))

import validate_repository as validator  # noqa: E402

def test_link_validation_rejects_broken_skill_and_atlas_wiki_links(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(validator, "ROOT", tmp_path)
    skill = tmp_path / "skills" / "workbench" / "fixture"
    references = skill / "references"
    references.mkdir(parents=True)
    (references / "orphan.md").write_text("# Orphan\n", encoding="utf-8")
    (skill / "SKILL.md").write_text(
        "[missing](references/missing.md)\n[escape](../../../../outside.md)\n",
        encoding="utf-8",
    )
    errors = validator.validate_markdown_references(skill)
    assert any("does not exist" in error for error in errors)
    assert any("escapes the repository" in error for error in errors)
    assert any("reference is not linked directly" in error for error in errors)

    # Without a root MAP.md the repository validator runs no Atlas check.
    assert validator.validate_atlas_wiki() == []
    wiki = {
        "MAP.md": "# Repository Map\n\n- [Validation](.map/validation/LANDMARK.md) — read for the runner.\n",
        ".map/validation/LANDMARK.md": "# Validation\n\n- [Runner](runner.md) — read when changing the runner.\n",
        ".map/validation/runner.md": "# Runner\n\n- [Runner entrypoint](../../tools/runner.py) — productive entrypoint.\n",
        "tools/runner.py": "",
    }
    for relative, text in wiki.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    assert validator.validate_atlas_wiki() == []
    # A rename outside the wiki breaks the Satellite pointer without touching a wiki path.
    (tmp_path / "tools" / "runner.py").rename(tmp_path / "tools" / "supervisor.py")
    errors = validator.validate_atlas_wiki()
    assert len(errors) == 1
    assert errors[0].startswith("Atlas wiki structure: map.link_broken: ")

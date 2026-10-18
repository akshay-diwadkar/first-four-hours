from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "validation"))

import validate_repository as validator  # noqa: E402
import sync_skill_catalog as catalog  # noqa: E402

def test_reference_checks_reject_broken_skill_docs_and_atlas_links(
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

    # Links in the user documentation must resolve too.
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("[Skills](skills/README.md)\n", encoding="utf-8")
    errors = validator.validate_documentation_links()
    assert len(errors) == 1
    assert "does not exist: skills/README.md" in errors[0]

    # Documentation names only declared handoff folders and active skill paths,
    # and the handoff page names every declared folder.
    errors = catalog.validate_documented_paths(
        {
            "docs/concepts/handoffs.md": "`.first-four-hours/routes/<slug>/route.md`\n",
            "docs/README.md": "See `.first-four-hours/reviews/` and `skills/workbench/router/SKILL.md`, not `tests/skills/router/x`.\n",
        },
        {"routes", "diagnoses"},
        {"skills/sensemaking/router"},
        "docs/concepts/handoffs.md",
    )
    assert sorted(errors) == [
        "docs/README.md: names .first-four-hours/reviews/, which no skill script declares",
        "docs/README.md: names skills/workbench/router, which is not an active skill folder",
        "docs/concepts/handoffs.md: missing the handoff folder .first-four-hours/diagnoses/",
    ]

    # The generated skill facts table must match its sources exactly.
    page = f"# Reference\n\n{catalog.TABLE_BEGIN}\n| old |\n{catalog.TABLE_END}\n"
    assert catalog.generated_block_errors(page, "| old |\n", "docs/reference/README.md") == []
    assert catalog.generated_block_errors(page, "| new |\n", "docs/reference/README.md") == [
        "docs/reference/README.md: skill facts table is stale; run python tools/validation/sync_skill_catalog.py --write"
    ]
    assert catalog.replace_generated_block(page, "| new |\n") == page.replace("| old |", "| new |")
    assert catalog.generated_block_errors("# Reference\n", "| new |\n", "docs/reference/README.md") != []

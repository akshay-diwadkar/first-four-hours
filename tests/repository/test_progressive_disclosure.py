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

    # Links in the user documentation and the root START_HERE front door must resolve too.
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("[Skills](skills/README.md)\n", encoding="utf-8")
    (tmp_path / "START_HERE.md").write_text("[Install](docs/missing.md)\n", encoding="utf-8")
    errors = validator.validate_documentation_links()
    assert sorted(errors) == [
        "START_HERE.md: local Markdown link target does not exist: docs/missing.md",
        "docs/README.md: local Markdown link target does not exist: skills/README.md",
    ]

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

    # Distribution has one plugin; source domains still classify documentation.
    import json
    import validate_npx_output as npx_output

    members = {"workbench": "fixture", "sensemaking": "reflection", "learning": "lesson"}
    paths = [f"./skills/{domain}/{name}" for domain, name in members.items()]
    for domain, name in members.items():
        folder = tmp_path / "skills" / domain / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SKILL.md").write_text("# Fixture\n", encoding="utf-8")
    monkeypatch.setattr(validator, "SKILLS_ROOT", tmp_path / "skills")
    monkeypatch.setattr(catalog, "ROOT", tmp_path)
    (tmp_path / "invocation-policy.json").write_text(
        json.dumps({"skills": {name: "both" for name in members.values()}}), encoding="utf-8"
    )
    legacy_plugins = [
        {"name": f"{domain}-skills", "source": "./", "skills": [path]}
        for domain, path in zip(members, paths)
    ]
    projected = catalog._projected_marketplace({
        "name": "first-four-hours", "owner": {"name": "Fixture"}, "plugins": legacy_plugins
    })
    assert [plugin["name"] for plugin in projected["plugins"]] == ["first-four-hours"]
    plugin = projected["plugins"][0]
    assert plugin["source"] == "./"
    assert plugin["skills"] == paths
    assert catalog.domain_groups() == {domain: [path] for domain, path in zip(members, paths)}
    table = catalog.skill_facts_table()
    for domain, name in members.items():
        assert f"| {domain.title()} | [`skills/{domain}/{name}/`]" in table

    marketplace = tmp_path / ".claude-plugin" / "marketplace.json"
    marketplace.parent.mkdir()
    monkeypatch.setattr(validator, "MARKETPLACE_PATH", marketplace)
    marketplace.write_text(json.dumps(projected), encoding="utf-8")
    assert validator.validate_marketplace() == []
    marketplace.write_text(json.dumps({**projected, "plugins": legacy_plugins}), encoding="utf-8")
    assert validator.validate_marketplace() != []
    missing = json.loads(json.dumps(projected))
    missing["plugins"][0]["skills"].pop()
    marketplace.write_text(json.dumps(missing), encoding="utf-8")
    assert validator.validate_marketplace() != []

    listing = "Found 3 skills\n\nFirst Four Hours\n" + "\n".join(members.values()) + "\n"
    assert npx_output.validate_output(listing) == []
    assert npx_output.validate_output(listing + "Workbench Skills\n") != []
    assert npx_output.validate_output(listing.replace("reflection\n", "")) != []
    assert npx_output.validate_output(listing + "fixture\n") != []

    # An alternate root keeps collection-only coverage, even without plugin metadata.
    # Stub the external npx provider; retain actual routing, snapshots, and policy checks.
    import shutil
    import subprocess
    import validate_skills_cli_install as installer

    foreign = tmp_path / "foreign"
    shutil.copytree(ROOT / "skills" / "workbench" / "architect", foreign / "skills" / "workbench" / "architect")
    (foreign / "invocation-policy.json").write_text(
        json.dumps({"skills": {"architect": "both"}}), encoding="utf-8"
    )
    calls = []

    def foreign_npx(argv, *, cwd, env=None):
        assert "--list" not in argv
        selected = argv[argv.index("--skill") + 1]
        calls.append(selected)
        assert selected == "*"
        selected_root = Path(argv[4])
        destination = Path(cwd) / ".agents" / "skills"
        destination.mkdir(parents=True)
        for source in sorted((selected_root / "skills").glob("*/*")):
            if source.is_dir() and (source / "SKILL.md").is_file():
                shutil.copytree(source, destination / source.name)
        (Path(cwd) / "skills-lock.json").write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    with monkeypatch.context() as scoped:
        scoped.setattr(validator, "ROOT", ROOT)
        scoped.setattr(validator, "SKILLS_ROOT", ROOT / "skills")
        scoped.setattr(installer.shutil, "which", lambda name: "fixture-npx")
        scoped.setattr(installer, "run_capture", foreign_npx)
        installer.validate_installs(foreign, "codex")
    assert calls == ["*"]

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

    # The documentation stays publishable to the flat GitHub wiki: every page has
    # one H1 title naming a unique wiki page, and links are rewritten for the wiki.
    from tools.wiki import publish_wiki

    (tmp_path / "REPO_VERSIONING.md").write_text("# Policy\n", encoding="utf-8")
    pages = {
        "README.md": "# Docs\n\n[Install](guide/install.md#cursor), [rules](../REPO_VERSIONING.md \"Policy\"), "
        "[top](#docs), [site](https://example.com/x.md), [gone](guide/gone.md)\n",
        "guide/install.md": "```text\n# Not a title\n```\n\n# Install it\n",
        "skills/README.md": "# install  it\n",
        "notes.md": "No title here.\n",
        "bad.md": "# A/B\n",
    }
    for relative, text in pages.items():
        page = tmp_path / "docs" / relative
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(text, encoding="utf-8")
    assert sorted(validator.validate_wiki_publication()) == [
        "GitHub wiki: docs/bad.md: title 'A/B' cannot name a wiki page",
        "GitHub wiki: docs/notes.md: has no H1 title",
        "GitHub wiki: docs/skills/README.md: wiki page name 'install-it' is also used by docs/guide/install.md",
    ]
    built, errors = publish_wiki.build_pages(tmp_path, "owner/repo", "main")
    assert built == {}
    assert "docs/README.md: link target does not exist: guide/gone.md" in errors
    for relative in ("skills/README.md", "notes.md", "bad.md"):
        (tmp_path / "docs" / relative).unlink()
    # A link error alone still blocks publication.
    assert validator.validate_wiki_publication() == []
    built, errors = publish_wiki.build_pages(tmp_path, "owner/repo", "main")
    assert built == {}
    assert errors == ["docs/README.md: link target does not exist: guide/gone.md"]
    # Without docs/README.md the wiki would have no Home page.
    (tmp_path / "docs" / "README.md").unlink()
    assert validator.validate_wiki_publication() == [
        "GitHub wiki: docs/README.md: missing, so the wiki has no Home page"
    ]
    (tmp_path / "docs" / "README.md").write_text(
        pages["README.md"].replace(", [gone](guide/gone.md)", ""), encoding="utf-8"
    )
    assert validator.validate_wiki_publication() == []
    built, errors = publish_wiki.build_pages(tmp_path, "owner/repo", "main")
    assert errors == []
    assert sorted(built) == ["Home", "Install-it"]
    assert built["Home"] == (
        "<!-- Generated from docs/README.md by tools/wiki/publish_wiki.py. Edit that file in the repository; "
        "changes made on the wiki are overwritten. -->\n"
        "# Docs\n\n[Install](https://github.com/owner/repo/wiki/Install-it#cursor), "
        "[rules](https://github.com/owner/repo/blob/main/REPO_VERSIONING.md \"Policy\"), "
        "[top](#docs), [site](https://example.com/x.md)\n"
    )

    # The command writes exactly the built live pages, LF-only, and never into an existing folder.
    live, errors = publish_wiki.build_pages(ROOT, "owner/repo", "main")
    assert errors == []
    output = tmp_path / "wiki-pages"
    arguments = ["--repository", "owner/repo", "--branch", "main", "--output", str(output)]
    assert publish_wiki.main(arguments) == 0
    assert sorted(path.name for path in output.iterdir()) == sorted(f"{name}.md" for name in live)
    assert "Home" in live
    for name, text in live.items():
        assert (output / f"{name}.md").read_bytes() == text.encode("utf-8")
    (output / "Home.md").unlink()
    assert publish_wiki.main(arguments) == 1
    assert not (output / "Home.md").exists()

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
    # The Cursor manifests list the same domain-tree skills, and the catalog check compares them exactly.
    cursor_plugin = catalog._projected_cursor_plugin()
    assert cursor_plugin == {"name": "first-four-hours", "description": plugin["description"], "skills": paths}
    cursor_marketplace = catalog._projected_cursor_marketplace()
    assert cursor_marketplace["plugins"] == [
        {"name": "first-four-hours", "source": "./", "description": plugin["description"]}
    ]
    cursor = tmp_path / ".cursor-plugin"
    missing_errors = catalog.cursor_manifest_errors(cursor)
    assert [error.split(" unreadable: ")[0] for error in missing_errors] == [
        ".cursor-plugin/plugin.json", ".cursor-plugin/marketplace.json"
    ]
    cursor.mkdir()
    (cursor / "plugin.json").write_text(json.dumps(cursor_plugin), encoding="utf-8")
    (cursor / "marketplace.json").write_text(json.dumps(cursor_marketplace), encoding="utf-8")
    assert catalog.cursor_manifest_errors(cursor) == []
    (cursor / "plugin.json").write_text(json.dumps({**cursor_plugin, "skills": paths[:-1]}), encoding="utf-8")
    stale = ".cursor-plugin/plugin.json is not derived from the current domain tree"
    assert catalog.cursor_manifest_errors(cursor) == [stale]
    assert stale in catalog.check()
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

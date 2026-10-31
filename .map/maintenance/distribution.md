# Distribution and catalog

- [Repository overview](../../README.md): start with the product front door: the install command, first use, the domain catalog of every public skill, and links into the documentation; the installation guide names the agents the install check covers.
- [User documentation](../../docs/README.md): find the human documentation entrypoint, its getting-started guides, concept pages, one page per skill, recipes for recurring problems, a reference with the generated skill facts table, and symptom-indexed troubleshooting; skill contracts stay authoritative, and catalog synchronization checks the skill index, the facts table, documented handoff folders, and skill paths against source.
- [Catalog synchronization](../../tools/validation/sync_skill_catalog.py): trace source-owned domains into documentation and reference facts separately from the generated Claude Code and Cursor plugin manifests; also check README catalogs, documented skill paths, and declared `.first-four-hours/` folders.
- [Router manifest synchronization](../../tools/validation/sync_router_manifest.py): project skill frontmatter into Router's capability manifest; a changed skill description changes Router's distributed assets too.
- [Invocation policy](../../invocation-policy.json): inspect suite invocation policy alongside the affected package's metadata.
- [Installation validation](../../tools/validation/validate_skills_cli_install.py): investigate Skills CLI listing groups, collection installation, and isolated selection for the active checkout, plus collection-only checks for alternate roots.
- [Claude Code plugin validation](../../tools/validation/validate_claude_plugin_install.py): investigate the single native plugin's installation, Claude Code skill discovery, and installed-copy parity in a temporary Claude Code configuration.
- [Release policy](../../REPO_VERSIONING.md#skill-versions): start at Skill Versions and read through Release Metadata for the authoritative coupling between affected skill versions, repository release metadata, dependency inputs, and required verification.
- [Release history](../../CHANGELOG.md): read released and unreleased user-visible changes; release policy says when to add an entry.

Domain membership comes from the skill tree; catalog metadata is derived from it. Use the synchronization entrypoint when that membership changes, and consult release policy before treating a repository-only edit as a distributed behavior change.

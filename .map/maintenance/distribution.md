# Distribution and catalog

- [Repository overview](../../README.md): start with installation, supported agent surfaces, domain intent, and the public capability catalog.
- [Catalog synchronization](../../tools/validation/sync_skill_catalog.py): trace filesystem-owned domain membership into marketplace metadata and README validation.
- [Router manifest synchronization](../../tools/validation/sync_router_manifest.py): project skill frontmatter into Router's capability manifest; a changed skill description changes Router's distributed assets too.
- [Invocation policy](../../invocation-policy.json): inspect suite invocation policy alongside the affected package's metadata.
- [Installation validation](../../tools/validation/validate_skills_cli_install.py): investigate collection installation and agent-specific distribution checks.
- [Release policy](../../REPO_VERSIONING.md): follow the authoritative coupling between affected skill versions, repository release metadata, dependency inputs, and required verification.
- [Release history](../../CHANGELOG.md): read released and unreleased user-visible changes; release policy says when to add an entry.

Domain membership comes from the skill tree; catalog metadata is derived from it. Use the synchronization entrypoint when that membership changes, and consult release policy before treating a repository-only edit as a distributed behavior change.

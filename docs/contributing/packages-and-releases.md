# Maintain packages and releases

Use the [contributor guide](README.md) to bound a change, [validation](validation.md) to select its proof, and the [documentation rules](documentation.md) to maintain human explanations. The [versioning and validation policy](../../REPO_VERSIONING.md) owns version, release, dependency, and required-check decisions.

## Keep a skill standalone

Each skill lives under `skills/<domain>/<skill>/` and must operate after installation without this repository's `tools/` directory. A skill that needs packages declares only its own packages in its optional `requirements.txt`. The [release requirements](../../tools/validation/release-requirements.txt) include those skill requirements and add validation tools. Change a requirements file only when its declared packages change.

The [CLI protocol](../../tools/skill_protocol/README.md) owns manifests and standalone adapters. The [invocation policy](../../invocation-policy.json) records invocation authority alongside package metadata. Domains organize capabilities; activation and permission remain capability-specific.

## Update the source, then its projections

Edit the canonical source before updating distributed copies. Use the synchronizer for the affected mechanism:

| Task | Authoritative source | Projection action |
| :--- | :--- | :--- |
| Common CLI runtime | [Protocol runtime](../../tools/skill_protocol/runtime.py) | [Sync the protocol runtime](../../tools/validation/sync_skill_protocol_runtime.py). |
| Diagnostic runtime | [Diagnostic runtime](../../tools/diagnostics/runtime.py) | [Sync diagnostics](../../tools/validation/sync_diagnostic_runtime.py). |
| Classification runtime | [Classification runtime](../../tools/classification/runtime.py) | [Sync classification](../../tools/validation/sync_classification_runtime.py). |
| Architecture handoff verifiers | Architect's [contract](../../skills/workbench/architect/scripts/architecture_contract.py) and [handoff runtime](../../skills/workbench/architect/scripts/architecture_handoff.py) | [Sync architecture handoffs](../../tools/validation/sync_architecture_handoff.py). |
| Delegation doctrine | [Skill philosophy](../../SKILL_PHILOSOPHY.md) | [Sync delegation projections](../../tools/validation/sync_delegation_projection.py). |
| Router capability metadata | Active skills' `SKILL.md` frontmatter | [Sync the Router manifest](../../tools/validation/sync_router_manifest.py). |
| Catalog membership and reference facts | Active skill folders and their metadata | [Sync the skill catalog](../../tools/validation/sync_skill_catalog.py). |

Every listed synchronizer accepts `--check` to detect drift without updating projections. The catalog writer requires `--write`; the other listed synchronizers update when invoked without `--check`. Run only the affected writer, then review its output. The complete [repository validator](../../tools/validation/validate_repository.py) checks projection parity.

For example, regenerate Router metadata after a relevant frontmatter change:

```bash
python tools/validation/sync_router_manifest.py
```

Regenerate catalog membership and reference facts after their sources change:

```bash
python tools/validation/sync_skill_catalog.py --write
```

These examples run from the repository root. Catalog writing updates derived marketplace membership and the generated facts block in the [reference](../reference/README.md). Maintain affected human skill pages, their [index](../skills/README.md), and the repository README catalog separately as their checks require. The writer does not author that prose.

Blueprint and Construct also share paired `scripts/blueprint_runtime.py` files with no synchronizer. When changing that runtime, update both copies identically and include proof covering their consumer, as Planning traps in the [versioning policy](../../REPO_VERSIONING.md) require. Use the existing source and projection mechanisms; do not invent a parallel synchronizer or hand-edit generated copies.

## Check distribution when it changes

The [repository validator](../../tools/validation/validate_repository.py) checks package metadata and projection consistency. The [Skills CLI installation check](../../tools/validation/validate_skills_cli_install.py) installs the collection for a selected agent, compares each installed package's files with source, and validates its invocation metadata.

This command exercises collection selection with `--skill '*'`. It does not exercise isolated `--skill <name>` installations, so a passing result establishes collection-install coverage only:

```bash
python tools/validation/validate_skills_cli_install.py --agent codex
```

This is an affected-agent example. The other accepted agents are `claude-code` and `github-copilot`. Run the check for the affected agent when package distribution changes, following the [policy](../../REPO_VERSIONING.md).

The check requires Node, `npx`, and network access. It uses the Skills CLI version pinned by the repository validator, installs into temporary consumer directories, compares installed copies and policy metadata, and cleans up. Keep that pin in its source rather than maintain another version table. Report unavailable or incomplete installation proof as incomplete.

Routine human-documentation changes do not need a network installation check. The installer verifies the Skills CLI surface for the selected agent; native Claude Code plugin completion remains separate work and must not be claimed from these checks or inferred from marketplace metadata.

## Apply versions to the final diff

Read Skill Versions, Contract Versions, Release Metadata, and the First Four Hours v1 Baseline in the [versioning authority](../../REPO_VERSIONING.md) before changing version fields.

Determine Semantic Versioning impact from the final user-visible behavior and distribution diff against the merge base. Version only affected skills, and set the version once after scope is stable. Rework that changes the required impact level recalculates from the merge-base version; routine pre-merge fixes do not accumulate extra increments.

When policy calls for a skill version change, update its `metadata.version`, owned contract constants and templates, required projections, and consumer built-against compatibility as the authority specifies. A skill owns the version of its formats; consumers accept the producer major they were built against. The repository validator checks declared version relationships.

Keep [VERSION](../../VERSION) as one repository release value and [CHANGELOG.md](../../CHANGELOG.md) as the single release history. Repository-only human documentation, tests, and formatting require no version bump or changelog entry unless they change installation, packaging, release output, or distributed behavior.

The current First Four Hours baseline holds repository, skill, and owned contract versions at `1.0.0` until the baseline is established. Its first release publishes Unreleased as `1.0.0` without an increment. Apply that policy exception before ordinary version arithmetic; this documentation change needs no bump.

## Prepare a release from maintained truth

Use the maintained release rule to turn the entries under Unreleased in [CHANGELOG.md](../../CHANGELOG.md) into a repository release. Update [VERSION](../../VERSION), publish the dated changelog section, retain a new Unreleased section, tag the release, and reuse its changelog entry for the release notes. The [versioning authority](../../REPO_VERSIONING.md) supplies the values, ordering, and first-baseline exception. The README's release badge reads the latest GitHub release and has no version to edit.

These are maintainer actions; no automated release pipeline or workflow file is promised. Complete required [validation](validation.md), the installation checks earned by affected distribution, and human review before declaring readiness. Keep native Claude plugin work with its owning change and update documentation when that behavior ships. Never merge a pull request.

# Maintain packages and releases

Use the [contributor guide](README.md) to bound a change, [validation](validation.md) to select its proof, and the [documentation rules](documentation.md) to maintain human explanations. The [versioning and validation policy](https://github.com/akshay-diwadkar/first-four-hours/blob/main/REPO_VERSIONING.md) owns version, release, dependency, and required-check decisions.

## Keep a skill standalone

Each skill lives under `skills/<domain>/<skill>/` and must operate after installation without this repository's `tools/` directory. A skill that needs packages declares only its own packages in its optional `requirements.txt`. The [release requirements](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/release-requirements.txt) include those skill requirements and add validation tools. Change a requirements file only when its declared packages change.

The [CLI protocol](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/skill_protocol/README.md) owns manifests and standalone adapters. The [invocation policy](https://github.com/akshay-diwadkar/first-four-hours/blob/main/invocation-policy.json) records invocation authority alongside package metadata. Domains organize capabilities; activation and permission remain capability-specific.

Examiner ships one [paper runtime](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/learning/examiner/assets/paper-runtime.html) that every on-screen practice paper copies unchanged, so the timed behaviour has one source. The repository validator refuses it when it names a URL, a network call, a module import, an external resource, or a page navigation. The [paper runtime exercise](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/exercise_paper_runtime.py) copies it into a [throwaway paper](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/paper_runtime_fixture.html) and drives a headless Chrome or Edge through the clock, question list, review flags and their orange marking, the wide-screen side menu, a second tab, reload and reopen, rest breaks, the break between parts, submission, expiry, saving and loading answer files, and blocked storage. It is not part of the required suite. Run it when the runtime or the fixture changes:

```bash
python tools/validation/exercise_paper_runtime.py
```

## Update the source, then its projections

Edit the canonical source before updating distributed copies. Use the synchronizer for the affected mechanism:

| Task | Authoritative source | Projection action |
| :--- | :--- | :--- |
| Common CLI runtime | [Protocol runtime](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/skill_protocol/runtime.py) | [Sync the protocol runtime](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/sync_skill_protocol_runtime.py). |
| Diagnostic runtime | [Diagnostic runtime](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/diagnostics/runtime.py) | [Sync diagnostics](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/sync_diagnostic_runtime.py). |
| Classification runtime | [Classification runtime](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/classification/runtime.py) | [Sync classification](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/sync_classification_runtime.py). |
| Learning scaffold and check runtime | [Learning runtime](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/learning/runtime.py) and its `tools/learning/templates/` | [Sync the learning runtime](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/sync_learning_runtime.py). |
| Architecture handoff verifiers | Architect's [contract](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/architect/scripts/architecture_contract.py) and [handoff runtime](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/architect/scripts/architecture_handoff.py) | [Sync architecture handoffs](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/sync_architecture_handoff.py). |
| Delegation doctrine | [Skill philosophy](https://github.com/akshay-diwadkar/first-four-hours/blob/main/SKILL_PHILOSOPHY.md) | [Sync delegation projections](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/sync_delegation_projection.py). |
| Router capability metadata | Active skills' `SKILL.md` frontmatter | [Sync the Router manifest](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/sync_router_manifest.py). |
| Catalog membership and reference facts | Active skill folders and their metadata | [Sync the skill catalog](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/sync_skill_catalog.py). |

Every listed synchronizer accepts `--check` to detect drift without updating projections. The catalog writer requires `--write`; the other listed synchronizers update when invoked without `--check`. Run only the affected writer, then review its output. The complete [repository validator](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/validate_repository.py) checks projection parity.

For example, regenerate Router metadata after a relevant frontmatter change:

```bash
python tools/validation/sync_router_manifest.py
```

Regenerate catalog membership and reference facts after their sources change:

```bash
python tools/validation/sync_skill_catalog.py --write
```

These examples run from the repository root. Catalog writing updates derived marketplace membership, the Cursor plugin manifest, and the generated facts block in the [reference](../reference/README.md). Maintain affected human skill pages, their [index](../skills/README.md), and the repository README catalog separately as their checks require. The writer does not author that prose.

Blueprint and Construct also share paired `scripts/blueprint_runtime.py` files with no synchronizer. When changing that runtime, update both copies identically and include proof covering their consumer, as Planning traps in the [versioning policy](https://github.com/akshay-diwadkar/first-four-hours/blob/main/REPO_VERSIONING.md) require. Use the existing source and projection mechanisms; do not invent a parallel synchronizer or hand-edit generated copies.

## Check distribution when it changes

The [repository validator](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/validate_repository.py) checks package metadata and projection consistency. The [Skills CLI installation check](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/validate_skills_cli_install.py) compares installed package files and invocation metadata with source for a selected agent.

From this checkout, the command below also checks that the listing has one `First Four Hours` group with every canonical skill name, installs the collection with `--skill '*'`, and installs Diagnose alone with `--skill diagnose`. It does not exercise every isolated skill or every agent. When `--repo-root` selects another directory, the command retains collection-only coverage and reports that narrower result:

```bash
python tools/validation/validate_skills_cli_install.py --agent codex
```

This is an affected-agent example. The other accepted agents are `claude-code` and `github-copilot`. Run the check for the affected agent when package distribution changes, following the [policy](https://github.com/akshay-diwadkar/first-four-hours/blob/main/REPO_VERSIONING.md).

The check requires Node and `npx`, plus the cached pinned Skills CLI or registry access. It uses the version pinned by the repository validator, installs into temporary consumer directories, compares installed copies and policy metadata, and cleans up. Keep that pin in its source rather than maintain another version table. Report unavailable or incomplete installation proof as incomplete.

Routine human-documentation changes do not need a network installation check. The Skills CLI check verifies only the Skills CLI surface for the selected agent; it says nothing about the Claude Code plugin.

The [Claude Code plugin installation check](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/validate_claude_plugin_install.py) copies the files a commit of this checkout would publish (tracked and untracked files that Git does not ignore) into a temporary marketplace, runs `claude plugin validate --strict` on it, installs its single plugin into a temporary Claude Code configuration, confirms that Claude Code lists only `first-four-hours@first-four-hours` as enabled and discovers every canonical skill, compares each installed skill's files with source, and validates its invocation metadata. It needs the `claude` CLI, never touches your own Claude Code configuration, and removes its temporary configuration. Run it when the marketplace, plugin packaging, or skill membership changes:

```bash
python tools/validation/validate_claude_plugin_install.py
```

It installs from a copy of the local checkout, not from GitHub. After a merge that changes plugin packaging, install from `akshay-diwadkar/first-four-hours` as the [installation guide](../getting-started/installation.md) shows.

The Cursor plugin and marketplace manifests, `.cursor-plugin/plugin.json` and `.cursor-plugin/marketplace.json`, are written by catalog writing and checked by the repository validator. No command-line installation check exists for Cursor: when plugin packaging or skill membership changes, install the plugin locally as the [installation guide](../getting-started/installation.md#install-as-a-cursor-plugin) shows and confirm in Cursor that every skill is listed.

## Apply versions to the final diff

Read Skill Versions, Contract Versions, Release Metadata, and the First Four Hours v1 Baseline in the [versioning authority](https://github.com/akshay-diwadkar/first-four-hours/blob/main/REPO_VERSIONING.md) before changing version fields.

Determine Semantic Versioning impact from the final user-visible behavior and distribution diff against the merge base. Version only affected skills, and set the version once after scope is stable. Rework that changes the required impact level recalculates from the merge-base version; routine pre-merge fixes do not accumulate extra increments.

When policy calls for a skill version change, update its `metadata.version`, owned contract constants and templates, required projections, and consumer built-against compatibility as the authority specifies. A skill owns the version of its formats; consumers accept the producer major they were built against. The repository validator checks declared version relationships.

Keep [VERSION](https://github.com/akshay-diwadkar/first-four-hours/blob/main/VERSION) as one repository release value and [CHANGELOG.md](https://github.com/akshay-diwadkar/first-four-hours/blob/main/CHANGELOG.md) as the single release history. Repository-only human documentation, tests, and formatting require no version bump or changelog entry unless they change installation, packaging, release output, or distributed behavior.

The first release, `1.0.0`, established the First Four Hours baseline, so ordinary version arithmetic applies to every later change.

## Prepare a release from maintained truth

Use the maintained release rule to turn the entries under Unreleased in [CHANGELOG.md](https://github.com/akshay-diwadkar/first-four-hours/blob/main/CHANGELOG.md) into a repository release. Update [VERSION](https://github.com/akshay-diwadkar/first-four-hours/blob/main/VERSION), publish the dated changelog section, retain a new Unreleased section, tag the release, and reuse its changelog entry for the release notes. The [versioning authority](https://github.com/akshay-diwadkar/first-four-hours/blob/main/REPO_VERSIONING.md) supplies the values and ordering. The README's release badge reads the latest GitHub release and has no version to edit.

These are maintainer actions; no automated release pipeline or workflow file is promised. Complete required [validation](validation.md), the installation checks earned by affected distribution, including the Claude Code plugin check when plugin packaging changes, and human review before declaring readiness. Never merge a pull request.

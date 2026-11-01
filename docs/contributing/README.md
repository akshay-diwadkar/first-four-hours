# Contributing to First Four Hours

Use this guide to locate the owner of a change, update its affected surfaces, and prepare it for review. The linked policies and source files own the rules; this guide connects the steps.

## Start here

Set up the validation environment through [Contributing](https://github.com/akshay-diwadkar/first-four-hours/blob/main/CONTRIBUTING.md). Read the [agent working rules](https://github.com/akshay-diwadkar/first-four-hours/blob/main/AGENTS.md) when an agent makes the change, the [skill design philosophy](https://github.com/akshay-diwadkar/first-four-hours/blob/main/SKILL_PHILOSOPHY.md) before designing or reviewing a skill, and the [versioning and validation policy](https://github.com/akshay-diwadkar/first-four-hours/blob/main/REPO_VERSIONING.md) for branches, versions, tests, and required proof.

These sources and the affected skill contract provide the contribution requirements. You do not need to reconstruct issue history.

## Choose the change boundary

Classify a new public capability by its primary owned job:

| Domain | Primary owned job |
| :--- | :--- |
| Workbench | Understand, represent, plan, change, or verify project/repository state or its change lifecycle. |
| Sensemaking | Improve decision readiness through reasoning, exploration, communication, or coordination. |
| Learning | Build a person's knowledge and ability in any subject, technical or nontechnical. |

Once investigation and design provide enough evidence, assign exactly one domain before package/release convergence. If none fits, revisit the hierarchy explicitly rather than add dual membership or another domain as a local workaround.

Domains organize the source and catalog. Invocation authority stays with each capability, Router routes concrete capabilities, and affected risk determines validation scope. The generated [skill facts table](../reference/README.md) supplies current capability membership and invocation facts.

## Put the change with its owner

| Surface | Where it belongs |
| :--- | :--- |
| Agent behavior and instructions | `skills/<domain>/<skill>/SKILL.md` and that skill's owned `references/`. |
| A skill's runtime and resources | Its local `scripts/`, `schemas/`, `assets/`, `skill-protocol.json`, `agents/openai.yaml`, and `requirements.txt`, where present. |
| Canonical shared mechanisms | Their owning source under `tools/`, followed by the required package projections. |
| Skill-specific tests, including integrations | `tests/skills/<skill>/`. |
| Tests of genuinely common mechanisms | `tests/repository/` or `tests/skill_protocol/`. |
| Human documentation | The reader-job section under `docs/`. |

Use only the resources a package needs; this table is not mandatory scaffolding. The [CLI protocol](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/skill_protocol/README.md) explains manifests and adapters. [Validation](validation.md) explains proof ownership, and [packages and releases](packages-and-releases.md) explains shared sources and standalone distribution.

## Make a normal capability change

1. Establish the desired outcome and inspect current behavior, the affected skill contract, and its owned references. Apply the philosophy's Change Gate to the proposed change.
2. Bound the files, affected consumers, and preserved behavior. Classify a new capability by its primary job; use concrete ownership to select work and tests.
3. Before editing agent-loaded guidance, [measure its context usage](validation.md) and inspect pinned instruction rules. Remove sediment and disclose exceptional detail progressively while preserving required meaning.
4. Update the canonical implementation or guidance, then its required projections, affected consumer contracts, earned tests, and [human documentation](documentation.md).
5. Once the final observable diff is stable, apply [version and release policy](packages-and-releases.md) to the affected skills and owned formats.
6. Run the smallest relevant deterministic proof, expand by affected risk, and finish the [required validation](validation.md) on the final relevant revision.

Agents retain semantic judgment within each skill's authority. Choose only the capabilities the task needs; this workflow does not require a fixed skill pipeline or a consultation on every decision. Follow the affected skill's own invocation, consultation, and handoff contract.

## Keep outputs and documentation honest

The [handoff guide](../concepts/handoffs.md) distinguishes ignored repository-local session handoffs from committable deliverables. Preserve that ownership when changing a producer or consumer. Use its maintained placement rules rather than introduce a parallel folder inventory or shared workspace runtime.

When public behavior changes, update every affected consumer contract and human explanation. When a capability is retired, remove its membership and references cleanly; do not leave compatibility placeholders for taxonomy symmetry. Reuse the generated [reference facts](../reference/README.md) instead of copying the capability catalog into another page.

Skill contracts remain authoritative for implemented behavior. If intended behavior is absent, report the concrete mismatch and its owner. Do not describe it as shipped or silently expand a documentation job into capability implementation. Follow the existing [documentation rules](documentation.md) for source grounding, navigation, examples, and voice.

## Prepare the pull request

Check the readiness guidance in [validation](validation.md), the governing [versioning policy](https://github.com/akshay-diwadkar/first-four-hours/blob/main/REPO_VERSIONING.md), and the [documentation rules](documentation.md). Explain the concrete problem and resulting behavior, report the validation actually completed, and disclose remaining limitations or owner review. If tests were added, briefly identify the uncovered behavior and the incorrect result they catch.

Review must assess meaning and preserved behavior as well as mechanical checks. Tests establish only the mechanics and evidence they exercise; they do not establish universal agent quality or quantified time savings. Never merge a pull request.

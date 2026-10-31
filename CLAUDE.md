# CLAUDE.md

## Skill Design

Before creating, reviewing, or changing a skill, read [SKILL_PHILOSOPHY.md](SKILL_PHILOSOPHY.md) and apply its Change Gate.

## Repository Changes

Before changing skills, packaging, validators, dependencies, runtime requirements, release configuration, tests, fixtures, or verification commands, read [REPO_VERSIONING.md](REPO_VERSIONING.md) and follow its guidance, including [Adding or changing tests](REPO_VERSIONING.md#adding-or-changing-tests). Never merge a PR.

## Testing Rules

Before changing tests, read [Adding or changing tests](REPO_VERSIONING.md#adding-or-changing-tests) and obey the [suite limits](REPO_VERSIONING.md#suite-size-cap): at most three collected cases per skill, 12 shared, 48 total, with a complete passing repository suite within 120 seconds. Skill-specific tests, including integrations, belong under `tests/skills/<skill>/`. Three is a ceiling, not a quota; strengthen or replace coverage when slots are full. Add tests only for real defects or missing acceptance behavior, not mundane fixture/formatting bookkeeping or implementation-detail assertions. Testing and repairs proceed automatically without approval; incomplete verification never counts as a pass.

<!-- ATLAS 1 -->
## Atlas

Atlas `setup-guidance` copied the rest of this section from `MAP.md`: follow only relevant links, and search project files directly when none fits. Update affected map pointers when files move or change meaning, and rerun `setup-guidance` after editing `MAP.md`; run Atlas `check`/`baseline` only for drift audits.

Project files are authoritative. This map offers selective orientation, not exhaustive coverage; inspect current sources before deciding or changing anything.

- [Project workflows](.map/workbench/LANDMARK.md): follow for project definition, investigation, architecture, planning, execution, review, tickets, and project orientation.
- [Reasoning and communication](.map/sensemaking/LANDMARK.md): follow for capability routing, decision support, research, and technical documents.
- [Learning](.map/learning/LANDMARK.md): follow for teaching a person any subject, written-examination practice and marking, and the `.learning/` records and study plan learning skills share.
- [Repository maintenance](.map/maintenance/LANDMARK.md): follow for contribution rules, standalone runtime contracts, validation, and distribution, including what a skill-guidance edit must fit or change with it.
<!-- /ATLAS -->

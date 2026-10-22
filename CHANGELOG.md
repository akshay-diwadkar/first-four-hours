# Changelog

All notable changes to First Four Hours are recorded in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). [Release Metadata](REPO_VERSIONING.md#release-metadata) says when to add an entry and how a release is prepared.

## [Unreleased]

First Four Hours starts its version history at 1.0.0. Earlier release history stays in the `akshay-diwadkar/skills` repository.

### Added

- Claude Code plugin installation. On Claude Code 2.1.275 or later, install all 15 skills as the `first-four-hours` plugin with `/plugin install first-four-hours --marketplace akshay-diwadkar/first-four-hours`. Plugin skills start as `/first-four-hours:<skill>`, for example `/first-four-hours:diagnose`.
- Charter 1.0.0: a user-invoked Workbench skill, started with `/charter`, that turns a rough ambition for a whole project into one agreed, resumable `.first-four-hours/charters/<slug>/charter.md`. On request it publishes the charter as one GitHub umbrella issue after you confirm the exact text, and never creates tickets.

### Changed

- The Claude Code marketplace and its single plugin are named `first-four-hours`, giving install id `first-four-hours@first-four-hours`. Users of the retired marketplace or the three preview plugins should follow [Replace an earlier plugin installation](docs/getting-started/installation.md#replace-an-earlier-plugin-installation) to remove the old entries before installing the single plugin.
- The repository, every skill, and every contract version the repository owns are now 1.0.0. A skill's version is also the version of every artifact, handoff, receipt, bundle, and state format it owns.
- A consumer accepts another minor or patch version of the same major and refuses any other version.
- Blueprint 1.0.0: before attacking a draft, the fresh challenger walks it in step order and reports any Proof run or Run that needs something only a later step creates, or that works only outside the way Construct launches it: as its own arguments with no shell, from the repository root, in Construct's inherited environment. Planners probe load-bearing commands the same way.
- Construct 1.0.0: the final report lists each after-implementation verification Run with its `Expect:` and whether the output met it, so every check's verdict can be read without rerunning it.
- Architect, Assess, Atlas, Construct, Ideate, PR, Reason, Scribe, and Ticket 1.0.0 name `charter` among the skills whose suggested next step you run yourself, and Router 1.0.0 knows Charter's handoff to Ticket.

### Removed

- Support for artifacts, receipts, and state written under earlier internal versions. Reseal or regenerate them with the current skills.

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
- Blueprint 1.0.0: before attacking a draft, the fresh challenger walks it in step order and reports any Proof run or Run that needs something not yet created at its phase (a Before implementation Run comes before every instruction), or that works only outside the way Construct launches it: as its own arguments with no shell, from the repository root, in Construct's inherited environment. Planners probe load-bearing commands the same way.
- Blueprint 1.0.0: planners and challengers load a smaller core planning contract on every run. Tracing command dispatch, authoring new step proof, and invoking Ideate are read only when that branch applies. Each Completion Condition is now the one statement of its outcome: a concrete example that names the Run, Proof run, or Exact-text step that shows it, or its owner for an `Owner gate:`. The Goal keeps only its summary. Plans sealed earlier stay valid.
- Blueprint 1.0.0: the fresh challenger now writes the review that a literally built plan would fail, seeded from the repository's planning traps and any review findings in the request. The challenger first checks the plan's tier itself. A plan is elevated if it creates, changes, or deletes code that runs or the configuration it reads, edits something under a budgeted or deadline gate, propagates across skills or packages, has irreversible or outward-facing effects, or changes the seal runtime. An elevated plan's challenger also works through the full attack dimensions, on a model at least as capable as the planner. Every other plan gets the shorter pre-mortem brief and the cheapest capable challenger. Every plan is still challenged.
- Blueprint 1.0.0: the planner first lists the facts its decisions depend on and sends independent questions that are worth delegating to cheap read-only workers together, one question each, keeping tiny or dependent questions local. A sealed plan for a similar task may seed a new plan's structure, but every premise and decision taken from it is re-checked against current source and never cited as evidence.
- Construct 1.0.0: the final report lists each after-implementation verification Run with its `Expect:` and whether the output met it, so every check's verdict can be read without rerunning it.
- Atlas 1.0.0: Satellite pages mark where to start reading, cue each other link by the task that needs it, and say when a kind of task has read enough. Navigating agents read the start target first and follow only matching links and cross-links. When a file moves or changes meaning, the agent searches `.map/` for its path to update every pointer citing it. An agent whose work edits files also fixes a cue that misled it, unless its skill limits Atlas upkeep as Construct does.
- Architect, Assess, Atlas, Construct, Ideate, PR, Reason, Scribe, and Ticket 1.0.0 name `charter` among the skills whose suggested next step you run yourself, and Router 1.0.0 knows Charter's handoff to Ticket.
- Examiner 1.0.0: an on-screen practice paper behaves like a timed examination. A countdown you cannot pause or extend except by a declared access arrangement (extra time, supervised rest breaks), a question list with answered, not answered, and flagged states, work that survives a refresh or a reopened file, an on-screen warning when the browser cannot keep it, timed breaks between papers, a locked paper with an answer file when the last paper ends, and a fresh attempt on request all come from one offline runtime every paper copies. The paper states the examination's sourced rules, including navigation, permitted materials, negative marking, and access arrangements, and labels the runtime's features as practice features, never examination rules.

### Removed

- Support for artifacts, receipts, and state written under earlier internal versions. Reseal or regenerate them with the current skills.

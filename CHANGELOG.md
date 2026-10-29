# Changelog

All notable changes to First Four Hours are recorded in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). [Release Metadata](REPO_VERSIONING.md#release-metadata) says when to add an entry and how a release is prepared.

## [Unreleased]

### Changed

- Reason 1.0.1: a failed tool, probe, identity check, or seal the work relies on now triggers the after-failure checkpoint. On a non-trivial decision, a checkpoint must state the strongest opposing argument and test each blind spot and load-bearing assumption it exposes; an untested "no material concern" no longer counts as a consultation. The visible result line names the risk tested, and the checkpoint trace counts a checkpoint as consulted only then and lists each further checkpoint an owner skill names.
- Diagnose 1.0.1: consults Reason after any failure or direction change, not only after a failed direction. Its diagnosis contract version is now 1.0.1; Blueprint and Construct still accept every 1.x diagnosis.
- Blueprint 1.0.3: the planner now consults Reason before committing to an approach, after a failure such as a failed probe or blocked seal, or a direction change, before the fresh challenge, and before sealing, and its seal and stop reports trace those checkpoints. The pre-challenge checkpoint attacks the draft's most load-bearing premise and its verification to catch defects before the challenger does. This reverses the 2026-10-11 decision that Blueprint needs no Reason consultations.
- Construct 1.0.3: ships the Blueprint 1.0.3 runtime copy, so it reports contract version 1.0.3. It still accepts every sealed 1.x plan.

### Fixed

- Blueprint 1.0.1: plans no longer author verification that writes inside the worktree. Every Run and Proof run must leave the worktree untouched, ignored files and tool caches included, and must take one of three verification shapes. The challenger checks this against Construct's execution contract, so Construct no longer stops a sealed plan because its own verification wrote a file.
- Construct 1.0.1: ships the Blueprint 1.0.1 runtime copy, so it reports contract version 1.0.1. It still accepts every sealed 1.x plan.
- Architect 1.0.1: in a Git worktree with no commits, the architecture snapshot now covers only tracked and non-ignored untracked files (plus the contents of nested repositories and submodules), so dependency installs, tool caches, and build output that Git ignores no longer stale a sealed handoff, and checks no longer walk them. A handoff sealed by Architect 1.0.0 in such a worktree that no longer matches is refused with a message to reseal it with Architect.
- Blueprint 1.0.2: ships the Architect 1.0.1 handoff verifier, so a no-HEAD architecture handoff stays current across Git-ignored output.
- Construct 1.0.2: ships the Blueprint 1.0.2 runtime copy, so it reports contract version 1.0.2. It still accepts every sealed 1.x plan.

## [1.0.0] - 2026-10-25

The first public release of First Four Hours: 15 skills for coding agents. Each skill helps an agent do one job properly before it moves on: find the real cause, settle the plan, carry the plan out faithfully, or check the result that matters. The skills need Python 3.11 or later and a coding agent that loads skills; Scribe and Ticket also need extra Python packages, and the plugin routes need Git. The README describes each skill and the documentation covers installation and first use. Distributed under the MIT License.

### Added

- Workbench skills, for working on a project and its changes: Architect, Assess, Atlas, Blueprint, Charter, Construct, Diagnose, PR, and Ticket.
- Sensemaking skills, for getting ready to decide: Ideate, Reason, Router, and Scribe.
- Learning skills, for building your own knowledge and ability in any subject: Examiner and Tutor.
- Installation with the Skills CLI, which needs Node.js for `npx`: `npx skills add akshay-diwadkar/first-four-hours --skill '*'` installs the whole suite, and `--skill <name>` installs one skill.
- Installation as the `first-four-hours` Claude Code plugin on Claude Code 2.1.275 or later: `/plugin install first-four-hours --marketplace akshay-diwadkar/first-four-hours`. Plugin skills start as `/first-four-hours:<skill>`, for example `/first-four-hours:diagnose`.
- Installation as the `first-four-hours` Cursor plugin, by cloning the repository into `~/.cursor/plugins/local/first-four-hours`, or, on a Teams or Enterprise plan, by importing the repository as a team marketplace.
- Versioned formats. Every skill starts at 1.0.0, and a skill's version is also the version of every artifact, handoff, receipt, bundle, and state format it owns. A consumer accepts another minor or patch version of the same major and refuses any other version.

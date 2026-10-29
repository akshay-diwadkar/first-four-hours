# Changelog

All notable changes to First Four Hours are recorded in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). [Release Metadata](REPO_VERSIONING.md#release-metadata) says when to add an entry and how a release is prepared.

## [Unreleased]

### Added

- Tutor 1.1.0: asks whether you want a quick explanation, a self-contained HTML page, or a course (one lesson per session or all at once) when your request doesn't say, and offers open material choices with a recommendation instead of deciding silently. Saved material is HTML unless you ask for Markdown, and a new `check-links` command checks it for broken links, missing anchors, and network-loaded assets before delivery. Visuals can now be step-through simulations for multi-stage processes.
- Examiner 1.1.0: offers open paper choices with a recommendation, saves HTML unless you ask for Markdown, and checks every saved set with the same `check-links` command before delivery.

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

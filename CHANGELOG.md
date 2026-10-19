# Changelog

All notable changes to First Four Hours are recorded in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). [Release Metadata](REPO_VERSIONING.md#release-metadata) says when to add an entry and how a release is prepared.

## [Unreleased]

First Four Hours starts its version history at 1.0.0. Earlier release history stays in the `akshay-diwadkar/skills` repository.

### Added

- Claude Code plugin installation. On Claude Code 2.1.275 or later, install all 14 skills as the `first-four-hours` plugin with `/plugin install first-four-hours --marketplace akshay-diwadkar/first-four-hours`. Plugin skills start as `/first-four-hours:<skill>`, for example `/first-four-hours:diagnose`.

### Changed

- The Claude Code marketplace and its single plugin are named `first-four-hours`, giving install id `first-four-hours@first-four-hours`. Users of the retired marketplace or the three preview plugins should follow [Replace an earlier plugin installation](docs/getting-started/installation.md#replace-an-earlier-plugin-installation) to remove the old entries before installing the single plugin.
- The repository, every skill, and every contract version the repository owns are now 1.0.0. A skill's version is also the version of every artifact, handoff, receipt, bundle, and state format it owns.
- A consumer accepts another minor or patch version of the same major and refuses any other version.

### Removed

- Support for artifacts, receipts, and state written under earlier internal versions. Reseal or regenerate them with the current skills.

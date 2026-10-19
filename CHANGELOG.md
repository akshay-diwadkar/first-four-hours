# Changelog

All notable changes to First Four Hours are recorded in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). [Release Metadata](REPO_VERSIONING.md#release-metadata) says when to add an entry and how a release is prepared.

## [Unreleased]

First Four Hours starts its version history at 1.0.0. Earlier release history stays in the `akshay-diwadkar/skills` repository.

### Added

- Claude Code plugin installation. On Claude Code 2.1.275 or later, install the suite as three plugins, `workbench-skills`, `sensemaking-skills`, and `learning-skills`, with `/plugin install <plugin> --marketplace akshay-diwadkar/first-four-hours`. Plugin skills start as `/<plugin>:<skill>`, for example `/workbench-skills:diagnose`.

### Changed

- The Claude Code plugin marketplace is now named `first-four-hours`, so plugin ids are `workbench-skills@first-four-hours`, `sensemaking-skills@first-four-hours`, and `learning-skills@first-four-hours`. If you added the earlier `akshay-diwadkar-skills` marketplace, remove it with `/plugin marketplace remove akshay-diwadkar-skills`, then install again as in the installation guide.
- The repository, every skill, and every contract version the repository owns are now 1.0.0. A skill's version is also the version of every artifact, handoff, receipt, bundle, and state format it owns.
- A consumer accepts another minor or patch version of the same major and refuses any other version.

### Removed

- Support for artifacts, receipts, and state written under earlier internal versions. Reseal or regenerate them with the current skills.

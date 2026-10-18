# Contributing

This guide is where a contribution starts. Each linked document owns its rules; this guide only points to them.

## Set up

Use Python 3.11 or later. From the repository root, install the validation environment:

```bash
python -m pip install -r tools/validation/release-requirements.txt
```

Each skill under `skills/<domain>/<skill>/` installs on its own. A skill that needs packages lists them in its own `requirements.txt`.

## Find your way

- [README.md](README.md) describes the skills and how to install them.
- [docs/README.md](docs/README.md) is the user documentation; [docs/contributing/documentation.md](docs/contributing/documentation.md) holds the rules for changing it.
- [MAP.md](MAP.md) points to the files that matter for a task. The files themselves are the authority.
- [AGENTS.md](AGENTS.md) holds the working rules for coding agents; `CLAUDE.md` carries the same rules for Claude Code.

## Make a change

1. Before you create or change a skill, apply the Change Gate in [SKILL_PHILOSOPHY.md](SKILL_PHILOSOPHY.md).
2. Before you change skills, packaging, validators, dependencies, tests, or release configuration, read [REPO_VERSIONING.md](REPO_VERSIONING.md). It owns branches, versions, tests, and verification.
3. Work on a dedicated branch and open a pull request.
4. If the change is user-visible, add an entry under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md), as [Release Metadata](REPO_VERSIONING.md#release-metadata) describes.

## Verify

Run the required validation from the repository root, naming the base your work is measured against:

```bash
python tools/validation/test_ownership.py run --base-ref <base> --format json
```

Incomplete verification never counts as a pass. [Validation](REPO_VERSIONING.md#validation) and [Adding or changing tests](REPO_VERSIONING.md#adding-or-changing-tests) explain what to run and when a test is earned.

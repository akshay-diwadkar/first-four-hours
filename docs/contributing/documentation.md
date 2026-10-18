# Writing the documentation

This page sets how `docs/` is organized and the rules for adding or changing a page.

## Sections

Each section serves one reader job. A section exists only once it holds a page with real content: do not add empty folders or placeholder pages.

| Section | Reader job |
| :--- | :--- |
| `getting-started/` | Install the suite and get a first useful result. |
| `concepts/` | Understand why the suite exists and how its parts relate. |
| `skills/` | Learn what one skill is for, how to use it, what to expect, and how it composes with others. |
| `recipes/` | Solve a real, recurring workflow problem with one or more skills. |
| `reference/` | Look up exact facts: commands, files, artifacts, and settings. |
| `troubleshooting/` | Recover when a skill stops, refuses, or produces something unexpected. |
| `contributing/` | Change the suite or this documentation. |

[The documentation entrypoint](../README.md) is the single way in. Link every new page from it, or from a page it already links.

## Facts come from source

Take names, commands, artifacts, file paths, invocation modes, and behavior from the current source, not from memory or old issues. Link to the source that owns a fact instead of copying it:

- a skill's `SKILL.md` and `references/` own its behavior;
- [the skill design philosophy](../../SKILL_PHILOSOPHY.md) owns the design doctrine;
- [the versioning and validation policy](../../REPO_VERSIONING.md) owns versions, tests, and validation;
- the skill folders under `skills/<domain>/<skill>/` own the list of skills and their domains. Repository validation fails when the [repository README](../../README.md) catalog or the [skill index](../skills/README.md) is missing a skill, when a skill has no page in `skills/`, or when a page in `skills/` has no skill. The skill facts table in [the reference](../reference/README.md) is generated: change its sources and run `python tools/validation/sync_skill_catalog.py --write` instead of editing it. Do not keep another list of all skills or their domains in these pages;
- the skill scripts own the handoff folders under `.first-four-hours/`. Repository validation fails when a page names a folder no skill script declares, when [How skills hand work to each other](../concepts/handoffs.md) is missing a declared folder, when a page names a `skills/<domain>/<skill>` path that is not an active skill, or when a local link in these pages or the repository README does not resolve.

Do not copy whole contracts, reasoning protocols, schemas, branch rules, or test-runner internals into these pages. Do not document retired skills, old names, or removed behavior; Git history keeps them.

## Validation and testing

Explain repository validation and testing only in `contributing/`, `reference/`, or `troubleshooting/`, and link to [the versioning and validation policy](../../REPO_VERSIONING.md) instead of restating its limits. Skill, recipe, and getting-started pages link there when they need to mention it.

## Conventions

- **Titles:** one H1 per page that names its subject in plain words.
- **Cross-links:** relative links to files in this repository. Link to a file rather than to a heading in another file when that heading may change.
- **Examples:** show what a user would actually type or see. Say when an example is illustrative rather than a recorded run.
- **Command blocks:** fenced, tagged `bash` for shell commands and `text` for requests to an agent, and runnable from the repository root unless the page says otherwise.
- **Claims:** no measured time savings, model rankings, certification, or promise of success without linked independent evidence.

## Voice

Brand voice fades with depth. Pages in `getting-started/`, `concepts/`, and `recipes/` are plain, direct, and start from the reader's problem; "sharpen the axe first" is the promise they make to users. Pages in `skills/` are practical: what to do and what to expect. Pages in `reference/`, `troubleshooting/`, and `contributing/` are dry and precise.

"Raise the floor, preserve the ceiling" is the design doctrine. Use it where a page explains how skills are designed, not as a slogan.

# First Four Hours documentation

These pages are for people who use First Four Hours. The skills themselves are instructions for coding agents; this documentation explains what they are for and how they fit together.

## Get started

- [Start here](../START_HERE.md): the plain-language way in for someone new to AI coding agents: what the suite is, what you need, and a first request.
- [Install First Four Hours](getting-started/installation.md): what you need, how to install the whole suite or one skill, and how to check that it worked.
- [Your first run](getting-started/first-run.md): start one skill on a real problem, see what it leaves behind, and learn how skills start.
- [Choose a skill](getting-started/choosing-a-skill.md): find the smallest skill for the problem in front of you, and when to combine skills.

## Understand the suite

- [Why First Four Hours exists](concepts/why-first-four-hours.md): the problem the suite addresses, and what it does not promise.
- [How the suite works](concepts/how-the-suite-works.md): what a skill is, how to pick the smallest one that helps, how skills hand work to each other, and how the suite is organized.
- [Anatomy of a sealed blueprint](concepts/anatomy-of-a-blueprint.md): one illustrative plan, section by section, and why each part is there.

## Skills

- [Skills](skills/README.md): one page per skill, grouped by domain: what it is for, how to start it, what it produces, and where it stops.
- [How skills hand work to each other](concepts/handoffs.md): the real handoffs between skills, where they are stored, and who starts the next step.

## Solve a recurring problem

- [Recipes](recipes/README.md): start from a problem you keep losing time to, such as a fix that only patches the symptom or a plan reopened halfway through editing, and see which skills deal with it.

## Look something up

- [Reference](reference/README.md): exact facts about each skill, such as its domain, source folder, how it starts, and the Python it needs, and where every other fact is kept.

## Fix a problem

- [Troubleshooting](troubleshooting/README.md): find the symptom you see, its likely cause, a check that changes nothing, and the next step.

## Contribute

- [Contributor guide](contributing/README.md): change the suite, validate the affected behavior, and maintain packages, releases, and documentation.

## Other sources

- The [repository README](../README.md) lists every skill by domain and shows how to install them.
- Each skill's `SKILL.md`, under `skills/<domain>/<skill>/`, is the contract its agent follows.
- [Writing the documentation](contributing/documentation.md) explains how these pages are organized and the rules for changing them.

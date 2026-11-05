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

Zensical builds these pages into the documentation site, published on GitHub Pages at [akshay-diwadkar.github.io/first-four-hours](https://akshay-diwadkar.github.io/first-four-hours/). [The site configuration](https://github.com/akshay-diwadkar/first-four-hours/blob/main/zensical.toml) reads pages from `docs/`, with [the entrypoint](../README.md) as the home page, and its `nav` list is the site's navigation: each section lists its pages in order, and a folder's `README.md` listed first is that section's landing page. Pages `nav` does not list do not appear in the navigation, so add every new page there too; repository validation fails when a page is missing from `nav` or when `nav` lists a page that does not exist. The site cannot follow a relative link out of `docs/`, so link other pages here relatively and any other repository file by its GitHub URL on `main`, such as `https://github.com/akshay-diwadkar/first-four-hours/blob/main/REPO_VERSIONING.md`; repository validation rejects a relative link that leaves `docs/` and a GitHub URL on `main` whose file does not exist.

[The docs workflow](https://github.com/akshay-diwadkar/first-four-hours/blob/main/.github/workflows/docs.yml) builds the site for every pull request and every push to `main`, and deploys it to GitHub Pages only from `main`. The repository's Pages source must be set to GitHub Actions.

## Facts come from source

Take names, commands, artifacts, file paths, invocation modes, and behavior from the current source, not from memory or old issues. Link to the source that owns a fact instead of copying it:

- a skill's `SKILL.md` and `references/` own its behavior;
- [the skill design philosophy](https://github.com/akshay-diwadkar/first-four-hours/blob/main/SKILL_PHILOSOPHY.md) owns the design doctrine;
- [the versioning and validation policy](https://github.com/akshay-diwadkar/first-four-hours/blob/main/REPO_VERSIONING.md) owns versions, tests, and validation;
- the skill folders under `skills/<domain>/<skill>/` own the list of skills and their domains. Repository validation fails when the [repository README](https://github.com/akshay-diwadkar/first-four-hours/blob/main/README.md) catalog or the [skill index](../skills/README.md) is missing a skill, when a skill has no page in `skills/`, or when a page in `skills/` has no skill. The skill facts table in [the reference](../reference/README.md) is generated: change its sources and run `python tools/validation/sync_skill_catalog.py --write` instead of editing it. Do not keep another list of all skills or their domains in these pages;
- the skill scripts own the handoff folders under `.first-four-hours/`. Repository validation fails when a page names a folder no skill script declares, when [How skills hand work to each other](../concepts/handoffs.md) is missing a declared folder, when a page names a `skills/<domain>/<skill>` path that is not an active skill, or when a local link in these pages or the repository README does not resolve.

Do not copy whole contracts, reasoning protocols, schemas, branch rules, or test-runner internals into these pages. Do not document retired skills, old names, or removed behavior; Git history keeps them.

## Validation and testing

Explain repository validation and testing only in `contributing/`, `reference/`, or `troubleshooting/`, and link to [the versioning and validation policy](https://github.com/akshay-diwadkar/first-four-hours/blob/main/REPO_VERSIONING.md) instead of restating its limits. Skill, recipe, and getting-started pages link there when they need to mention it.

## Conventions

- **Titles:** one H1 per page that names its subject in plain words.
- **Cross-links:** relative links to other pages in `docs/`, and GitHub URLs on `main` for every other file in this repository, because the documentation site cannot follow a relative link out of `docs/`. Link to a file rather than to a heading in another file when that heading may change.
- **Examples:** show what a user would actually type or see. Say when an example is illustrative rather than a recorded run.
- **Prompt examples:** give the reader a problem worth having: a specific clue, real stakes, or a hard constraint the skill is built for. Keep them true to what the skill does, never imply a result, and leave handoff prompts that only name an artifact plain.
- **Command blocks:** fenced, tagged `bash` for shell commands and `text` for requests to an agent, and runnable from the repository root unless the page says otherwise. Code blocks do not wrap on GitHub or the docs site, so wrap lines in `text` and `markdown` blocks at 76 characters and give each prompt its own block so it copies on its own; keep each shell command on one line so it runs when copied. Repository validation rejects lines over 80 characters in those blocks.
- **Claims:** no measured time savings, model rankings, certification, or promise of success without linked independent evidence.
- **Why sections:** each page in `skills/` has a `## Why it's built this way` section immediately before `## Related skills`, with three parts: the failure the skill prevents, what it refuses and why, and its floor and ceiling. Take the reasons from the owner's stated intent for the skill, recorded in [issue #3](https://github.com/akshay-diwadkar/first-four-hours/issues/3) for every skill except PR, whose reason the owner stated directly, and from the skill's current `SKILL.md`. Apply the shared principle to the skill in concrete terms; the skill index links [the skill design philosophy](https://github.com/akshay-diwadkar/first-four-hours/blob/main/SKILL_PHILOSOPHY.md), so a section never restates the principle itself. Each part may open with a concrete moment or a short argument before its reasons, so the section reads as a point of view rather than a list of requirements.
- **Worked scenarios:** each recipe has a `## A worked scenario` section after `## Steps`. Coding recipes follow FreshCart, one made-up online grocery service, so readers watch one codebase move between skills; keep FreshCart's names consistent with the other recipes. Label every scenario as illustrative, never present it as a recorded run, and keep artifact excerpts true to the real artifact's shape. Excerpts contain no Markdown links, because repository validation checks every link in these pages, including inside code blocks. A scenario's prose names who is hurting and why, the tempting shortcut, and what that shortcut would have cost.
- **Cast:** people in scenarios and examples come from many parts of the world, so every reader can find themselves in the story; no single region supplies more than one recurring name. FreshCart's recurring cast is below. Introduce each person by role the first time they appear on a page, and add to the table rather than inventing a one-off name.

    | Role | Name |
    | :--- | :--- |
    | Support lead | Amara Okafor |
    | Checkout engineer | Mateo Rojas |
    | Reviewer | Yuki Tanaka |
    | On-call and platform engineer | Søren Lindqvist |
    | Product owner | Priya Raman |
    | Learner, outside FreshCart | Leila Haddad |

## Voice

Brand voice fades with depth, but it does not vanish.

- **Grounded story.** Pages in `getting-started/` and `concepts/`, recipe introductions and scenarios, and each skill's `## Why it's built this way` section start from a person and what is at stake for them: the 3 a.m. page, the Friday release, the review that will happen without the context. Use concrete detail from engineering life and short sentences. Use aphorisms sparingly: a line earns its place only when it carries an argument the page goes on to make. "Sharpen the axe first" is the promise these pages make to users.
- **Plain and practical.** The rest of each recipe is plain and direct and starts from the reader's problem. The rest of each page in `skills/` says what to do and what to expect.
- **Dry and precise.** Pages in `reference/`, `troubleshooting/`, and `contributing/`.

Story has limits, because it is the easiest place for a claim to slip in:

- Dramatise the failure, not the cure. A scene may show what goes wrong without a skill; it never shows a skill guaranteeing an outcome it cannot.
- Feeling belongs to people in the story, never to a skill or an agent.
- Invent no metrics, and keep every fact in a story true to the source it comes from.
- Code blocks, artifact excerpts, and commands stay exact; the voice lives in the prose around them.

"Raise the floor, preserve the ceiling" is the design doctrine. Use it where a page explains how skills are designed, not as a slogan.

<p align="center"><img alt="First Four Hours — Skills for AI agents. Sharpen the axe first." src="assets/first-four-hours-banner.png"></p>

<h1 align="center">First Four Hours</h1>

<p align="center"><b>Sharpen the axe before your agent swings.</b></p>

<p align="center">
  <a href="https://github.com/akshay-diwadkar/first-four-hours/releases/latest"><img alt="Latest Release" src="https://img.shields.io/github/v/release/akshay-diwadkar/first-four-hours?sort=semver&display_name=tag&cacheSeconds=300"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-blue.svg"></a>
  <a href="pyproject.toml"><img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11+-blue.svg"></a>
  <a href="https://first-four-hours.pages.dev/"><img alt="Docs" src="https://img.shields.io/badge/docs-online-brightgreen.svg"></a>
  <a href="https://first-four-hours.pages.dev/recipes/"><img alt="Recipes for common failures" src="https://img.shields.io/badge/recipes-common%20failures-orange.svg"></a>
  <a href="docs/getting-started/installation.md"><img alt="Works with Claude Code, Codex, GitHub Copilot, Cursor" src="https://img.shields.io/badge/works%20with-Claude%20Code%20%C2%B7%20Codex%20%C2%B7%20Copilot%20%C2%B7%20Cursor-8A63D2.svg"></a>
</p>

<p align="center"><a href="#install">Install</a> · <a href="#your-first-run">Your first run</a> · <a href="#the-skills">Skills</a> · <a href="https://first-four-hours.pages.dev/">Docs</a> · <a href="https://first-four-hours.pages.dev/recipes/">Recipes</a> · <a href="CHANGELOG.md">Changelog</a></p>

> *"Give me six hours to chop down a tree, and I will spend the first four sharpening the axe."*

Your agent said **done**. Then came the missed requirement, the decision it quietly reopened, the caller it broke.

First Four Hours does the sharpening first: each skill does one job before the work moves on, and leaves a file you can open and check. On a small fix, that takes minutes.

## Install

You need Node.js for `npx` and Python 3.11 or later. From your project's root folder:

```bash
npx skills add akshay-diwadkar/first-four-hours --skill '*'
```

Then type `/provision` in your agent. It installs any Python packages the installed skills declare and sets up the suite's subagents on the models you choose.

<details>
<summary>Claude Code plugin, Cursor, or one skill only</summary>

On Claude Code 2.1.275 or later, install the suite as a plugin from a Claude Code session:

```text
/plugin install first-four-hours --marketplace akshay-diwadkar/first-four-hours
```

For Cursor, see [Install as a Cursor plugin](docs/getting-started/installation.md#install-as-a-cursor-plugin). [Install First Four Hours](docs/getting-started/installation.md) covers installing one skill, choosing the agent, installing for every project, and checking that the install worked.

</details>

## Your first run

Name a skill and say what is at stake. For example (illustrative; FreshCart is a made-up online grocery service):

```text
/blueprint : Add per-client rate limiting to the FreshCart public API before the holiday sale. Partner integrations must never be throttled, every response under the limit must stay exactly as it is today, and a cheaper model will build this overnight with nobody watching.
```

`/blueprint` reads the project without editing it and seals `blueprint.md`. Its Goal, shortened, is what you read and approve before anything is edited:

```markdown
## Goal

Approach: add a per-client token bucket to the existing middleware chain, keyed on the API key when one is present and on the client address otherwise. Partner keys bypass the limit. A limited request gets 429 with a Retry-After header; every other response is unchanged.

Load-bearing invariants: responses under the limit are exactly what they are today; partner keys are never limited; the client address comes only from the app's trusted proxy helper.

Main risk: /search/suggest shares the search handler, so it is limited too.
```

Below it, the plan cites the files its facts come from, gives ordered instructions, and names the check for each outcome. `/construct` then carries the plan out; if the plan turns out wrong against the real code, `/construct` stops and reports instead of deciding on its own. [Anatomy of a sealed blueprint](docs/concepts/anatomy-of-a-blueprint.md) walks through a whole plan.

## Built with itself

This repository is planned, built, and reviewed with its own skills, and its pull requests keep the record:

- **[Epic #27](https://github.com/akshay-diwadkar/first-four-hours/issues/27): research to shipped features.** One `/ideate` run researched how real examinations and good tutors work; `/ticket` split it into four issues, closed by four pull requests.
- **[#203](https://github.com/akshay-diwadkar/first-four-hours/pull/203) and [#205](https://github.com/akshay-diwadkar/first-four-hours/pull/205): the diagnosis that led to better plans.** `/diagnose` read real session logs and found why `/blueprint`'s plans cost so much: it explored the code one read per turn, and every turn re-read the whole conversation. An experiment then showed that asking for fewer calls made plans worse, while asking for fewer turns without gathering less took 33 turns instead of 72 and wrote the best plan. `/blueprint` planned that rule, `/construct` built it, and `/assess` cleared both pull requests.
- **[#162](https://github.com/akshay-diwadkar/first-four-hours/pull/162): the skill that halved itself.** `/blueprint` planned the cut to its own guidance, from 12,854 tokens to 6,420, and a hard limit now stops it growing back. `/assess` then caught two rules the cut had removed by accident, and a second sealed plan dealt with them.

## Start from the problem

| You are dealing with | Start with |
| :--- | :--- |
| Something is wrong and you do not know why | `/diagnose` |
| A change whose mistakes would show up late, or that someone else will carry out | `/blueprint`, then `/construct` |
| A finished change you need to trust before merging | `/assess` |
| A decision that is stuck, or rests on an assumption you doubt | `/reason` |
| A slow or costly test suite | `/temper` |
| Not knowing which skill comes next | `/router` |

Each skill works alone and hands work on through a file; you decide when the next one starts. [Choose a skill](docs/getting-started/choosing-a-skill.md) and the [recipes](docs/recipes/README.md) cover more situations.

## When not to use it

- A small, clear task may need no skill at all.
- If the same agent will carry out the plan in the same session while you watch, and mistakes surface within minutes, your agent's plan mode is enough. [`/blueprint`](docs/skills/blueprint.md) explains when.
- No skill replaces your review. You own the decisions, commits, and merges, and the suite makes no measured claim about time saved. [Why First Four Hours exists](docs/concepts/why-first-four-hours.md) says what it does and does not promise.

## The skills

Sixteen skills in three domains. Each name links to its page; each contract is the `SKILL.md` the agent follows.

<details>
<summary><b>Workbench</b>: working on a project and its changes</summary>

### Workbench

- [`/architect`](docs/skills/architect.md): decide a structural question, such as a boundary, dependency direction, or module structure, before planning. [Contract](skills/workbench/architect/SKILL.md)
- [`/assess`](docs/skills/assess.md): review one exact change against its requirements and base behavior before you trust it. [Contract](skills/workbench/assess/SKILL.md)
- [`/blueprint`](docs/skills/blueprint.md): plan a repository change so completely that a weaker agent can carry it out. [Contract](skills/workbench/blueprint/SKILL.md)
- [`/charter`](docs/skills/charter.md): give a rough idea for a whole project its agreed purpose, scope, and success before anyone splits it into tickets. [Contract](skills/workbench/charter/SKILL.md)
- [`/construct`](docs/skills/construct.md): carry out a sealed `/blueprint` plan and verify the result. [Contract](skills/workbench/construct/SKILL.md)
- [`/diagnose`](docs/skills/diagnose.md): find the evidence-backed cause of a defect, risk, or improvement opportunity before anyone decides a fix. [Contract](skills/workbench/diagnose/SKILL.md)
- [`/pr`](docs/skills/pr.md): write a reviewer-oriented pull request description and open the pull request, or update its description, once you confirm it. [Contract](skills/workbench/pr/SKILL.md)
- [`/provision`](docs/skills/provision.md): install the suite's Python requirements and set up its subagents on the models you choose. [Contract](skills/workbench/provision/SKILL.md)
- [`/temper`](docs/skills/temper.md): audit a test suite to cut its run cost while keeping or raising the faults it catches. [Contract](skills/workbench/temper/SKILL.md)
- [`/ticket`](docs/skills/ticket.md): split large work into session-sized tickets, or pick the next ready ticket and prepare it for planning. [Contract](skills/workbench/ticket/SKILL.md)

</details>

<details>
<summary><b>Sensemaking</b>: getting ready to decide</summary>

### Sensemaking

- [`/ideate`](docs/skills/ideate.md): research and compare options for a goal and recommend a direction you choose from. [Contract](skills/sensemaking/ideate/SKILL.md)
- [`/reason`](docs/skills/reason.md): check a judgment at the moments it matters, or ask what only you can answer. [Contract](skills/sensemaking/reason/SKILL.md)
- [`/router`](docs/skills/router.md): lay out which skills to use, in what order, as far as that can be known now. [Contract](skills/sensemaking/router/SKILL.md)
- [`/scribe`](docs/skills/scribe.md): write or audit technical documentation that carries its sources faithfully. [Contract](skills/sensemaking/scribe/SKILL.md)

</details>

<details>
<summary><b>Learning</b>: building your own knowledge in any subject</summary>

### Learning

- [`/examiner`](docs/skills/examiner.md): write practice papers for a specific written examination and mark attempts. [Contract](skills/learning/examiner/SKILL.md)
- [`/tutor`](docs/skills/tutor.md): learn any subject through an explanation, interactive tutoring, or a continuing series. [Contract](skills/learning/tutor/SKILL.md)

</details>

## More

- **[Documentation](https://first-four-hours.pages.dev/)**: getting started, how the suite works, one page per skill, recipes, [reference](docs/reference/README.md), and [troubleshooting](docs/troubleshooting/README.md).
- **Contributing**: start with [`CONTRIBUTING.md`](CONTRIBUTING.md). Skills raise the floor and preserve the ceiling, as [`SKILL_PHILOSOPHY.md`](SKILL_PHILOSOPHY.md) explains; [`REPO_VERSIONING.md`](REPO_VERSIONING.md) owns versions and tests.
- **License**: [MIT](LICENSE).

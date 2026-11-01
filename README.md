<img alt="First Four Hours — Skills for AI agents. Sharpen the axe first." src="assets/first-four-hours-banner.png">

# First Four Hours

[![Latest Release](https://img.shields.io/github/v/release/akshay-diwadkar/first-four-hours?sort=semver&display_name=tag&cacheSeconds=300)](https://github.com/akshay-diwadkar/first-four-hours/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](pyproject.toml)

**Sharpen the axe first.**

> "Give me six hours to chop down a tree, and I will spend the first four sharpening the axe."

Coding agents are supposed to save time. You ask for a change; the agent writes the code, runs the tests, and says it is done. Then you find the missed requirement, the decision it quietly reopened, the caller the fix broke. You explain the context again and review another patch. Those are the lost hours: the time spent turning work that looks finished into work you can trust.

First Four Hours is a suite of skills for coding agents. Each skill helps an agent do one job properly before it moves on: find the real cause, settle the plan, carry the plan out faithfully, or check the result that matters. Use one skill for one job, and combine skills only when the work needs it. Small tasks stay light.

It does not make every task faster, and it makes no measured claim about time saved. [Why First Four Hours exists](docs/concepts/why-first-four-hours.md) explains what it aims for and what it does not promise.

## Install

You need Node.js for `npx`, Python 3.11 or later, and a coding agent that loads skills. From your project's root folder, install the whole suite:

```bash
npx skills add akshay-diwadkar/first-four-hours --skill '*'
```

On Claude Code 2.1.275 or later, you can instead install the whole suite as the `first-four-hours` plugin. Run this in a Claude Code session:

```text
/plugin install first-four-hours --marketplace akshay-diwadkar/first-four-hours
```

In Cursor, you can install the same suite as a plugin; [Install as a Cursor plugin](docs/getting-started/installation.md#install-as-a-cursor-plugin) shows how.

[Install First Four Hours](docs/getting-started/installation.md) covers installing one skill, choosing the agent, installing for every project, the plugin skill names, and checking that the install worked.

## First use

Start a skill on a real problem by naming it in your agent's chat. For example (illustrative):

```text
/diagnose : Find out why authentication tokens expire early under high concurrency.
```

[Your first run](docs/getting-started/first-run.md) shows what a skill leaves behind and how each skill starts.

## Start from the problem

| You are dealing with | Start with |
| :--- | :--- |
| Something is wrong and you do not know why | `diagnose` |
| A change another session, agent, or cheaper model will carry out, whose mistakes would show up late, or whose decisions must outlast the session | `blueprint`, then `construct` to carry out the plan |
| A finished change you need to trust before merging | `assess` |
| A decision that is stuck, or rests on an assumption you doubt | `reason` |
| Not knowing which skill comes next | `router` (ask in plain words) |
| A subject to learn, or a written examination to practise for | `tutor` or `examiner` |

[Choose a skill](docs/getting-started/choosing-a-skill.md) covers more situations.

## The skills

Every skill belongs to one of three domains. The domains only group the list: choose a skill by the task in front of you. Each name links to the skill's page; each contract link opens the `SKILL.md` its agent follows.

### Workbench

Working on a project and its changes.

- [Architect](docs/skills/architect.md): decide a structural question, such as a boundary, dependency direction, or module structure, before planning. [Contract](skills/workbench/architect/SKILL.md)
- [Assess](docs/skills/assess.md): review one exact change against its requirements and base behavior before you trust it. [Contract](skills/workbench/assess/SKILL.md)
- [Blueprint](docs/skills/blueprint.md): plan a repository change so completely that a weaker agent can carry it out. [Contract](skills/workbench/blueprint/SKILL.md)
- [Charter](docs/skills/charter.md): give a rough idea for a whole project its agreed purpose, scope, and success before anyone splits it into tickets. [Contract](skills/workbench/charter/SKILL.md)
- [Construct](docs/skills/construct.md): carry out a sealed Blueprint plan and verify the result. [Contract](skills/workbench/construct/SKILL.md)
- [Diagnose](docs/skills/diagnose.md): find the evidence-backed cause of a defect, risk, or improvement opportunity before anyone decides a fix. [Contract](skills/workbench/diagnose/SKILL.md)
- [PR](docs/skills/pr.md): write a reviewer-oriented pull request description and open the pull request, or update its description, once you confirm it. [Contract](skills/workbench/pr/SKILL.md)
- [Ticket](docs/skills/ticket.md): split large work into session-sized tickets, or pick the next ready ticket and prepare it for planning. [Contract](skills/workbench/ticket/SKILL.md)

### Sensemaking

Getting ready to decide.

- [Ideate](docs/skills/ideate.md): research and compare options for a goal and recommend a direction you choose from. [Contract](skills/sensemaking/ideate/SKILL.md)
- [Reason](docs/skills/reason.md): check a judgment at the moments it matters, or ask the one question only you can answer. [Contract](skills/sensemaking/reason/SKILL.md)
- [Router](docs/skills/router.md): lay out which skills to use, in what order, as far as that can be known now. [Contract](skills/sensemaking/router/SKILL.md)
- [Scribe](docs/skills/scribe.md): write or audit technical documentation that carries its sources faithfully. [Contract](skills/sensemaking/scribe/SKILL.md)

### Learning

Building your own knowledge and ability in any subject.

- [Examiner](docs/skills/examiner.md): write practice papers for a specific written examination and mark attempts. [Contract](skills/learning/examiner/SKILL.md)
- [Tutor](docs/skills/tutor.md): learn any subject through an explanation, interactive tutoring, or a continuing series. [Contract](skills/learning/tutor/SKILL.md)

## Common workflows

- **Fix a bug at its cause.** Diagnose finds the evidence-backed cause, Blueprint plans the fix for one finding, and Construct carries out the plan. See [Fix the bug without patching the symptom](docs/recipes/fix-a-bug.md).
- **Plan before editing.** Blueprint settles every decision and seals a plan, and Construct carries it out without reopening it, possibly with a cheaper model. Reach for it when someone else will carry the change out, a mistake would show up late, or the decisions must outlast the session, not because the change looks big; [Blueprint](docs/skills/blueprint.md) explains when your agent's plan mode is enough. See [Plan a change before your agent starts editing](docs/recipes/plan-a-change.md).
- **Trust a change before merging.** Assess reviews the exact change, and its findings go to a new Blueprint run rather than a direct edit. See [Trust a change before you merge it](docs/recipes/review-before-merge.md).

Each skill works alone. A skill hands work on through a file, and you decide when the next skill starts; see [How skills hand work to each other](docs/concepts/handoffs.md). [Recipes](docs/recipes/README.md) cover more recurring problems.

## Documentation

[The documentation](docs/README.md) is the full manual: getting started, how the suite works, one page per skill, recipes, a [reference](docs/reference/README.md) of exact facts, and [troubleshooting](docs/troubleshooting/README.md) by symptom.

## Contributing

Start with [`CONTRIBUTING.md`](CONTRIBUTING.md) and the [contributor guide](docs/contributing/README.md). Skills are designed to raise the floor and preserve the ceiling, as [`SKILL_PHILOSOPHY.md`](SKILL_PHILOSOPHY.md) explains. [`REPO_VERSIONING.md`](REPO_VERSIONING.md) owns versions, tests, and validation, and [`CHANGELOG.md`](CHANGELOG.md) holds the release history.

## License

Distributed under the [MIT License](LICENSE).

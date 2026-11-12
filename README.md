<img alt="First Four Hours — Skills for AI agents. Sharpen the axe first." src="assets/first-four-hours-banner.png">

# First Four Hours

[![Latest Release](https://img.shields.io/github/v/release/akshay-diwadkar/first-four-hours?sort=semver&display_name=tag&cacheSeconds=300)](https://github.com/akshay-diwadkar/first-four-hours/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](pyproject.toml)

**Sharpen the axe first.**

> "Give me six hours to chop down a tree, and I will spend the first four sharpening the axe."

The four hours are a metaphor, not a schedule. Sharpening takes minutes on a small fix, and more only when a mistake would be costly to find later.

Coding agents are supposed to save time. You ask for a change. The agent writes the code, runs the tests, and says it is done.

Then you find the missed requirement. The decision it quietly reopened. The caller the fix broke. You explain the context again, review another patch, and stop trusting the word "done".

Those are the lost hours: the time spent turning work that looks finished into work you can trust.

First Four Hours is a suite of skills for coding agents. Each skill does one job before the work moves on, and leaves a file you can open and check:

- **Diagnose** finds the cause of a defect and writes `diagnosis.md`: each finding with how well its cause is established, and what evidence is still missing.
- **Blueprint** settles every decision before anyone edits and seals `blueprint.md`, a plan another agent, even a cheaper model, carries out without reopening those decisions.
- **Assess** reviews the exact change and writes `assessment.md`: each finding with its location, the steps that show it going wrong, and its consequence.

Use one skill for one job, and combine skills only when the work needs it. Small tasks stay light.

## What a skill leaves behind

The Goal at the top of a sealed plan, shortened (illustrative; FreshCart is a made-up online grocery service):

```markdown
## Goal

Approach: add a per-client token bucket to the existing middleware chain, keyed on the API key when one is present and on the client address otherwise. Partner keys bypass the limit. A limited request gets 429 with a Retry-After header; every other response is unchanged.

Load-bearing invariants: responses under the limit are exactly what they are today; partner keys are never limited; the client address comes only from the app's trusted proxy helper.

Main risk: /search/suggest shares the search handler, so it is limited too.
```

You read and approve these few lines before anything else. Below them, the plan cites the files its facts come from, gives ordered instructions, and names the check that proves each outcome. [Anatomy of a sealed blueprint](docs/concepts/anatomy-of-a-blueprint.md) walks through the whole plan.

## Built with itself

This repository is planned, built, and reviewed with its own skills, and its pull requests keep the record:

- **Research to a finished epic.** One Ideate run researched how real examinations and good tutors work. It found, for example, that learning styles have no support and that learners in active lessons often learn more while feeling they learned less. Ticket turned it into epic [#27](https://github.com/akshay-diwadkar/first-four-hours/issues/27) with four issues, closed by [#46](https://github.com/akshay-diwadkar/first-four-hours/pull/46), [#50](https://github.com/akshay-diwadkar/first-four-hours/pull/50), [#51](https://github.com/akshay-diwadkar/first-four-hours/pull/51), and [#52](https://github.com/akshay-diwadkar/first-four-hours/pull/52): practice papers that behave like the real examination, marking by its own rules, and teaching methods chosen from that evidence.
- **Structure settled first.** Construct's safety check hashed the whole worktree, ignored folders included, before and after every command, and one verification took 332 seconds while its tests took 42. In [#128](https://github.com/akshay-diwadkar/first-four-hours/pull/128), Architect settled what the check should cover before Blueprint planned it, and Assess's six minor findings went through their own repair plan.
- **A plan that drifted from the request.** Two changes in one epic each needed extra plan, build, and review rounds. Every finding was a gap between what the plan delivered and what the request asked; none was a build or test failure. Since [#88](https://github.com/akshay-diwadkar/first-four-hours/pull/88), Blueprint judges each deliverable against every clause of the request before it seals.

## When not to use it

- A small, clear task may need no skill at all.
- If the same agent will carry out the plan in the same session while you watch, and mistakes surface within minutes, your agent's plan mode is enough. [Blueprint](docs/skills/blueprint.md) explains when.
- No skill replaces your review. You still own the decisions that are yours, and every commit, pull request, and merge.
- It makes no measured claim about time saved, and no claim that one model or agent beats another.

[Why First Four Hours exists](docs/concepts/why-first-four-hours.md) explains what it aims for and what it does not promise.

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

After installing, type `/provision` in your agent. After you confirm, it installs the Python packages some skills need and sets up the suite's subagents on the models you choose. Run it again in each agent harness you use, or when you want fresh model choices. See [Provision](docs/skills/provision.md).

[Install First Four Hours](docs/getting-started/installation.md) covers installing one skill, choosing the agent, installing for every project, the plugin skill names, and checking that the install worked.

## First use

Start a skill on a real problem by naming it in your agent's chat. For example (illustrative):

```text
/diagnose : About one invoice in 4,000 comes out exactly one cent short, only on the first of the month, and re-running the job gives the right total. Nobody has touched billing in a year. Find out why.
```

Diagnose reads your project without editing it, and leaves a sealed `diagnosis.md` in `.first-four-hours/diagnoses/<slug>/`, a folder Git ignores. [Your first run](docs/getting-started/first-run.md) shows what to do with it and how each skill starts.

## Start from the problem

| You are dealing with | Start with |
| :--- | :--- |
| Something is wrong and you do not know why | `diagnose` |
| A change another session, agent, or cheaper model will carry out, whose mistakes would show up late, or whose decisions must outlast the session | `blueprint`, then `construct` to carry out the plan |
| A finished change you need to trust before merging | `assess` |
| A decision that is stuck, or rests on an assumption you doubt | `reason` |
| Not knowing which skill comes next | `router` (ask in plain words) |
| A fresh install to finish, or subagents to set up on the models you choose | `provision` |
| A test suite that is slow, costly in CI, or full of tests that protect little | `temper` |
| A subject to learn, or a written examination to practise for | `tutor` or `examiner` |

[Choose a skill](docs/getting-started/choosing-a-skill.md) covers more situations.

## Common workflows

- **Fix a bug at its cause.** Diagnose finds the evidence-backed cause, Blueprint plans the fix for one finding, and Construct carries out the plan. See [Fix the bug without patching the symptom](docs/recipes/fix-a-bug.md).
- **Plan before editing.** Blueprint settles every decision and seals a plan, and Construct carries it out without reopening it, possibly with a cheaper model. Reach for it when someone else will carry the change out, a mistake would show up late, or the decisions must outlast the session, not because the change looks big; [Blueprint](docs/skills/blueprint.md) explains when your agent's plan mode is enough. See [Plan a change before your agent starts editing](docs/recipes/plan-a-change.md).
- **Trust a change before merging.** Assess reviews the exact change, and its findings go to a new Blueprint run rather than a direct edit. See [Trust a change before you merge it](docs/recipes/review-before-merge.md).

Each skill works alone. A skill hands work on through a file, and you decide when the next skill starts; see [How skills hand work to each other](docs/concepts/handoffs.md). [Recipes](docs/recipes/README.md) cover more recurring problems.

## What you can ask

Say what is actually going wrong, what is at stake, and what must not break. For example (illustrative):

```text
/reason : Everyone on the team agrees this API migration is backwards compatible, and that is what worries me. Challenge the claim before it reaches 300 integrators on Friday.
```

```text
/blueprint : Plan the migration that splits our 40-million-row orders table into monthly partitions without downtime. Checkout keeps writing throughout, last quarter's revenue report must match to the cent, and a cheaper model will build this overnight with nobody watching.
```

```text
/scribe : It is 3 a.m., the on-call engineer has never seen this service, and the one person who knows how to deploy it leaves on Friday. Write a deployment runbook from our docker-compose file and deploy scripts, with nothing in it that does not trace to a source.
```

```text
/tutor : I study history, and I am tired of people citing Gödel to prove things the theorem never said. Teach me the first incompleteness theorem from scratch, make me build the self-referring sentence myself, then show me popular claims about it and have me say which ones are wrong.
```

## The skills

Each skill helps an agent do one job properly, so the next step has something solid to stand on.

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
- [Provision](docs/skills/provision.md): install the suite's Python requirements and set up its subagents on the models you choose. [Contract](skills/workbench/provision/SKILL.md)
- [Temper](docs/skills/temper.md): audit a test suite to cut its run cost while keeping or raising the faults it catches. [Contract](skills/workbench/temper/SKILL.md)
- [Ticket](docs/skills/ticket.md): split large work into session-sized tickets, or pick the next ready ticket and prepare it for planning. [Contract](skills/workbench/ticket/SKILL.md)

### Sensemaking

Getting ready to decide.

- [Ideate](docs/skills/ideate.md): research and compare options for a goal and recommend a direction you choose from. [Contract](skills/sensemaking/ideate/SKILL.md)
- [Reason](docs/skills/reason.md): check a judgment at the moments it matters, or ask what only you can answer. [Contract](skills/sensemaking/reason/SKILL.md)
- [Router](docs/skills/router.md): lay out which skills to use, in what order, as far as that can be known now. [Contract](skills/sensemaking/router/SKILL.md)
- [Scribe](docs/skills/scribe.md): write or audit technical documentation that carries its sources faithfully. [Contract](skills/sensemaking/scribe/SKILL.md)

### Learning

Building your own knowledge and ability in any subject.

- [Examiner](docs/skills/examiner.md): write practice papers for a specific written examination and mark attempts. [Contract](skills/learning/examiner/SKILL.md)
- [Tutor](docs/skills/tutor.md): learn any subject through an explanation, interactive tutoring, or a continuing series. [Contract](skills/learning/tutor/SKILL.md)

## Documentation

[The documentation](docs/README.md) is the full manual: getting started, how the suite works, one page per skill, recipes, a [reference](docs/reference/README.md) of exact facts, and [troubleshooting](docs/troubleshooting/README.md) by symptom. Read it online at [akshay-diwadkar.github.io/first-four-hours](https://akshay-diwadkar.github.io/first-four-hours/).

## Contributing

Start with [`CONTRIBUTING.md`](CONTRIBUTING.md) and the [contributor guide](docs/contributing/README.md). Skills are designed to raise the floor and preserve the ceiling, as [`SKILL_PHILOSOPHY.md`](SKILL_PHILOSOPHY.md) explains. [`REPO_VERSIONING.md`](REPO_VERSIONING.md) owns versions, tests, and validation, and [`CHANGELOG.md`](CHANGELOG.md) holds the release history.

## License

Distributed under the [MIT License](LICENSE).

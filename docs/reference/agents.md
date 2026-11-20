# First Four Hours subagents

[`/provision`](../skills/provision.md) writes up to seven subagents into your harness. Several skills hand them delegated work by name. The name, description, permissions, and instructions of each subagent are fixed by [Provision's agent definitions](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/provision/references/agents.md); only the model and effort are yours. Every subagent may read and search files.

## What each subagent does

| Subagent | Job | Access beyond reading | Used by | When it is missing |
| :--- | :--- | :--- | :--- | :--- |
| `ffh-challenger` | Attacks a plan, proposal, or result in fresh context and reports every material gap. | A shell, for safe probes only. | `/blueprint`, for the one fresh challenge a risky plan gets; `/ideate`, for a Deep ideation's fresh challenge; `/assess`, for its clear challenge; `/reason`, for its challenger. | A generic subagent. `/blueprint` uses one at least as capable as the planner and stops unsealed if none launches. |
| `ffh-reviewer` | Reviews a change against its requirements and reports material defects with evidence. | A shell, for running tests and checks only. | `/assess`, for its falsification slices. | A generic subagent. |
| `ffh-conformance` | Compares a final diff with its sealed plan and reports missing instructions, unauthorized changes, and broken preservation rules. | None. | `/construct`, for an earned conformance review. | A generic subagent. |
| `ffh-evidence` | Answers one bounded repository question with exact file and line evidence. | None. | `/architect` and `/diagnose`, for evidence workers that need only file reads; `/blueprint`, `/architect`, and `/diagnose`, for a large sweep of more than about 8 files or a whole-repository search. | A generic subagent for evidence workers. A large sweep is done by the main agent. |
| `ffh-researcher` | Answers one bounded research question from current sources and cites them. | Web search and page fetch. | `/ideate`, for a Deep ideation's research workers. | A generic subagent. |
| `ffh-constructor` | Runs `/construct` on a sealed plan and returns its report. | File edits, a shell, and loading skills, used as `/construct` directs. | `/blueprint`, when it hands a sealed plan to `/construct`. | A generic subagent. |
| `ffh-planner` | Runs `/blueprint`'s planning stage after `/blueprint` has asked the questions it can already see, and returns its seal or stop report. | File edits, a shell, and loading skills, used as `/blueprint` directs. | `/blueprint`, when another skill orchestrating a larger task starts it or the session already holds much unrelated work. | `/blueprint` plans in the main session. |

No subagent may start another. `ffh-planner` stops when its plan needs a fresh challenger, a question answered, or `/ideate`, and `/blueprint` in the main session does that and resumes it. `ffh-constructor` cannot start the conformance review its `/construct` run earns, so it reports the review as earned and not run, and the agent that started it launches the review or reports it as not run.

## Choosing models

`ffh-constructor` and `ffh-planner` each own a whole stage, so `/provision` recommends a model that can carry out a plan unaided, or write and seal one, rather than the cheapest model. For the other five it recommends the cheapest model and effort likely to do the job well. [Provision](../skills/provision.md) describes how you choose.

## Harness differences

- On Codex and OpenCode the names use underscores, such as `ffh_planner`.
- No subagent starts another, so no harness needs nested subagents. On Codex and OpenCode, `/provision` offers to remove the `agents.max_depth` or `experimental.subagent_depth` setting an earlier version may have raised to 2.
- On Claude Code, `ffh-planner` keeps a one-hour prompt cache.
- A read-only subagent with a shell could still change files through it, so on every harness its no-edit limit rests on its instructions. `/provision` asks you to skip such a subagent or accept that limit.

## batch-ops

When batch-ops is connected, `/provision` asks which subagents read, search, run commands, and edit only through batch-ops' `batch_read`, `batch_run`, and `batch_edit` tools, with all selected by default. Changing that choice later takes a `/provision` rerun.

## Sources

- [Provision's agent definitions](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/provision/references/agents.md)
- Delegation guidance: [`/architect`](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/architect/references/delegation-protocol.md), [`/assess`](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/assess/references/delegation-protocol.md), [`/blueprint`](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/blueprint/references/delegation-protocol.md), [`/construct`](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/construct/references/delegation-protocol.md), [`/diagnose`](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/diagnose/references/delegation-protocol.md), [`/ideate`](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/sensemaking/ideate/references/delegation-protocol.md), [`/reason`](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/sensemaking/reason/references/delegation-protocol.md)
- `/blueprint` handoffs: [challenge](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/blueprint/references/challenge-and-rehearsal.md), [construct](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/blueprint/references/construct-handoff.md), [planner](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/blueprint/references/planner-handoff.md)

# Provision

`/provision` sets up First Four Hours in the agent harness you run it in. After you confirm, it installs any Python packages the installed skills declare. It then writes up to seven subagents for the suite's delegated work, each on the model and effort you choose. It also offers batch-ops, an optional MCP server that no skill needs. It belongs to the Workbench domain.

## When to use it

- You just installed the suite, or updated your harness, and want its requirements installed and its subagents in place.
- Newer models are out, or a model you chose is gone, and you want fresh recommendations.
- You want to remove the subagents it wrote.

## When to use something else

- To install the skills themselves, follow [Install First Four Hours](../getting-started/installation.md); `/provision` runs once they are installed.
- `/provision` sets up only the harness it runs in. Run it again in each harness you use.

## How to start it

Only you can start `/provision`: type `/provision`. The agent never starts it on its own, except on OpenCode, which ignores that setting. For example (illustrative):

```text
/provision : I installed the suite in this project for Codex. Set up the subagents, and put the reviewer on the strongest model you list.
```

## What happens

1. `/provision` identifies the harness and whether the suite is installed for this project or for your user account.
2. It lists the `requirements.txt` files of the installed skills and installs them with the agent's Python only after you confirm. If Python refuses because the environment is externally managed, it offers a virtual environment, at a location you confirm, instead of overriding that.
3. It offers batch-ops, an optional MCP server whose `batch_read`, `batch_run`, and `batch_edit` tools read many files, run several commands, or apply several edits with rollback in one call. Only after you say yes, it installs the `mcp` and `pydantic` packages with the same Python, registers the server with your harness, and checks that the harness shows it connected. If your harness cannot run a local MCP server, it says so and skips this. It replaces a `batch-ops` entry you added yourself only after you agree. When its own entry is already there, it shows that entry's batch-ops version beside the one it carries and lets you update, keep, or remove it. After an install or update, it offers to add one line to your `CLAUDE.md` or `AGENTS.md`, for the project or your user account as the suite is installed, telling the agent to prefer batch-ops' tools.

4. It maps each subagent's fixed permissions onto the harness. Where the harness cannot enforce one, it explains the gap, and you choose whether to skip that subagent or accept limits that rest only on its instructions. For example, Codex cannot stop an agent from editing files, and on any harness a subagent with a shell could edit files through it. `ffh-planner` is written only where a subagent can start subagents and `ffh-challenger` is written too; on Codex and OpenCode only after you let `/provision` raise `agents.max_depth` or `experimental.subagent_depth` to 2. When batch-ops is connected, you choose which subagents use only batch-ops' tools, with all selected by default.
5. It lists the models your harness offers now and recommends the cheapest model and effort likely to do each subagent's job well, with a one-line reason; for `ffh-constructor` and `ffh-planner`, which each own a whole stage, that is a model able to carry out or write a plan unaided. On a re-run it shows your current choices beside fresh recommendations and flags any your harness no longer offers. You accept every recommendation or choose per subagent.
6. It writes the subagents, then checks that the harness loaded them with the chosen model.
For a harness it has no notes for, it reads that harness's official documentation first and shows you each file before writing it.

## What you get

Up to seven subagents in your harness's agent folder: `ffh-challenger`, `ffh-reviewer`, `ffh-conformance`, `ffh-evidence`, `ffh-researcher`, `ffh-constructor`, and `ffh-planner`. On Codex and OpenCode their names use underscores. [First Four Hours subagents](../reference/agents.md) says what each one does, what it can access, and which skills use it. On OpenCode subagents use the V2 `permissions` format. Their names, descriptions, permissions, and instructions are fixed; only the model and effort are yours. The report lists each subagent as loaded, or as written but unverified with the step that confirms it, such as a restart. For each subagent you skipped or accepted with instruction-only limits, it names the limits the harness could not enforce.

If you chose batch-ops, your harness's MCP settings gain a `batch-ops` server entry (`batch_ops` on Codex) that runs it with the Python that has its packages. On Claude Code it follows the suite's install scope and stays private to you. On Codex and OpenCode it is registered for your user account, so every project sees it. No skill uses it; your agent may call its tools. The entry holds absolute paths, so run `/provision` again after you move or update the suite or that Python.

Where your harness has a tool for asking you questions, `/provision` asks its setup questions through it.

## When it stops

If the harness has no custom subagents or cannot set a model per subagent, `/provision` writes none, removes any it wrote before once you confirm, and the skills keep their generic subagents. Without your yes it installs nothing. On a re-run, a subagent you now skip is removed after you confirm, and so are its batch-ops entry and its batch-ops line in your `CLAUDE.md` or `AGENTS.md` when you now decline batch-ops. To uninstall, ask `/provision` to remove its subagents: after you confirm, it deletes only its `ffh-` and `ffh_` agent files, its batch-ops entry, and the batch-ops line it added to your `CLAUDE.md` or `AGENTS.md`, and leaves installed packages in place. It also offers to remove the depth setting it raised, after you confirm. Adding or removing batch-ops later needs a rerun to rewrite the subagents.

## Why it's built this way

**The failure it prevents.** Not every job needs the most expensive model in the room, and paying for one on every lookup adds up quietly. Several skills hand bounded work, such as a fresh challenge or an evidence lookup, to a subagent that runs on whatever model the session uses, and `/blueprint` hands a sealed plan's whole implementation to `/construct` the same way. `/provision` lets each of those roles run on the cheapest model and effort that still gives a quality result for it, and lets you refresh those choices as models change. The owner set this out in [issue #129](https://github.com/akshay-diwadkar/first-four-hours/issues/129) and [issue #174](https://github.com/akshay-diwadkar/first-four-hours/issues/174).

**What it refuses, and why.** The skill names no model or effort. They come from your harness's current list and your choice, so its recommendations do not go stale inside the skill. It never changes a file other than its own subagent files, its own batch-ops entry, the batch-ops line it adds to your `CLAUDE.md` or `AGENTS.md`, and a virtual environment you confirm, never installs without your yes, and never reports a subagent as ready until the harness shows it loaded.

**Floor and ceiling.** A weaker agent gets each known harness's file format, permission mapping, and model-listing method written down, plus fixed agent definitions to copy exactly. A stronger agent judges which model fits each role, and researches a harness the skill has no notes for.

## Related skills

`/blueprint`, `/reason`, `/assess`, `/construct`, `/architect`, `/diagnose`, and `/ideate` use these subagents by name for the work each is for, and a generic subagent, as before, when one is missing, with the exceptions [First Four Hours subagents](../reference/agents.md) lists. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[`/provision`'s contract](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/provision/SKILL.md)

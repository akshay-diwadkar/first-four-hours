# Provision

Provision sets up First Four Hours in the agent harness you run it in. After you confirm, it installs the Python packages some skills need. It then writes up to five subagents for the suite's delegated work, each on the model and effort you choose. It belongs to the Workbench domain.

## When to use it

- You just installed the suite, or updated your harness, and want its requirements installed and its subagents in place.
- Newer models are out, or a model you chose is gone, and you want fresh recommendations.
- You want to remove the subagents it wrote.

## When to use something else

- To install the skills themselves, follow [Install First Four Hours](../getting-started/installation.md); Provision runs once they are installed.
- Provision sets up only the harness it runs in. Run it again in each harness you use.

## How to start it

Only you can start Provision: type `/provision`. The agent never starts it on its own, except on OpenCode, which ignores that setting. For example (illustrative):

```text
/provision : I installed the suite in this project for Codex. Set up the subagents, and put the reviewer on the strongest model you list.
```

## What happens

1. Provision identifies the harness and whether the suite is installed for this project or for your user account.
2. It lists the `requirements.txt` files of the installed skills and installs them with the agent's Python only after you confirm. If Python refuses because the environment is externally managed, it offers a virtual environment, at a location you confirm, instead of overriding that.
3. It maps each subagent's fixed permissions onto the harness. Where the harness cannot enforce one, it explains the gap, and you choose whether to skip that subagent or accept limits that rest only on its instructions. For example, Codex cannot stop an agent from editing files, and on any harness a subagent with a shell could edit files through it.
4. It lists the models your harness offers now and recommends the cheapest model and effort likely to do each subagent's job well, with a one-line reason. On a re-run it shows your current choices beside fresh recommendations and flags any your harness no longer offers. You accept every recommendation or choose per subagent.
5. It writes the subagents, then checks that the harness loaded them with the chosen model.

For a harness it has no notes for, it reads that harness's official documentation first and shows you each file before writing it.

## What you get

Up to five subagents in your harness's agent folder: `ffh-challenger`, `ffh-reviewer`, `ffh-conformance`, `ffh-evidence`, and `ffh-researcher`. On Codex and OpenCode their names use underscores. Their names, descriptions, permissions, and instructions are fixed; only the model and effort are yours. The report lists each subagent as loaded, or as written but unverified with the step that confirms it, such as a restart. For each subagent you skipped or accepted with instruction-only limits, it names the limits the harness could not enforce.

## When it stops

If the harness has no custom subagents or cannot set a model per subagent, Provision writes none, removes any it wrote before once you confirm, and the skills keep their generic subagents. Without your yes it installs nothing. On a re-run, a subagent you now skip is removed after you confirm. To uninstall, ask Provision to remove its subagents: after you confirm, it deletes only its `ffh-` and `ffh_` agent files and leaves installed packages in place.

## Why it's built this way

**The failure it prevents.** Several skills hand bounded work, such as a fresh challenge or an evidence lookup, to a subagent that runs on whatever model the session uses. Provision lets each of those roles run on the cheapest model and effort that still gives a quality result, and lets you refresh those choices as models change. The owner set this out in [issue #129](https://github.com/akshay-diwadkar/first-four-hours/issues/129).

**What it refuses, and why.** The skill names no model or effort. They come from your harness's current list and your choice, so its recommendations do not go stale inside the skill. It never changes a file other than its own subagent files and a virtual environment you confirm, never installs without your yes, and never reports a subagent as ready until the harness shows it loaded.

**Floor and ceiling.** A weaker agent gets each known harness's file format, permission mapping, and model-listing method written down, plus fixed agent definitions to copy exactly. A stronger agent judges which model fits each role, and researches a harness the skill has no notes for.

## Related skills

Blueprint, Reason, Assess, Construct, Architect, Diagnose, and Ideate use these subagents by name for the work each is for, and a generic subagent, as before, when one is missing. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Provision's contract](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/provision/SKILL.md)

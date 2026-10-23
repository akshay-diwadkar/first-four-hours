# Construct

Construct carries out a sealed Blueprint plan: it applies each instruction in order, runs the plan's verification, compares the final diff with the plan, and reports. It belongs to the Workbench domain.

## When to use it

You have a sealed `blueprint.md` and want it implemented faithfully, possibly by a cheaper model than the one that planned it.

## When to use something else

- Without a sealed plan, start with [Blueprint](blueprint.md). Construct does not plan.
- To review the finished change, use [Assess](assess.md).

## How to start it

Start it yourself with `/construct`, or the agent may start it when your request matches. It needs a Git worktree. For example:

```text
/construct : Implement the sealed blueprint in .first-four-hours/blueprints/<task-slug>/blueprint.md.
```

## What happens

Construct checks the plan's seal and that the files it was planned against have not changed. It then implements each instruction in order, writing any text the plan fixes exactly as declared, and proves each step that declares proof, with at most three attempts per step. It may repair its own coding mistakes, but it never changes the plan's method, scope, or decisions. After the last instruction it repairs [Atlas](atlas.md) links to files the plan deleted and lists other pointers the change may affect, runs the plan's verification, and compares the final diff with the plan once. It writes no state of its own, so a resumed run rereads progress from the worktree. It never edits the plan and never commits.

## What you get

Your worktree with the change applied, and a report of the instructions, proof results, checks run before the change, each final verification command with its expected result and whether the output met it, Atlas repairs, and whether protected paths and HEAD are unchanged. Conditions marked `Owner gate:` are listed as pending for their owner.

## When it stops

| Result | Meaning | What to do |
| :--- | :--- | :--- |
| Completion report | Every instruction is applied, verification passed, and the diff matches the plan. | Review the result, settle the owner gates, then commit and open a pull request. |
| `verification-incomplete` | A check the plan declared environmental did not finish. | Run Construct again when the environment is healthy. An incomplete check is never a pass. |
| `plan-contradiction` | The plan is stale, wrong, or incomplete against the actual code. | Run a new `/blueprint` with the original request and Construct's evidence, then a fresh `/construct`. |
| `protected-work-conflict` | Continuing would overwrite unrelated uncommitted work. | That work's owner resolves it, then run a fresh `/construct`. |
| `safety-contradiction` | A safety check failed or the baseline moved, for example HEAD changed. | Restore a trusted state, then run a fresh `/construct`. |
| Stopped with evidence | A step failed its third attempt, or a resume cannot verify earlier progress. | Judge the diff, then run a fresh `/construct` from a trustworthy worktree, or take the evidence back to `/blueprint` when the plan is at fault. |

## Why it's built this way

**The failure it prevents.** Ordinary implementation agents drift from instructions: they redesign while coding, take a shortcut the plan ruled out, or "improve" a decision they do not understand. Construct makes execution follow the plan reliably, so a weaker, cheaper executor can carry out a strong planner's decisions faithfully.

**What it refuses, and why.** It never changes the plan's method, scope, or decisions, and never edits the plan. It fixes its own coding mistakes, but when the plan disagrees with the actual code it stops with `plan-contradiction` and its evidence instead of improvising. An executor that quietly patches planning gaps has become the planner, without the planner's grounding or challenge. It keeps no state of its own, so a resumed run rereads progress from the worktree instead of trusting an earlier success message.

**Floor and ceiling.** A weaker executor gets ordered steps, exact text to write verbatim, proof for each step with a bounded number of attempts, and a final comparison of the diff with the plan. A stronger executor still writes its own code for every step the plan specifies in prose; pseudocode fixes decisions, not wording.

## Related skills

Fix review findings the same way: plan the fix with a new Blueprint and apply it with a fresh Construct, so the planner keeps every decision. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Construct's contract](../../skills/workbench/construct/SKILL.md)

# Plan a change before your agent starts editing

An agent that starts editing before the decisions are made settles them halfway through, and redoes work when one turns out wrong. Blueprint settles every decision first and seals a plan. Construct then carries the plan out without reopening it, in the same session or a later one, possibly with a cheaper model.

## Use this when

- The change touches several files, or it has to be right the first time.
- Another agent, a later session, or a cheaper model will implement it.
- You know the outcome you want.

## Use something else when

- The cause of a problem is unknown: [Fix the bug without patching the symptom](fix-a-bug.md).
- The right structure is the open question: [Settle the structure before agents add parallel machinery](settle-structure.md).
- The change is finished and needs review: [Trust a change before you merge it](review-before-merge.md).
- The edit is small and clear: it needs no plan.

## Steps

1. Start Blueprint with the outcome, the constraints, and what must not change.
2. Answer only the questions it asks. If it shows you directions from [Ideate](../skills/ideate.md), the choice is yours, and its recommendation is not your approval.
3. Read the sealed plan's Goal summary. The seal proves the plan's shape and its binding to the files it read. Nothing is implemented yet.
4. Start Construct on the sealed plan in a Git worktree.
5. Read Construct's report and settle the conditions it lists as `Owner gate:`. Then commit and open a pull request yourself, or with [PR](../skills/pr.md).

## Example

For example (illustrative):

```text
/blueprint : Plan adding rate limiting to the public search endpoint; existing API clients must keep working unchanged.
```

```text
/construct : Implement the sealed blueprint in .first-four-hours/blueprints/<task-slug>/blueprint.md.
```

`<task-slug>` is a placeholder for the folder Blueprint reports. Blueprint leaves `blueprint.md` and `request.md` in `.first-four-hours/blueprints/<task-slug>/`, which Git ignores. Construct leaves the change in your worktree, with a report.

## You are done when

Construct's report shows every instruction applied, the plan's verification passed, and the diff matching the plan, and you have settled its owner gates. The agent saying it is done is not the signal.

## If it goes wrong

- Blueprint will not seal: it is waiting on a question only you can answer, so answer it ([Blueprint](../skills/blueprint.md)).
- Construct stops with `plan-contradiction`: run a new `/blueprint` with the original request and Construct's evidence, then a fresh `/construct`. Never patch the plan ([Construct](../skills/construct.md)).
- Construct reports `verification-incomplete`: run it again when the environment is healthy. An incomplete check is never a pass ([Construct](../skills/construct.md)).
- Construct stops any other way: follow the table on [Construct](../skills/construct.md).

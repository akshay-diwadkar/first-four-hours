# Settle the structure before agents add parallel machinery

When no one has decided which part of the code owns a job, agents add a new helper, cache, or pipeline beside the one that already exists, and the codebase grows two ways to do one thing. Architect decides where the responsibility belongs first. Blueprint then plans around that decision instead of guessing.

## Use this when

- The open question is a boundary, a dependency direction, who owns some state, or whether to consolidate duplicated mechanisms.
- You suspect the design needs work but have no specific target.

## Use something else when

- The structure is already settled: [Plan a change before your agent starts editing](plan-a-change.md).
- A defect has an unknown cause: [Fix the bug without patching the symptom](fix-a-bug.md).
- The goal is not mainly structural and you need options compared: [Ideate](../skills/ideate.md).

## Steps

1. Start Architect with the structural question.
2. Read the sealed `architecture.md`. It holds the selected structure with its owner, boundary, and consequences, or a no-change outcome. No change is a valid answer, and it ends the recipe.
3. Start Blueprint on `architecture.md`. It plans around the decision rather than reopening it.
4. Carry out the plan with Construct, as in [Plan a change before your agent starts editing](plan-a-change.md).

## Example

For example (illustrative):

```text
/architect : Decide where retry logic for outbound HTTP calls should live; three services each keep their own copy.
```

```text
/blueprint : Plan the change described in .first-four-hours/architectures/<slug>/architecture.md.
```

`<slug>` is a placeholder for the folder Architect reports.

## You are done when

`architecture.md` is sealed with a selected structure or a no-change outcome. When you go on, Construct's report shows the plan built on it was applied and verified.

## If it goes wrong

- Architect ends with a blocker: supply the evidence or the policy decision it names, then run it again ([Architect](../skills/architect.md)).
- You no longer agree with the structure while planning: run Architect again on the new question instead of asking Blueprint to redesign it ([Architect](../skills/architect.md)).
- Construct stops: follow [Construct](../skills/construct.md).

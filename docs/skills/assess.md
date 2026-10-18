# Assess

Assess reviews one exact proposed change, such as a branch or pull request, against what it was supposed to do. It checks correctness, code quality, and maintainability, and checks security where the change touches trust or permission boundaries, inputs, sensitive data, or risky operations. It belongs to the Workbench domain.

## When to use it

- A change is finished and you need to know whether it does what its issue, specification, or Blueprint asked, without breaking existing behavior.
- You want a re-review after rework, or an acceptance-criteria check before merge.

## When to use something else

- To fix what Assess finds, plan the fix with [Blueprint](blueprint.md) and apply it with [Construct](construct.md). Assess never edits code.
- To investigate a broader defect or risk whose cause is unknown, use [Diagnose](diagnose.md).
- To write the pull request description, use [PR](pr.md).

## How to start it

Start it yourself with `/assess`, or the agent may start it when your request matches. For example (illustrative):

```text
/assess : Assess this branch against issue #42 and the current main branch before merge.
```

## What happens

Assess fixes the exact target, base, and head, reads the authoritative requirements, and works out what the change must do before it reads pull request prose or earlier reviews. Those can suggest concerns but never clear one. It reports every independently material defect it finds, not only the first. If the same agent wrote or planned the change, Assess first asks for a fresh-context review, and it discloses any part that only a self-review examined. It consults [Reason](reason.md) at its judgment points.

## What you get

A sealed `assessment.md` in the ignored folder `.first-four-hours/assessments/<slug>/`, with one result:

- `clear`: no material defect was found after sufficient examination;
- `findings`: evidenced material defects, each with its location, consequence, and severity;
- `blocked`: missing or contradictory authority or evidence prevents a trustworthy result.

No result is approval, certification, or permission to merge.

## When it stops

Assess returns `blocked` when it cannot establish the authority or evidence it needs, for example when it cannot confirm that an external source is current.

When an evidence-backed risk beyond the change could alter the merge decision, Assess stops before sealing and asks you to run `/diagnose` on that risk. You then run Assess again with the resulting `diagnosis.md`; if that diagnosis is missing or contradictory, Assess returns `blocked`.

## Related skills

Findings usually lead to a new Blueprint and a fresh Construct run. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Assess's contract](../../skills/workbench/assess/SKILL.md)

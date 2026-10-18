# Architect

Architect decides a structural question about a codebase before anyone plans the change: where a boundary sits, which way dependencies point, who owns a piece of state, whether an abstraction or consolidation is worth it, and how modules, classes, or subsystems should be organized. It belongs to the Workbench domain.

## When to use it

- The right structure is the open question, and a plan would otherwise have to guess it.
- You suspect the design needs work but have no specific target. Architect can first look for bounded opportunities, and it may conclude that no design change is needed.

## When to use something else

- To plan file-level edits, tests, and verification for a settled structure, use [Blueprint](blueprint.md). Architect stops at architecture and never prescribes file-level edits, migration order, or tests.
- To find the cause of a defect, use [Diagnose](diagnose.md).
- To compare options for a goal that is not mainly structural, use [Ideate](ideate.md).

## How to start it

Start it yourself with `/architect`, or the agent may start it when your request matches. For example (illustrative):

```text
/architect : Decide whether the billing and invoicing modules should share one persistence layer.
```

## What happens

Architect grounds the question in the repository, applies design principles where they help, and prefers the simplest structure that meets the goal. It consults [Reason](reason.md) at its judgment points. It edits no implementation files.

## What you get

A sealed `architecture.md` in the ignored folder `.first-four-hours/architectures/<slug>/`. It records the structural pressure or a no-change outcome, the owner and boundary, constraints, the selected architecture, its consequences, the evidence, and the unknowns that affect trust.

## When it stops

Architect can end with a blocker instead of a design when evidence or a policy only you can set is missing. If sealing fails, it repairs the draft and seals again; if the evidence changed, it refreshes and seals against the new state.

## Related skills

Blueprint plans around the direction in `architecture.md`; starting Blueprint is your choice. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Architect's contract](../../skills/workbench/architect/SKILL.md)

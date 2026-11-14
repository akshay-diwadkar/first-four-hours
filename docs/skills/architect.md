# Architect

`/architect` decides a structural question about a codebase before anyone plans the change: where a boundary sits, which way dependencies point, who owns a piece of state, whether an abstraction or consolidation is worth it, and how modules, classes, or subsystems should be organized. It belongs to the Workbench domain.

## When to use it

- The right structure is the open question, and a plan would otherwise have to guess it.
- You suspect the design needs work but have no specific target. `/architect` can first look for bounded opportunities, and it may conclude that no design change is needed.

## When to use something else

- To plan file-level edits, tests, and verification for a settled structure, use [`/blueprint`](blueprint.md). `/architect` stops at architecture and never prescribes file-level edits, migration order, or tests.
- To find the cause of a defect, use [`/diagnose`](diagnose.md).
- To list several maintainability problems across a repository, start [`/diagnose`](diagnose.md) yourself with `/diagnose` and ask for a broad code-quality pass. `/architect` settles one structural target per run; bring a structural finding from that list back here.
- To compare options for a goal that is not mainly structural, use [`/ideate`](ideate.md).

## How to start it

Start it yourself with `/architect`, or the agent may start it when your request matches. For example (illustrative):

```text
/architect : I inherited this repository and everyone calls it a mess, but nobody can say what to fix first, and I do not know software design. Look through it for technical debt in how it is organized, tell me the one problem that costs us the most, and decide how to fix it. If the structure is actually fine, say so. Explain it in plain words.
```

## What happens

`/architect` grounds the question in the repository. Before choosing a structure, it looks for every existing mechanism that already does the job and makes it the owner, merges it, or records why it stays separate, instead of quietly adding a parallel one. It applies design principles where they help, and prefers the simplest structure that meets the goal. It consults [`/reason`](reason.md) at its judgment points. It edits no implementation files.

## What you get

A sealed `architecture.md` in the ignored folder `.first-four-hours/architectures/<slug>/`. It records the structural pressure or a no-change outcome, the owner and boundary, constraints, the selected architecture, its consequences, the evidence, and the unknowns that affect trust.

## When it stops

`/architect` can end with a blocker instead of a design when evidence or a policy only you can set is missing. If sealing fails, it repairs the draft and seals again; if the evidence changed, it refreshes and seals against the new state.

## Why it's built this way

**The failure it prevents.** Open any codebase old enough and you will find two ways to do the same thing, each added by someone who could not see the other. When nobody has decided where a responsibility lives, each agent decides on its own, and the codebase grows a second cache, a third retry helper, or a parallel pipeline. Each one looks reasonable in its own diff. `/architect` makes the structural decision once, with experienced engineering judgment, so the plans that follow build on it instead of guessing.

**What it refuses, and why.** It never prescribes file-level edits, migration order, or tests. Those belong to `/blueprint`, and a decision that also plans the change cannot be challenged as a plan. It does not add patterns for their own sake: the simplest structure that meets the goal wins, and "no design change" is a complete answer.

**Floor and ceiling.** A weaker agent has to fill a fixed decision shape: the owner and boundary, the constraints, the consequences, and the evidence for each. That stops it from reaching for a fashionable pattern without saying who owns what. A stronger agent stays free to choose the design concepts that fit, including SOLID where they help, at the level of a class, a module, or the whole system.

## Related skills

`/blueprint` plans around the direction in `architecture.md`; starting `/blueprint` is your choice. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[`/architect`'s contract](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/architect/SKILL.md)

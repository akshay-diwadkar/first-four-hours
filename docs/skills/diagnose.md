# Diagnose

Diagnose investigates a concrete problem, risk, or improvement opportunity and finds its cause from evidence before anyone decides on a fix. It belongs to the Workbench domain.

## When to use it

- Something is wrong and the cause is not yet known: a defect, a performance bottleneck, or runtime behavior you cannot explain by reading the code.
- You want to know what is materially worth improving, with evidence rather than generic advice.

## When to use something else

- To plan a fix once the cause is known, use [Blueprint](blueprint.md).
- To decide a structural question, use [Architect](architect.md).
- To review a finished change, use [Assess](assess.md).

## How to start it

Only you can start Diagnose: type `/diagnose`. The agent never starts it on its own. For example (illustrative):

```text
/diagnose : Find out why authentication tokens expire early under high concurrency.
```

## What happens

Diagnose stays on the named problem unless evidence earns a wider look. It traces symptoms through the repository, may consult authoritative technology documentation for version-specific behavior, and runs only non-mutating probes. It asks before using shared or billable resources or production data. It never edits the project or touches GitHub issues. It consults [Reason](reason.md) at its judgment points.

## What you get

A sealed `diagnosis.md` in the ignored folder `.first-four-hours/diagnoses/<slug>/`, reporting the symptoms, each finding with how well its cause is established, the limitations, and any advisory directions. Advisory directions are leads to investigate, not a recommendation or a plan.

## When it stops

Diagnose is complete only when its `diagnosis.md` is sealed. When the evidence cannot support a finding, it says what evidence is missing instead of guessing.

## Related skills

You decide what comes next: [Ideate](ideate.md) to explore options, [Blueprint](blueprint.md) with one finding ID to plan a fix, or nothing. Diagnose starts neither. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Diagnose's contract](../../skills/workbench/diagnose/SKILL.md)

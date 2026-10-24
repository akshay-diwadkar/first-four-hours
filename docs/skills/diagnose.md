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

Diagnose stays on the named problem unless evidence earns a wider look. It traces symptoms through the repository, may consult authoritative technology documentation for version-specific behavior, and runs only non-mutating probes: a probe that would write into your project, such as bisecting history, building, installing, or running tests that leave caches, runs in a throwaway copy outside your project with its own environment, runs with those writes switched off, or is left for you to run. For a regression from a known-good version, it usually reads the project's history before bisecting or running other probes to narrow down the cause. It asks before using shared or billable resources or production data. It never edits the project or touches GitHub issues. It consults [Reason](reason.md) at its judgment points.

## What you get

A sealed `diagnosis.md` in the ignored folder `.first-four-hours/diagnoses/<slug>/`, reporting the symptoms, each finding with how well its cause is established, the limitations, and any advisory directions. Advisory directions are leads to investigate, not a recommendation or a plan.

## When it stops

Diagnose is complete only when its `diagnosis.md` is sealed. When the evidence cannot support a finding, it says what evidence is missing instead of guessing.

## Why it's built this way

**The failure it prevents.** When the cause is unknown, agents patch the place where the symptom shows, or answer with generic advice such as "add caching" or "raise the timeout", and the problem returns somewhere else. Diagnose investigates with a senior diagnostic specialist's depth: it traces the symptom through the project and explains what each piece of evidence establishes and how it connects to the symptom.

**What it refuses, and why.** It never edits the project and never chooses a fix. Its advisory directions are leads, not a recommendation, a design, or a plan. An investigation that is also allowed to fix tends to stop at the first plausible cause. It never states a cause more strongly than the evidence supports: a cause is `demonstrated` only when executed evidence shows that changing it moves the effect, and documentation or another project's incident can support a mechanism but never prove this project's cause. When evidence is missing, it names what is missing instead of guessing. Only you start it, and you decide what follows.

**Floor and ceiling.** A weaker agent must back every finding with current, inspectable evidence and explain what each citation shows, because a citation alone explains nothing. A stronger agent chooses its own techniques, probes, and version-specific documentation, and widens the investigation when the evidence earns it.

## Related skills

You decide what comes next: [Ideate](ideate.md) to explore options, [Blueprint](blueprint.md) with one finding ID to plan a fix, or nothing. Diagnose starts neither. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Diagnose's contract](../../skills/workbench/diagnose/SKILL.md)

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

## A worked scenario

*Illustrative: Larder is a made-up project, and this is not a recorded run. Excerpts are shortened.*

Larder calls three outside services: the payment provider, the email service, and the stock supplier. Each client has its own retry loop, with its own backoff and its own idea of which errors to retry. A new delivery-slot client is next, and an agent asked to "add retries" would write a fourth.

```text
/architect : Decide where retry logic for Larder's outbound HTTP calls should live; payments, messages, and stock each keep their own copy.
```

Architect reads the three loops and finds they differ in only two ways that matter: which responses are safe to retry, and how long a call may keep trying. One difference is not a matter of taste: a payment must never be retried when the charge may already have gone through.

```markdown
## Decision

- Selected architecture: one retry policy in the shared HTTP client; each service client passes its retryable responses and time budget as configuration.
- Owner / boundary: the shared HTTP client owns how to retry; each service client owns what is safe to retry.
- Invariants / constraints: a payment request is retried only when the provider confirms it was not received.
- Consequences: the three loops are removed, and the delivery-slot client gets retries through configuration instead of a fourth copy.
```

Architect did not name files to edit, an order of migration, or tests. That is Blueprint's job, and Blueprint plans around this decision instead of reopening it.

```text
/blueprint : Plan the change described in .first-four-hours/architectures/outbound-retry-policy/architecture.md.
```

## You are done when

`architecture.md` is sealed with a selected structure or a no-change outcome. When you go on, Construct's report for the plan built on it shows every instruction applied, the plan's verification passed, and the diff matching the plan, and you have settled its owner gates.

## If it goes wrong

- Architect ends with a blocker: supply the evidence or the policy decision it names, then run it again ([Architect](../skills/architect.md)).
- You no longer agree with the structure while planning: run Architect again on the new question instead of asking Blueprint to redesign it ([Architect](../skills/architect.md)).
- Construct stops: follow [Construct](../skills/construct.md).

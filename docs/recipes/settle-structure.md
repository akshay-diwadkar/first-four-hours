# Settle the structure before agents add parallel machinery

Many codebases have a second cache. Nobody decided to build it. An agent could not find the first one, or could not tell it was allowed to use it.

When no one has decided which part of the code owns a job, agents add a new helper, cache, or pipeline beside the one that already exists, and the codebase grows two ways to do one thing. `/architect` decides where the responsibility belongs first. `/blueprint` then plans around that decision instead of guessing.

## Use this when

- The open question is a boundary, a dependency direction, who owns some state, or whether to consolidate duplicated mechanisms.
- You suspect the design needs work but have no specific target.
- An agent added an abstraction "for flexibility" that nobody asked for, and you want the structure decided instead of accumulated.

## Use something else when

- The structure is already settled: [Plan a change before your agent starts editing](plan-a-change.md).
- A defect has an unknown cause: [Fix the bug without patching the symptom](fix-a-bug.md).
- The goal is not mainly structural and you need options compared: [`/ideate`](../skills/ideate.md).

## Steps

1. Start `/architect` with the structural question.
2. Read the sealed `architecture.md`. It holds the selected structure with its owner, boundary, and consequences, or a no-change outcome. No change is a valid answer, and it ends the recipe.
3. Start `/blueprint` on `architecture.md`. It plans around the decision rather than reopening it.
4. Carry out the plan with `/construct`, as in [Plan a change before your agent starts editing](plan-a-change.md).

## A worked scenario

*Illustrative: FreshCart is a made-up online grocery service, and this is not a recorded run. Excerpts are shortened.*

FreshCart calls three outside services: the payment provider, the email service, and the stock supplier. Each client has its own retry loop, with its own backoff and its own idea of which errors to retry. A new delivery-slot client is next, and an agent asked to "add retries" would write a fourth. Mateo Rojas, who owns checkout, knows what a careless payment retry costs: one basket, two charges.

```text
/architect : Payments, messages, and stock each keep their own retry loop with their own idea of what is safe to retry, and a delivery-slot client is about to become the fourth. Decide where retry logic for FreshCart's outbound HTTP calls should live.
```

`/architect` reads the three loops and finds they differ in only two ways that matter: which responses are safe to retry, and how long a call may keep trying. One difference is not a matter of taste: a payment must never be retried when the charge may already have gone through.

```markdown
## Decision

- Selected architecture: one retry policy in the shared HTTP client; each service client passes its retryable responses and time budget as configuration.
- Owner / boundary: the shared HTTP client owns how to retry; each service client owns what is safe to retry.
- Invariants / constraints: a payment request is retried only when the provider confirms it was not received.
- Consequences: the three loops are removed, and the delivery-slot client gets retries through configuration instead of a fourth copy.
```

`/architect` did not name files to edit, an order of migration, or tests. That is `/blueprint`'s job, and `/blueprint` plans around this decision instead of reopening it.

A fourth retry loop would have taken an afternoon to write. Sooner or later, one of the four would have retried a payment.

```text
/blueprint : Plan the change described in .first-four-hours/architectures/outbound-retry-policy/architecture.md.
```

## You are done when

`architecture.md` is sealed with a selected structure or a no-change outcome. When you go on, `/construct`'s report for the plan built on it shows every instruction applied, the plan's verification passed, and the diff matching the plan, and you have settled its owner gates.

## If it goes wrong

- `/architect` ends with a blocker: supply the evidence or the policy decision it names, then run it again ([`/architect`](../skills/architect.md)).
- You no longer agree with the structure while planning: run `/architect` again on the new question instead of asking `/blueprint` to redesign it ([`/architect`](../skills/architect.md)).
- `/construct` stops: follow [`/construct`](../skills/construct.md).

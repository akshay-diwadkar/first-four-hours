# Reason

Reason is a short, bounded check of a judgment: before an agent commits to an approach, after a failure or a change of direction, and before it presents a result. It can also restore a stuck decision or ask you the one question only you can answer. It belongs to the Sensemaking domain.

## When to use it

- You want a proposal or claim challenged before you rely on it.
- A decision is stuck because the goal, evidence, cause, or options are unresolved.

Several skills also consult it on their own at their judgment points; [How skills hand work to each other](../concepts/handoffs.md) names them.

## When to use something else

- Mechanical work with nothing left to judge, such as a rote edit or applying a decision-complete plan, skips Reason. [Construct](construct.md) does not consult it.
- To explore and compare options in depth, use [Ideate](ideate.md).

## How to start it

Start it yourself with `/reason`, or the agent may start it when your request matches. For example (illustrative):

```text
/reason : Challenge the claim that this API migration is backwards compatible.
```

## What happens

Reason picks the smallest branch that fits the concern:

- `decide` restores readiness when no defensible next move exists;
- `challenge` attacks one load-bearing claim in a concrete proposal or result;
- `ask` puts one smallest action-changing question to you when progress depends on a fact or choice only you can supply.

The agent that consulted it weighs the result, fixes supported gaps, and chooses any replacement itself.

## What you get

No file. Each consultation ends with a one- or two-line result naming what it examined and one disposition: material objection, missing evidence, needed user input, or no material concern. When you start Reason yourself, it returns its branch result to you. No result is approval or proof of correctness.

## When it stops

A consultation is one pass. Reason does not call itself again or start other skills.

## Related skills

Reason is an internal checkpoint of the skills that consult it, not a stage you must run between them. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Reason's contract](../../skills/sensemaking/reason/SKILL.md)

# Reason

`/reason` is a short, bounded check of a judgment: before an agent commits to an approach, after a failure or a change of direction, and before it presents a result. It can also restore a stuck decision or ask you what only you can answer. It belongs to the Sensemaking domain.

## When to use it

- You want a proposal or claim challenged before you rely on it.
- A decision is stuck because the goal, evidence, cause, or options are unresolved.

Several skills also consult it on their own at their judgment points; [How skills hand work to each other](../concepts/handoffs.md) names them.

## When to use something else

- Mechanical work with nothing left to judge, such as a rote edit or applying a decision-complete plan, skips `/reason`. [`/construct`](construct.md) does not consult it.
- To explore and compare options in depth, use [`/ideate`](ideate.md).

## How to start it

Start it yourself with `/reason`, or the agent may start it when your request matches. For example (illustrative):

```text
/reason : Everyone on the team agrees this API migration is backwards compatible, and that is what worries me. Challenge the claim before it reaches 300 integrators on Friday.
```

## What happens

`/reason` picks the smallest branch that fits the concern:

- `decide` restores readiness when no defensible next move exists;
- `challenge` attacks one load-bearing claim in a concrete proposal or result, preferring an observation whose expected result it states first, such as a file read, a search, or a run it names for the agent, over rereading the agent's own reasoning, and saying so when its result rests on no observation;
- `ask` puts the smallest action-changing question to you when progress depends on a fact or choice only you can supply, or several at once when no answer could change another.

The agent that consulted it weighs the result, fixes supported gaps, and chooses any replacement itself.

When the agent challenges its own non-trivial proposal or result and a wrong one would be hard to reverse or cross a safety, security, permission, or authority boundary, including a readiness claim that clears such an action, the challenge runs in a fresh-context subagent. That challenger gets the claim, its requirements, and its evidence, never the agent's reasoning, and the agent rechecks what it returns. Skills with their own fresh challenger, reviewer, or adversarial specialist, such as [`/blueprint`](blueprint.md), [`/assess`](assess.md), and [`/ideate`](ideate.md), use theirs instead. Where no subagent can start, or the host or you do not allow one, the challenge runs in the agent's own context and the agent tells you the fresh challenge did not run.

## What you get

No file. Each consultation ends with a one- or two-line result on its own line, outside the agent's answer (or as a set-off first line where only the answer is shown), naming what it examined, the risk it tested, and one disposition: material objection, missing evidence, needed user input, or no material concern. When you start `/reason` yourself, it returns its branch result to you. An objection, evidence gap, or needed input still open when the agent presents its result is resolved first or told to you with what would settle it, and the agent claims no readiness it undermines. No result is approval or proof of correctness.

## When it stops

A consultation is one pass, including when a fresh-context challenger runs it; that challenger starts nothing further. `/reason` does not call itself again or start other skills.

## Why it's built this way

**The failure it prevents.** Nobody can see their own blind spot; that is what makes it one. A weaker agent does not notice its own blind spots. It commits to an approach that rests on an unchecked assumption, drifts into a side quest, or presents a result without questioning it. `/reason` helps it reason more like a stronger model from the facts, constraints, and goals it already has, at the moments that matter: before committing to an approach, after a failure or a change of direction, and before presenting a result.

**What it refuses, and why.** It never takes over. It explains what needs reconsidering and why; the agent that consulted it owns the replacement and the work. It writes no file, starts no other skill, and never calls itself again, so a consultation cannot grow into a chain. Skills that rely on it consult it at those moments instead of only considering whether to, because an agent that cannot see its blind spot cannot judge whether it needs the check.

**Floor and ceiling.** A weaker agent gets a bounded check at fixed checkpoints, including after a failed tool, probe, identity check, or seal its work relies on. A stronger agent keeps each consultation in proportion to the stakes, and "no material concern" is a valid result for a non-trivial decision only once the strongest opposing argument has been stated, blind spots tested, and every load-bearing assumption verified; an untested affirmation is not a consultation. Simple tasks stay light, and mechanical work with nothing left to judge skips `/reason` entirely.

## Related skills

`/reason` is an internal checkpoint of the skills that consult it, not a stage you must run between them. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[`/reason`'s contract](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/sensemaking/reason/SKILL.md)

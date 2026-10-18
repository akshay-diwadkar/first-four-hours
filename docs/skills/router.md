# Router

Router lays out which skills a task needs and in what order, as far as that can be known now, and stops where the next step depends on a result that does not exist yet. It belongs to the Sensemaking domain.

## When to use it

- The next skill is not obvious.
- The work spans several skills.
- Part of the request may already be done, and you want only the steps still needed.

## When to use something else

When one skill obviously fits, use it directly; Router stays out of the way.

## How to start it

The suite marks Router as model-invoked: the agent starts it when a task matches, and it is not meant to be started by name. Ask for the outcome in plain words. For example (illustrative):

```text
Work out which skills I need to move our job queue from Redis to Postgres, and in what order.
```

## What happens

Router reads the current state, drops work that is already done, and lists only the skills still needed. Each step is a concrete skill, never a domain. A route that stops early is a correct answer, not a partial one. Router never runs a routed skill, plans, edits source, commits, or opens a pull request.

## What you get

A sealed `route.md` in the ignored folder `.first-four-hours/routes/<slug>/`. Each step names a skill, why it is needed now, its input, its expected result, and a ready-to-copy prompt. When the current state already meets the target, the route is a single `None:` line instead. Router ends by offering step 1's prompt.

## When it stops

Router stops at the first step whose need depends on an unmade decision, an unknown result, or a fact not yet produced. Running out of steps returns control to you; it does not mean the whole target is done, and a later state may need a fresh route.

## Related skills

Only your later yes starts a step. You run the prompt for a user-invoked skill, such as [Diagnose](diagnose.md), [Ticket](ticket.md), or [PR](pr.md), yourself. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Router's contract](../../skills/sensemaking/router/SKILL.md)

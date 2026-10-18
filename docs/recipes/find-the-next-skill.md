# Find the next step when work spans several skills

When the next skill is unclear, an agent either picks one and drifts into a side quest, or lays out a long plan that is wrong as soon as the first result comes in. Router lays out the skills as far as the next steps can be known now, and stops where a step depends on a result that does not exist yet.

## Use this when

- The next skill is not obvious.
- The work spans several skills.
- Part of the request may already be done.

## Use something else when

- One skill obviously fits: use it. See [Choose a skill](../getting-started/choosing-a-skill.md).
- A decision is stuck, rather than the route: [Get a stuck decision moving again](unstick-a-decision.md).

## Steps

1. Ask for the outcome in plain words. Router starts when the agent recognizes the task, not by name.
2. Read the sealed `route.md`. Each step names a skill, why it is needed now, its input, its expected result, and a ready-to-copy prompt.
3. Say yes to step 1's prompt. For [Diagnose](../skills/diagnose.md), [Ticket](../skills/ticket.md), and [PR](../skills/pr.md), you type the prompt yourself.
4. When the route runs out, ask again from the new state. A route never continues itself.

## Example

For example (illustrative):

```text
Work out which skills I need to add multi-tenant support to the reporting service, and in what order.
```

## You are done when

A fresh route is a single `None:` line, meaning the current state already meets the target. A route that runs out of steps does not by itself mean the target is done.

## If it goes wrong

- The route stops earlier than you expected: that is a correct answer. Produce the result it stops at, then ask for a fresh route ([Router](../skills/router.md)).
- A routed skill stops: follow that skill's page from [the skill index](../skills/README.md).

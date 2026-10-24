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
3. Say yes to step 1's prompt. For [Diagnose](../skills/diagnose.md) and [Ticket](../skills/ticket.md), you type the prompt yourself.
4. When the route runs out, ask again from the new state. A route never continues itself.

## A worked scenario

*Illustrative: Larder is a made-up project, and this is not a recorded run. Excerpts are shortened.*

Larder wants to send order updates by text message as well as by email.

```text
Work out which skills I need to add text-message order updates to Larder alongside email, and in what order.
```

Router reads the current state first. The job queue is already running, so "move sending onto the queue" is not a step. Larder's message code already sends through one channel interface, so adding a channel is not a structural question, and Architect is not a step either. No text-message provider is chosen yet, but that is not a separate step: Blueprint asks Ideate for the options inside its own run, and you choose there.

```markdown
# Route: text-message order updates alongside email

## Steps

1. `blueprint`
   - Why: the change touches the message code, settings, and templates, and needs a provider decision.
   - Input: this request and Larder's message code.
   - Result: a sealed `blueprint.md`.
2. `construct`
   - Why: carry out the sealed plan.
   - Input: the `blueprint.md` from step 1.
   - Result: the change in the worktree, with a report.
3. `assess`
   - Why: check the change against the request before anyone merges it.
   - Input: the change from step 2.
   - Result: an `assessment.md` that is `clear`, `findings`, or `blocked`.
```

Each step also carries a ready-to-copy prompt. The route stops after Assess, because what comes next depends on its result: a pull request after `clear`, or a fix after `findings`. A longer route would guess. When you get there, ask again; the fresh route starts from the new state.

## You are done when

A fresh route is a single `None:` line, meaning the current state already meets the target. A route that runs out of steps does not by itself mean the target is done.

## If it goes wrong

- The route stops earlier than you expected: that is a correct answer. Produce the result it stops at, then ask for a fresh route ([Router](../skills/router.md)).
- A routed skill stops: follow that skill's page from [the skill index](../skills/README.md).

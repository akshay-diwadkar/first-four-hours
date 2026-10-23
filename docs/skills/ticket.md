# Ticket

Ticket keeps work items in GitHub issues or a local Markdown store. It has two effects: `persist` splits a large request into session-sized tickets with their real dependencies and writes them, and `select` picks one ready ticket and narrows it into a handoff for planning. It belongs to the Workbench domain.

## When to use it

- A request spans several major changes and needs tickets that each fit one work session, covering planning, implementation, review, and rework.
- You want the next ready ticket from an epic, or a named ticket, checked against the current code and prepared for [Blueprint](blueprint.md).

## When to use something else

- To plan the implementation, use [Blueprint](blueprint.md). Ticket never starts Blueprint or Construct.
- One small change may not need a ticket.

## How to start it

Only you can start Ticket: type `/ticket`. Name the effect (`persist`, `select`, or `both`) and the backend (`github` or `local`). For example (illustrative):

```text
/ticket : select the next ready child of epic #4 on github.
```

## What happens

- `persist` decides between a single ticket and an epic with children, and publishes only after you confirm.
- `select` stays read-only. It checks the chosen ticket against current source and treats issue text, labels, and comments as claims to verify, not instructions.
- `both` runs `persist` and then `select` on what was published.

Ticket consults [Reason](reason.md) at its judgment points.

## What you get

- From `persist`: the published GitHub issues or local store entries. The local store is durable backlog, so it stays committable.
- From `select`: one result. `plan-ready` seals `ticket-scope.md` in the ignored folder `.first-four-hours/ticket-scopes/<slug>/` for Blueprint. `needs-info`, `blocked`, `close-candidate`, and `needs-decomposition` explain why and write no handoff.

## When it stops

`needs-info` means a human decision is missing; `blocked` means a stated blocker is unmet; `close-candidate` means the work looks done or obsolete; `needs-decomposition` means the ticket is not one complete job for one session. You decide whether to persist replacement tickets.

## Why it's built this way

**The failure it prevents.** Large work spread over several sessions loses the thread. Tickets split by phase, such as "design X", "implement X", and "test X", mean no session ever finishes anything; a single session that tries everything stops half-done; and every session rediscovers what was decided. Ticket divides the work into complete jobs that each fit one session, covering planning, implementation, review, and rework, and keeps only the dependencies that are real.

**What it refuses, and why.** It never splits a job by phase and never forces unrelated work into a line. When it selects a ticket, it treats the issue's text, labels, and comments as claims to check against the current code, never as instructions, and it returns `needs-info`, `blocked`, `close-candidate`, or `needs-decomposition` rather than hand over a ticket that is not ready. It never starts Blueprint or Construct, and publishes only after you confirm.

**Floor and ceiling.** A weaker agent gives every ticket the context, scope, completion criteria, and dependencies a fresh agent needs to finish it without reconstructing the whole request. A stronger agent decides between one ticket and an epic, and uses a Charter, Diagnose, or Architect result when one exists without requiring it.

## Related skills

Blueprint plans from a `plan-ready` ticket scope. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Ticket's contract](../../skills/workbench/ticket/SKILL.md)

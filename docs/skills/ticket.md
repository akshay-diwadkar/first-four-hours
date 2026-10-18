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

## Related skills

Blueprint plans from a `plan-ready` ticket scope. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Ticket's contract](../../skills/workbench/ticket/SKILL.md)

# Work through a large ticket without losing the thread

Large work spread over several sessions loses the thread: each session rediscovers what was decided, or one session tries everything and stops half-done. Ticket splits the work into tickets that each fit one session and keeps their real dependencies. In each session it picks one ready ticket and checks it against the current code before planning.

## Use this when

- A request spans several major changes.
- You have an epic or backlog and want the next ready ticket checked against the current code.

## Use something else when

- The change fits one session: [Plan a change before your agent starts editing](plan-a-change.md).
- You do not know which skills the work needs: [Find the next step when work spans several skills](route-work-across-skills.md).

## Steps

1. Start Ticket's `persist` effect with the request and a backend, `github` or `local`. It publishes only after you confirm. A local store is committable backlog.
2. At the start of each session, start Ticket's `select` effect for the next ready ticket. A `plan-ready` result seals `ticket-scope.md`.
3. Plan it with Blueprint from that scope, and carry it out with Construct, as in [Plan a change before your agent starts editing](plan-a-change.md).
4. Review the result as in [Trust a change before you merge it](review-before-merge.md).
5. In the next session, run `select` again. It checks the next ticket against the code as it is now, not against what an earlier session recorded.

## Example

For example (illustrative):

```text
/ticket : persist the migration from the legacy job scheduler to the new queue on github.
```

```text
/ticket : select the next ready child of epic #<number> on github.
```

```text
/blueprint : Plan the ticket scope in .first-four-hours/ticket-scopes/<slug>/ticket-scope.md.
```

`#<number>` and `<slug>` are placeholders.

## You are done when

For a session: its one ticket is implemented, Construct's verification passed, and the change is reviewed. For the whole request: `select` finds no ticket left to do. Closing tickets is your decision.

## If it goes wrong

- `needs-info`: make the human decision it names ([Ticket](../skills/ticket.md)).
- `blocked`: finish the stated blocker first ([Ticket](../skills/ticket.md)).
- `needs-decomposition`: the ticket is not one session's job. Decide whether to persist replacement tickets ([Ticket](../skills/ticket.md)).
- `close-candidate`: the work looks done or obsolete. Decide whether to close it ([Ticket](../skills/ticket.md)).

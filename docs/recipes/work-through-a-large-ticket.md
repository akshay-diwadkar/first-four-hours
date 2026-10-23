# Work through a large ticket without losing the thread

Large work spread over several sessions loses the thread: each session rediscovers what was decided, or one session tries everything and stops half-done. Ticket splits the work into tickets that each fit one session and keeps their real dependencies. In each session it picks one ready ticket and checks it against the current code before planning.

## Use this when

- A request spans several major changes.
- You have an epic or backlog and want the next ready ticket checked against the current code.

## Use something else when

- The change fits one session: [Plan a change before your agent starts editing](plan-a-change.md).
- You do not know which skills the work needs: [Find the next step when work spans several skills](find-the-next-skill.md).

## Steps

1. Start Ticket's `persist` effect with the request and a backend, `github` or `local`. It publishes only after you confirm. A local store is committable backlog.
2. At the start of each session, start Ticket's `select` effect for the next ready ticket. A `plan-ready` result seals `ticket-scope.md`.
3. Plan it with Blueprint from that scope, and carry it out with Construct, as in [Plan a change before your agent starts editing](plan-a-change.md).
4. Review the result as in [Trust a change before you merge it](review-before-merge.md).
5. In the next session, run `select` again. It checks the next ticket against the code as it is now, not against what an earlier session recorded.

## A worked scenario

*Illustrative: Larder is a made-up project, and this is not a recorded run. Excerpts are shortened.*

Larder runs its scheduled work from a crontab on one server. Moving it to a job queue is too big for one session.

```text
/ticket : persist the move of Larder's scheduled jobs from cron to a job queue on github.
```

Ticket proposes an epic with four children. Each is one complete job that a session can plan, build, review, and rework, rather than a "design", "build", or "test" ticket:

1. Run the job queue in every environment.
2. Move the nightly stock sync to the queue. Depends on 1.
3. Move abandoned-cart reminders to the queue. Depends on 1.
4. Remove the crontab. Depends on 2 and 3.

Children 2 and 3 do not depend on each other, so neither waits for the other. After you confirm, Ticket publishes them: the epic becomes #30 and the children #31 to #34.

A few sessions later, #31 is closed.

```text
/ticket : select the next ready child of epic #30 on github.
```

Ticket picks #32 and checks it against the code as it is now, not as the ticket describes it. The ticket names a function, `sync_inventory`, that was renamed `sync_stock` last month. Ticket records what the code says as evidence; the ticket's own wording appears only as a quoted, untrusted claim at the end of the scope:

```markdown
## Observable outcome

The nightly stock sync runs as a queued job at the time the crontab sets today, and no longer runs from cron.

## Current evidence

- `deploy/crontab:7` | anchor: `sync_stock` | observation: the sync runs nightly at 03:00 UTC under the name `sync_stock`, not `sync_inventory`.
- `larder/jobs/queue.py:12` | anchor: `enqueue` | observation: the queue that #31 delivered accepts scheduled jobs.

## Protected constraints

- The abandoned-cart entry stays in the crontab until #33 moves it.
```

Later you ask for #34 directly while #33 is still open. Ticket returns `blocked`, names the unmet dependency, and writes no handoff, so nothing is planned against work that does not exist yet.

```text
/blueprint : Plan the ticket scope in .first-four-hours/ticket-scopes/move-stock-sync-to-queue/ticket-scope.md.
```

## You are done when

For a session: Construct's report for its one ticket shows every instruction applied, the plan's verification passed, and the diff matching the plan; you have settled its owner gates; and Assess returns `clear` for the change, after any rework its findings needed. For the whole request: no ticket in it is still open. When `select` finds no ready ticket while some are still open, none of them is ready yet (for example, blocked, waiting on your decision, or in progress), and the request is not done. Closing tickets is your decision.

## If it goes wrong

- `needs-info`: make the human decision it names ([Ticket](../skills/ticket.md)).
- `blocked`: finish the stated blocker first ([Ticket](../skills/ticket.md)).
- `needs-decomposition`: the ticket is not one session's job. Decide whether to persist replacement tickets ([Ticket](../skills/ticket.md)).
- `close-candidate`: the work looks done or obsolete. Decide whether to close it ([Ticket](../skills/ticket.md)).

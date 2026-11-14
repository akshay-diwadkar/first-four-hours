# Work through a large ticket without losing the thread

On Monday the session knew everything. By Thursday a new session asks the questions you answered on Monday, and you answer them again, slightly differently.

Large work spread over several sessions loses the thread: each session rediscovers what was decided, or one session tries everything and stops half-done. `/ticket` splits the work into tickets that each fit one session and keeps their real dependencies. In each session it picks one ready ticket and checks it against the current code before planning.

## Use this when

- A request spans several major changes.
- You have an epic or backlog and want the next ready ticket checked against the current code.
- You keep re-explaining the same decisions to each new session, or after the agent compacts its context.

## Use something else when

- The change fits one session: [Plan a change before your agent starts editing](plan-a-change.md).
- You do not know which skills the work needs: [Find the next step when work spans several skills](find-the-next-skill.md).

## Steps

1. Start `/ticket`'s `persist` effect with the request and a backend, `github` or `local`. It publishes only after you confirm. A local store is committable backlog.
2. At the start of each session, start `/ticket`'s `select` effect for the next ready ticket. A `plan-ready` result seals `ticket-scope.md`.
3. Plan it with `/blueprint` from that scope, and carry it out with `/construct`, as in [Plan a change before your agent starts editing](plan-a-change.md).
4. Review the result as in [Trust a change before you merge it](review-before-merge.md).
5. In the next session, run `select` again. It checks the next ticket against the code as it is now, not against what an earlier session recorded.

## A worked scenario

*Illustrative: FreshCart is a made-up online grocery service, and this is not a recorded run. Excerpts are shortened.*

FreshCart runs its scheduled work from a crontab on one server, and Søren Lindqvist, FreshCart's platform engineer, is the only person who remembers why each line is there. Moving it to a job queue is too big for one session, and too important to leave in one person's head.

```text
/ticket : persist the move of FreshCart's scheduled jobs from one server's crontab to a job queue on github, as tickets a single session can finish.
```

`/ticket` proposes an epic with four children. Each is one complete job that a session can plan, build, review, and rework, rather than a "design", "build", or "test" ticket:

1. Run the job queue in every environment.
2. Move the nightly stock sync to the queue. Depends on 1.
3. Move abandoned-cart reminders to the queue. Depends on 1.
4. Remove the crontab. Depends on 2 and 3.

Children 2 and 3 do not depend on each other, so neither waits for the other. After you confirm, `/ticket` publishes them: the epic becomes #30 and the children #31 to #34.

A few sessions later, #31 is closed.

```text
/ticket : select the next ready child of epic #30 on github.
```

`/ticket` picks #32 and checks it against the code as it is now, not as the ticket describes it. The ticket names a function, `sync_inventory`, that was renamed `sync_stock` last month. `/ticket` records what the code says as evidence; the ticket's own wording appears only as a quoted, untrusted claim at the end of the scope:

```markdown
## Observable outcome

The nightly stock sync runs as a queued job at the time the crontab sets today, and no longer runs from cron.

## Current evidence

- `deploy/crontab:7` | anchor: `sync_stock` | observation: the sync runs nightly at 03:00 UTC under the name `sync_stock`, not `sync_inventory`.
- `freshcart/jobs/queue.py:12` | anchor: `enqueue` | observation: the queue that #31 delivered accepts scheduled jobs.

## Protected constraints

- The abandoned-cart entry stays in the crontab until #33 moves it.
```

Later you ask for #34 directly while #33 is still open. `/ticket` returns `blocked`, names the unmet dependency, and writes no handoff, so nothing is planned against work that does not exist yet. Planned anyway, #34 would have removed the crontab while abandoned-cart reminders still ran from it, and the reminders would have stopped without an error anyone would notice.

```text
/blueprint : Plan the ticket scope in .first-four-hours/ticket-scopes/move-stock-sync-to-queue/ticket-scope.md.
```

## You are done when

For a session: `/construct`'s report for its one ticket shows every instruction applied, the plan's verification passed, and the diff matching the plan; you have settled its owner gates; and `/assess` returns `clear` for the change, after any rework its findings needed. For the whole request: no ticket in it is still open. When `select` finds no ready ticket while some are still open, none of them is ready yet (for example, blocked, waiting on your decision, or in progress), and the request is not done. Closing tickets is your decision.

## If it goes wrong

- `needs-info`: make the human decision it names ([`/ticket`](../skills/ticket.md)).
- `blocked`: finish the stated blocker first ([`/ticket`](../skills/ticket.md)).
- `needs-decomposition`: the ticket is not one session's job. Decide whether to persist replacement tickets ([`/ticket`](../skills/ticket.md)).
- `close-candidate`: the work looks done or obsolete. Decide whether to close it ([`/ticket`](../skills/ticket.md)).

# Agree what a project is for before every session re-argues it

On Monday you agreed the project would not handle delivery. On Wednesday a new session suggests adding delivery "while we're here". On Friday you are not sure what you agreed anymore, and neither is anyone else.

A project that starts from a rough idea gets split into tickets and built before anyone has written down what it is for. Each session then rebuilds the purpose from whatever is in front of it, and settled questions reopen. `/charter` agrees the purpose, scope, and success with you once and records them in one resumable file. `/ticket` splits the agreed scope into session-sized tickets, and each session starts from the next ready ticket instead of from your memory.

## Use this when

- You have an idea for a whole app, project, or large feature, and nobody has agreed what done looks like.
- Sessions keep reopening scope, or you keep retyping the same background at the start of each one.
- A project already exists and you want to state where it is going, with the code as evidence rather than as the answer.

## Use something else when

- The work is one change to existing code: [Plan a change before your agent starts editing](plan-a-change.md).
- The purpose is agreed and the work only needs splitting: [Work through a large ticket without losing the thread](work-through-a-large-ticket.md).
- You have no direction yet and want options compared first: [`/ideate`](../skills/ideate.md). `/charter` can start from the direction you choose.

## Steps

1. Start `/charter` yourself with the rough idea. Only you can start it. It agrees the purpose first, then works through one area at a time with you.
2. Answer its questions. It records each answer with where it came from, keeps open questions with who can settle them, and never records a recommendation or your silence as agreement.
3. Stop when its Authority says `ready`: nothing open blocks splitting the scope into tickets. If it stops at `settling`, the file keeps what was agreed and a later session resumes it.
4. If other clones, worktrees, collaborators, or cloud sessions will do the work, ask `/charter` to publish the charter as one GitHub issue. The local file is ignored by Git and exists only in the working copy that wrote it.
5. Split the agreed scope with `/ticket`'s `persist` effect, then work through it one session at a time, as in [Work through a large ticket without losing the thread](work-through-a-large-ticket.md).

## A worked scenario

*Illustrative: FreshCart is a made-up online grocery service, and this is not a recorded run. Excerpts are shortened.*

Priya Raman, FreshCart's product owner, wants customers to pick up orders from partner stores. Three sessions in, there are two half-built pickup screens, a draft delivery-slot model nobody asked for, and a thread where Mateo Rojas asks whether pickup orders can be paid for at the store. Nobody can say whether any of it is in scope, because the scope was never written down.

```text
/charter : FreshCart wants store pickup: customers order online and collect from a partner store. Three sessions have produced work nobody agreed was in scope. Agree what this project is for, what is out, and what done looks like.
```

`/charter` proposes a purpose and agrees it with Priya before anything else, then works through the areas one at a time: who picks up, which stores, how payment works. Paying at the store depends on checkout work Mateo has not scoped, so it stays an open question with Mateo as its owner instead of becoming a guess. Shortened:

```markdown
## Purpose

FreshCart customers who would rather not wait for delivery can order online and collect from a partner store at a time they choose. Success: a customer chooses a store and a pickup slot at checkout, and the store sees the order before the slot starts. Out of scope: delivery slots, and changes to delivery.

## Agreed

- Payment stays online at checkout, as it is today. [user]
- A pickup slot can be chosen only within a store's opening hours. [confirmed]

## Unsettled

### Open questions

- Can customers pay when they collect at the store? owner: Mateo Rojas
```

The delivery-slot draft is now plainly out of scope, and the question of paying at the store has an owner instead of a recurring debate. With Authority at `ready`, Priya asks `/charter` to publish the charter as a GitHub issue, then splits the agreed scope:

```text
/ticket : persist the scope of the store-pickup charter on github, as tickets a single session can finish.
```

`/ticket` reuses the published issue as the epic. From then on, each session starts with `select`, which picks a ready ticket and checks it against the code as it is now. The shortcut was another session that opened with "where were we?" and an agent happy to guess.

## You are done when

The charter's Authority is `ready`, its agreed scope is split into tickets, and each session starts from a ticket rather than from a retold history. For the project as a whole: no ticket in it is still open.

## If it goes wrong

- `/charter` stops at `settling`: the purpose has no observable success yet, or an open question still blocks splitting the work. Settle it with its named owner and resume ([`/charter`](../skills/charter.md)).
- Publication fails or you do not confirm it: the local file stays the authority ([`/charter`](../skills/charter.md)).
- A session reopens something the charter settled: point it at the charter. If the agreement itself has changed, record it in `/charter` rather than in the session ([`/charter`](../skills/charter.md)).

# Stop rediscovering an unfamiliar codebase

In an unfamiliar project, every session searches for the same files from scratch and chases keyword matches that do not matter. Atlas keeps a small committed map that points agents to the few files worth reading. The files themselves stay the truth.

## Use this when

- Agents keep searching for the same files.
- You want a map created or rebalanced, a broken pointer repaired, or the map audited for drift.

## Use something else when

- You need documentation for people: [Write documentation that matches its sources](write-docs-from-sources.md).
- You need a change planned: [Plan a change before your agent starts editing](plan-a-change.md).

## Steps

1. Start Atlas with `/atlas`, or ask for the map in plain words and the agent starts it.
2. Atlas writes `MAP.md` and pages under `.map/`, checks the hierarchy, and adds a short guidance block to the root `AGENTS.md` and `CLAUDE.md`, creating either file when it is missing. Adding `<!-- OPT-OUT ATLAS -->` to a root file keeps the block out of it.
3. Review and commit the pages. The map is a deliverable, not a handoff.
4. In later sessions, the agent starts from the copy of `MAP.md` in its root guidance, follows only the relevant branches, reads the part of a large file that a pointer names, and reads the current files before deciding.
5. Whoever changes a file that a pointer cites updates that pointer in the same work.

## A worked scenario

*Illustrative: Larder is a made-up project, and this is not a recorded run.*

Every new session on Larder starts the same way: the agent searches for "checkout" and gets matches in templates, analytics events, tests, and an old admin tool, and reads a dozen files before it finds the two that matter.

```text
Map the Larder repository so agents can find the ordering, payment, and customer-message code quickly.
```

Atlas writes a small `MAP.md` with one line per area of the project. The line for ordering says to follow it for checkout, order state, payment calls, and the payment webhook, and leads to the ordering Landmark, a short index of Satellites. From there, the checkout Satellite gives a starting file and a stopping point:

- start with `larder/orders/checkout.py`;
- for payment failures, also read `larder/payments/client.py`;
- for missing or duplicate confirmations, read `larder/payments/webhooks.py`, where the event ID is stored;
- for a checkout fix, these are usually enough.

The pages are short pointers, not explanations of the code, so there is little in them to go stale. In the next session, the agent asked about duplicate confirmations reads `MAP.md`, follows the ordering line to its Landmark and the checkout Satellite, and opens the webhook handler, then reads the current code before deciding anything. When a later change moves that handler, the same change updates the pointer.

## You are done when

`MAP.md` and the `.map/` pages are committed, the hierarchy check reports no problems, and an agent in a new session reaches the files you care about by following the map.

## If it goes wrong

- The hierarchy check reports problems: the agent repairs them and checks again ([Atlas](../skills/atlas.md)).
- The map is stale or missing: it never blocks work. Ask for a repair or a drift audit ([Atlas](../skills/atlas.md)).
- The map disagrees with the files: the files win, so fix the pointer ([Atlas](../skills/atlas.md)).

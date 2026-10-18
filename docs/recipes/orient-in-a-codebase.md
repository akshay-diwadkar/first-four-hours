# Stop rediscovering an unfamiliar codebase

In an unfamiliar project, every session searches for the same files from scratch and chases keyword matches that do not matter. Atlas keeps a small committed map that points agents to the few files worth reading. The files themselves stay the truth.

## Use this when

- Agents keep searching for the same files.
- You want a map created or rebalanced, a broken pointer repaired, or the map audited for drift.

## Use something else when

- You need documentation for people: [Write documentation that matches its sources](write-docs-from-sources.md).
- You need a change planned: [Plan a change before your agent starts editing](plan-a-change.md).

## Steps

1. Ask for the map in plain words. Atlas starts when the agent recognizes the task, not by name.
2. Atlas writes `MAP.md` and pages under `.map/`, checks the hierarchy, and adds a short guidance block to the root `AGENTS.md` and `CLAUDE.md`, creating either file when it is missing. Adding `<!-- OPT-OUT ATLAS -->` to a root file keeps the block out of it.
3. Review and commit the pages. The map is a deliverable, not a handoff.
4. In later sessions, the agent reads `MAP.md`, follows only the relevant branches, and reads the current files before deciding.
5. Whoever changes a file that a pointer cites updates that pointer in the same work.

## Example

For example (illustrative):

```text
Map this repository so agents can find the payment and billing code quickly.
```

## You are done when

`MAP.md` and the `.map/` pages are committed, the hierarchy check reports no problems, and an agent in a new session reaches the files you care about by following the map.

## If it goes wrong

- The hierarchy check reports problems: the agent repairs them and checks again ([Atlas](../skills/atlas.md)).
- The map is stale or missing: it never blocks work. Ask for a repair or a drift audit ([Atlas](../skills/atlas.md)).
- The map disagrees with the files: the files win, so fix the pointer ([Atlas](../skills/atlas.md)).

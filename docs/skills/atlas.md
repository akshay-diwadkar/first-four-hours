# Atlas

Atlas keeps a small navigation wiki in a project so agents find the few files worth reading without searching everything. The wiki is plain Markdown: a tiny `MAP.md` at the root links to `LANDMARK.md` index pages under `.map/`, which link to Satellite pages that say which project file to open first, which others matter for which task, and when a kind of task has read enough. It belongs to the Workbench domain.

## When to use it

- An agent is orienting in an unfamiliar project folder.
- You want to create a map, rebalance one that has grown awkward, repair a broken pointer, or audit whether the map has drifted from the files.

## When to use something else

- To write documentation for people, use [Scribe](scribe.md). Atlas pages are short pointers with a cue, not explanations.
- Atlas only says where to look. The project files are the truth, and a missing or stale map never blocks normal work.

## How to start it

The suite marks Atlas as model-invoked: the agent starts it when a task matches, and it is not meant to be started by name. Ask for the outcome in plain words. For example (illustrative):

```text
Map this repository so agents can find the validation and release code quickly.
```

## What happens

To navigate, the agent reads `MAP.md`, follows only the branches whose cues match the task, opens the file a Satellite marks as its start, and then reads the current project files before deciding anything. A Satellite's stopping point is a hint; the files still decide what the task needs. To author or rebalance, Atlas writes the wiki pages and validates the hierarchy with a read-only check. Authoring finishes by adding one short guidance block to the root `AGENTS.md` and `CLAUDE.md`, creating either file when it is missing, so other agents find the map.

## What you get

Committed wiki pages: `MAP.md` and the pages under `.map/`. The wiki is a deliverable, not a handoff, so Git does not ignore it. To keep the guidance block out of a root file, add `<!-- OPT-OUT ATLAS -->` to that file yourself.

## When it stops

The hierarchy check reports structural, reachability, link-safety, and portability problems for the agent to repair.

## Related skills

When work moves, renames, deletes, or changes the meaning of a file that a pointer cites, the agent doing that work updates the pointer in the same work. [Construct](construct.md) repairs links to files its plan deletes. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Atlas's contract](../../skills/workbench/atlas/SKILL.md)

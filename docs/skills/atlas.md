# Atlas

Atlas keeps a small navigation wiki in a project so agents find the few files worth reading without searching everything. The wiki is plain Markdown: a short Map in the root `AGENTS.md` and `CLAUDE.md` links to `LANDMARK.md` index pages under `.map/`, which link to Satellite pages that say which project file to open first, which others matter for which task, and when a kind of task has read enough. It belongs to the Workbench domain.

## When to use it

- An agent is orienting in an unfamiliar project folder.
- You want to create a map, rebalance one that has grown awkward, repair a broken pointer, or audit whether the map has drifted from the files.

## When to use something else

- To write documentation for people, use [Scribe](scribe.md). Atlas pages are short pointers with a cue, not explanations.
- Atlas only says where to look. The project files are the truth, and a missing or stale map never blocks normal work.

## How to start it

Start it yourself with `/atlas`, or the agent may start it when your request matches. For example (illustrative):

```text
/atlas : Map this repository so agents can find the validation and release code quickly.
```

## What happens

To navigate, the agent starts from the Map in its root guidance, follows only the branches whose cues match the task, and opens the file a Satellite marks as its start. For a large file, the pointer names a heading or a symbol, so the agent reads that part first and widens only when it needs more. It then reads the current project files before deciding anything. A Satellite's stopping point is a hint; the files still decide what the task needs. To author or rebalance, Atlas writes the wiki pages and validates the hierarchy with a read-only check, which also confirms that each named heading and symbol still exists. Authoring finishes by writing the Map as one guidance block in the root `AGENTS.md` and `CLAUDE.md`, creating either file when it is missing, so other agents find the wiki. The Map lists each top-level Landmark, with its title as the link and its opening paragraph as the cue, so it changes only when those do; the check reports a Map block that is missing or no longer matches them until the guidance is set up again.

## What you get

Committed wiki pages under `.map/`, and the Map block in the root `AGENTS.md` and `CLAUDE.md`. The wiki is a deliverable, not a handoff, so Git does not ignore it. To keep the guidance block out of a root file, add `<!-- OPT-OUT ATLAS -->` to that file yourself; without it, the check reports a removed block as missing.

## When it stops

The hierarchy check reports structural, reachability, link-safety, and portability problems, a top-level Landmark whose title or opening paragraph cannot appear in the Map, a heading or symbol a pointer names that its file no longer has, and a root Map block that is missing, unreadable, or no longer matches the top-level Landmarks, for the agent to repair.

## Why it's built this way

**The failure it prevents.** In an unfamiliar project, every session pays again to find the same files, and keyword searches return many matches that do not matter. Effort spent searching is effort not spent deciding. Atlas points agents at the few files worth reading, and at relationships a filename search would miss, so that relevant context is easy to find. Better plans with less effort is the design goal, not a measured result.

**What it refuses, and why.** It does not explain or copy the code. A page is a pointer with a short cue, not a narrative, because a copy goes stale and then misleads. The project files stay the truth: a missing or stale map never blocks work, and an agent always reads the current files before it decides anything.

**Floor and ceiling.** A weaker agent gets a short path from the Map through a Landmark and a Satellite to the right file, with a hint about when a task has read enough. A stronger agent treats the map as a starting point, not a fence, and explores further when the task needs it.

## Related skills

When work moves, renames, deletes, or changes the meaning of a file that a pointer cites, the agent doing that work updates the pointer in the same work. An agent whose work edits files also fixes a map cue that misled it, so small `.map/` edits can appear in a pull request about something else. [Construct](construct.md) only repairs links to files its plan deletes. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Atlas's contract](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/atlas/SKILL.md)

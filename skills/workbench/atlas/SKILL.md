---
name: atlas
description: Navigate, author, rebalance, validate, or maintain a project's filesystem-native Map/Landmark/Satellite orientation wiki over eligible project files. Use for unfamiliar project-folder orientation, initial mapping, a hierarchy defect, pointer upkeep, or a freshness drift audit; underlying project files remain truth and missing Atlas state never blocks normal work.
metadata:
  version: "1.1.0"
---

# Atlas

Use Atlas as optional project-folder orientation. Underlying project files are authoritative; expand exploration as evidence requires.

When Atlas work is the user's whole request, end with one optional next step fitting this outcome: a fenced, self-contained prompt naming any repository, issue, PR, or artifact it needs, or say none is needed. Only a "yes" starts it, via any skill it names, but the user runs a `charter`, `diagnose`, or `ticket` step as its `/<skill>` command.

Invoke commands as `python <skill>/scripts/cli.py --repo-root <root> --format json [--input name=value ...] <command>`; `doctor` returns the next command.

## Navigate an existing wiki

1. Start from root guidance's `MAP.md` copy, else read `MAP.md`.
2. Follow only cue-matching links, batching each level's reads into one turn: a Satellite's start target first, a cross-link only when the task crosses its boundary.
3. Read a link's heading section or named symbol's definition with a bounded read; widen only if insufficient.
4. When no cue fits, routes compete, or an entrypoint proves unproductive, reconsider the route or search natively; never hunt through the whole wiki. If your work edits files, fix the misleading cue unless your skill limits Atlas upkeep.
5. Inspect current project files before making claims or decisions.

## Author or rebalance

Before changing wiki structure, read [information architecture](references/information-architecture.md) for roles, cues, and links, and [authoring and rebalancing](references/authoring-and-rebalancing.md) for mapping and completion.

## Validate the hierarchy

The command is read-only. After edits, run `run` and repair every diagnostic. Counts are review signals.

## Keep pointers current

When your work moves, renames, deletes, or changes the meaning of a file or symbol, update each pointer a `.map/` search for it finds in the same work; never walk the wiki or remap unrelated areas. This needs no freshness cycle. For a deliberate drift audit, read [freshness and maintenance](references/freshness-and-maintenance.md).

## Install project-folder guidance

Agents discover the map only through root guidance, so authoring, rebalancing, and `MAP.md` edits finish with `setup-guidance`; it validates the hierarchy and maintains one block holding `MAP.md`'s body in root `AGENTS.md` and `CLAUDE.md`, creating either when missing. Only the user adds `<!-- OPT-OUT ATLAS -->`; `remove-guidance` runs only on explicit request.

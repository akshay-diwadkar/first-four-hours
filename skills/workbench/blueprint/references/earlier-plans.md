# Earlier plans

Read this before reusing a sealed plan, replanning, amending after a Construct stop, or changing a workspace's request.

## Commands

For a replan, `carryover` reports an earlier sealed plan's bound files, writing nothing and refusing an edited plan:

```bash
python scripts/cli.py --repo-root /absolute/repo --input predecessor_file=/absolute/earlier/blueprint.md --format json carryover
```

`result.entries` gives each Source's and existing or deleted Location's `path`, `role`, and `status`: `unchanged`, `changed`, or `missing`.

To amend after a Construct stop, add `--predecessor /absolute/stopped/blueprint.md` to the [README](../README.md) preparation, with the same task name. It refuses an edited or unbound plan, reserves a fresh task directory even when the request is unchanged, starts its draft as the stopped plan without receipts, and returns the same entries as `carryover`. It reuses a directory only while its draft is absent or still exactly that seed, so no sealed plan is reopened, and a draft already edited leads to another fresh directory. Every earlier workspace stays unchanged. One task name holds at most six workspaces for the same request; past that, use another task name.

To change the request, write the amended request outside the repository and rerun preparation with `--amend /absolute/repo/.first-four-hours/blueprints/<task-slug>/blueprint.md`, the path preparation returned. It replaces that workspace's `request.md` in place and turns a sealed plan back into a draft to repair and reseal. Once a bound file's bytes changed or a planned-new Location exists, Construct may have started, so it refuses with `workspace.amend.progressed` and only a fresh workspace remains.

## Reuse

Amend a stopped plan by preparing with `--predecessor`: edit only what the stop evidence and applied work change, restating applied instructions as Current State. A seal proves shape, not review acceptance: re-derive every premise you keep, except facts read only from files `carryover` reports `unchanged`, never its probes, measurements, or disputed facts.

An amendment after a `verification.mutated_workspace` stop cites the stopped command and summarizes `changed_paths`, `index_changed`, and `head_changed`, proving writes but not their full surface or writer; it reshapes each writing command, inventorying no writes, never calls that command pure, and names any other writer to drop or state as a limitation.

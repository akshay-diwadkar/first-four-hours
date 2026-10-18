# Persist tickets

Persist turns the current user request — or one authoritative upstream artifact the user supplied or explicitly selected — into work-item meaning for exactly one explicit backend.

## Authority

A direct current user request is sufficient persist authority. Never require a diagnosis, architecture decision, scope artifact, or other lifecycle predecessor merely to create a ticket. Preserve only the upstream artifact's settled work-item meaning: observable outcome, material constraints or settled decisions, relevant evidence or acceptance truth, real dependency or readiness facts. Never copy the artifact wholesale or replay its reasoning. A sealed `blueprint.md` is Construct's planning authority, never persist input; persisting from it would loop back through Blueprint.

## Shape

Every work item is one complete job: an agent can carry it through planning, implementation, review, and any needed rework in one useful work session. Never persist a lifecycle phase, such as planning, building, or review, as its own work item.

Choose `single` or `epic`; `single` is the default: one implementation work item, no epic. An epic is coordination-only, for 2+ direct implementation children that are independently useful merge/review units. Split when the request does not fit one session as one complete job, or when splitting materially improves dependency sequencing, safe parallel execution, ownership/review boundaries, rollback/migration isolation, or bisectability; each child is then itself a complete session-sized job. Session fit is a decomposition test, not an estimate to record: a job that already fits one session splits only when splitting materially improves one of the outcomes listed above, never for size alone. Never split by file count, layer symmetry, or roadmap manufacture, and never infer boundaries from Blueprint Implementation steps, Locations, files, or layers. Children inherit shared meaning where unambiguous; membership is not dependency; declaration order is not scheduling; dependencies name only real prerequisites, so unrelated children stay unordered; no nested epics.

## Work-item meaning

Each work item lets a fresh agent finish it without reconstructing the whole request or upstream artifact, carrying only what downstream planning cannot safely rediscover: the relevant context and an observable bounded outcome with checkable completion; the source binding when authority exceeds the request; material constraints or settled decisions when any exist; real blockers/dependencies when any exist. Do not add implementation mechanism, edit-file lists, PR rationale, rollout/recovery, test commands, or validation plans — those belong to `blueprint`. Carry an external acceptance constraint only when it is genuinely part of the work item; never invent verification detail for completeness.

## Input

Author the persist meaning as one JSON object and pass it to `start` as `persist_input`:

- `backend`: `github` or `local`. With `github`, also `github_repo_url` as `owner/repo`; with `local`, also `local_store` and, for an epic, `epic_id` ([Local persist](persist-local.md) owns their rules).
- `shape`: `single` (exactly one work item) or `epic` (two or more).
- `task`: an object whose `text` is the shared request; it titles an epic root.
- `work_items`: one object per item with a unique `id`, an `outcome`, and optional `dependencies` listing other ids in this package.
- `authority_source`: only when authority is not the bare request: `{"type": "artifact", "reference": ...}` for a supplied upstream artifact.

`outcome` becomes the work item's title (whitespace collapsed), so state it as one short observable result. Every other key on a work item renders as its own `## Heading` section of that item's body, so give each work item its checkable completion as `completion`, plus any material meaning from above, such as `context` or `constraints`. Keys on `task` render only on an epic root or a single ticket, and `dependencies` name only items in this package, so put each blocker outside this package in the `blockers` string of every work item it gates, one line per blocker. With `backend=github`, write an issue in the same repository as `Blocked by: #N`; select reads it as a real dependency that clears only when #N closes as completed, and otherwise a person edits or removes it. Write every other blocker, including every local blocker and any issue in another repository, as a plain line naming what must happen first; a person clears it by editing or removing that line. Only work-item meaning enters `persist_input`; reasoning stays ephemeral.

The flow also takes `--input` values that must match the JSON: `backend` on every command and, with `github`, `github_repo_url`. Labels go only through the repeatable `label` input, never as JSON keys; a local run takes neither `label` nor `github_repo_url`.

## Backend

A backend named in the request is authority; an ambiguous, underivable choice goes through the shared `reason` ask contract. Backend failure never triggers fallback, mirroring, or mode switching.

## Package and preview

Keep one logical package meaning. Do not create a durable package artifact. Derive the preview from that same meaning — never author it independently. Persist ends at publication: selecting work and writing `ticket-scope.md` belong to select.

## Flow

Run the stateful persist flow through `scripts/cli.py`; its root manifest owns `start`, preview review, backend reconciliation, and the confirmed publish transition. `start` validates `persist_input` and derives `preview.json`; repair each diagnostic in the input and start again. With `backend=github`, `reconcile` must reach `ready` before publication review; with `backend=local`, `reconcile` plans against the store as described in [Local persist](persist-local.md). Publication runs only after `publish_confirmation=yes`, supplied to the flow's `next` command from publication review; a confirmation supplied earlier blocks `reconcile` and requires a new run. Never improvise publication outside the flow.

Persist is complete when publication returns `status` `complete` and `publication-result.json` names every published work item; report that result. Any other outcome is a stop: present the recorded state, or the stop's diagnostic when no result was written, and follow the resume guidance in [GitHub persist](persist-github.md) or [Local persist](persist-local.md).

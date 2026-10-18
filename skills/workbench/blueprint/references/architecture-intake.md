# Architecture intake

Architect's settled decisions are upstream authority; Blueprint owns implementation planning.

## Verify, then reuse

Require receipt-valid `.first-four-hours/architectures/<slug>/architecture.md` in the target repository: a current snapshot whose `scope_version` shares Architect's major, evidence hashes, primary identity. Preparation verifies before writes; sealing and fresh intake recheck. Bad, stale, or ambiguous input returns to Architect; never repair receipts. Reseal to recover.

Receipt validity does not establish semantic actionability. Before preparing a workspace, require a concrete settled target and no blocking architecture unknown or unresolved user policy. Stop on no-design-change without planning when relying on architecture for the target; with an authoritative request supplying an independent concrete target referencing settled no-design-change authority, proceed. Genuine contradictions return to Architect.

Reuse settled owner/boundary, decisions, evidence, invariants and constraints, consequences, earned tradeoffs and discriminators, and user-owned policy before opening a fact or question branch. Do not replay reconnaissance, architecture falsification, or settled tradeoffs; do not ask for reconfirmation or require absent reasoning history. Equivalent settled authority preserves equivalent downstream obligations; implementation order may differ.

For a new implementation fact, follow the [exploration envelope](delegation-protocol.md): upstream evidence first, then one bounded delegated or local question. New implementation-level user-owned blockers stay Blueprint-owned under intent closure. Ordinary implementation choices stay agent-owned.

## Freeze and translate

Prepare from verified architecture.md with the README command; its exact bytes become the canonical request.md sibling. Architect never authors this workspace.

When a new implementation answer changes request meaning, freeze resolved request prose with one source declaration:

```text
<!-- architecture-source: {"path":"/absolute/repo/.first-four-hours/architectures/<slug>/architecture.md","sha256":"EXACT_FILE_SHA256"} -->
```

Compute the digest from verified file bytes. Preparation and sealing check the referenced artifact and digest. A changed source needs a fresh request; never refresh the hash silently. No extra artifact or proof-binding field is created.

Carry structural intent, mechanism facts, protected behavior, accepted consequences, and authoritative evidence into Goal and Current State. Implementation chooses the owner and seam realizing the architecture. Derive affected consumers from the architecture; its paths and views are non-exhaustive bearings, never automatic edit scope.

Do not copy architecture prose wholesale, create mapping artifacts, restore historical fields, or persist temporary reasoning. Every material imported invariant, constraint, and policy must survive the requirement trace in [requirement trace](challenge-and-rehearsal.md#requirement-trace) as an observable completion condition or an explicit preservation disposition in the ordinary fields; omission or weakening blocks seal. Scripts verify bytes, shape, and evidence, not semantic completeness.

## Stop and lifetime

Seal the Blueprint and stop after sealing. Construct is a separate workflow; Architect cannot route directly to it.

Safe `.first-four-hours/blueprints/` planning files and sealed `.first-four-hours/architectures/` handoffs are excluded from architecture snapshots and cannot supply architecture evidence. Foreign, tracked, or symlinked namespace content fails closed. Repository and evidence changes invalidate fresh intake. Displaced envelopes never become generic.

Once Blueprint seals, the bound Blueprint/request/proof identity owns progress. Cold or warm resume does not reopen the architecture handoff. Upstream architecture availability is required only during preparation and sealing.

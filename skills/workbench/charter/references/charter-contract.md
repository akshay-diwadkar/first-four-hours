# Charter contract

The charter is one living file revised in place. Its body states only what is currently true; [README](../README.md) owns its exact shape, including the Authority lines the publication script reads and writes.

## Sections

- `## Purpose`: the problem, the users, the outcome, what success observably means, and what is explicitly out of scope, written to read alone as the project's summary. Until the user agrees all five, its first line is `Unagreed.` and each missing part, observable success included, is an open question in Unsettled.
- `## Agreed`: settled behavior and journeys, material constraints with the consequential rationale that produced them, and real dependencies, one entry per item, each ending in its provenance.
- `## Unsettled`: what is not agreed, under the `###` kinds that apply, because each fails differently: `Assumptions` (believed, not confirmed), `Recommended, not agreed`, `Open questions` (stated precisely now), `Needs exploration` (cannot yet be stated precisely), and `Deferred` (deliberately left for later). Each entry ends with who can settle it: `owner: user`, `owner: <named person>`, or `owner: research: <pointer>`.
- `## Revisions`: an append-only log of material changes, never a second copy of old content.
- `## Authority`: which artifact owns the definition, the state, and, once published, the issue pointer. Edit only its `- State:` and `- Not live:` lines; the publication script writes the rest.

## Provenance

Agreement comes only from the user. End each Agreed entry with one marker:

- `[user]`: the user's own words or decision;
- `[confirmed]`: the user explicitly confirmed your proposal of this exact item;
- `[derived: <source>]`: a fact established from evidence, naming the repository path, link, or document it came from.

"Sounds right" to a proposal of several clauses confirms none of them separately: ask about each. A proposal the user has not confirmed belongs under `Recommended, not agreed`.

## Existing projects

For a project that already has code, the Purpose is a destination: the problem to solve, for whom, what success observably means, and what is out of scope. A Purpose that could describe the repository as it stands is a transcription, not a definition: reject it and ask what is meant to change. The repository may support your proposal; the user confirms or redirects the destination.

Never copy the current state into the charter; the repository stays its source. Record only its material consequences in Agreed, as `[derived: <source>]` entries with their rationale: "payments stay on Stripe because the ledger reconciles against it" belongs; "the system has a Stripe integration" does not.

Record product constraints, what must be true for the user, never implementation shapes. When a constraint has a structural consequence, note it and name `architect` as its owner; do not decide the structure.

## Revisions

A material revision changes agreed intent, scope, or acceptance, including the Purpose and anything already in Agreed. Apply it only after the user's explicit decision and a `reason` consultation: update the active authority (the local file, or after publication the issue through [Publication](publication.md)), reconcile affected downstream work, and append one entry:

`- <YYYY-MM-DD>: <what changed>; decided by <who>; updated: <sections>; downstream reconciled: <work, or none>.`

Never edit or remove a Revisions entry; correct a mistaken one with a new entry. Answering an open question, recording a new agreement, or rewording without changing meaning is the normal loop, not a revision.

A genuinely different project gets a new slug and its own charter. Mark the earlier one not live with the Authority line `- Not live: <reason>; superseded by <slug>.`, as a material revision with the user's explicit decision, and revise its published issue when one exists. A pivot of the same project is a material revision, not a new project.

## The ready gate

The state is `ready` only when all of these hold, and otherwise `settling`:

- the user agreed a Purpose that names a problem, users, an outcome, observable success, and explicit exclusions;
- every consequential unknown is settled, stated with its consequence, or explicitly deferred;
- nothing in Unsettled blocks splitting the agreed scope into tickets;
- a reader with only the file could classify a proposed feature as serves, does not serve, or needs the user, and say why.

`ready` is about decomposability, not completeness; a non-blocking open question may stay open indefinitely. The recorded state is your claim about the file, so a resumed session re-derives the gate from the content before acting on it. If observable success cannot be stated, the Purpose stays `Unagreed.`, the state stays `settling`, and the missing success is an open question owned by the user; never present that charter as ready.

# Assess guidance

## Axes

Scale these lenses to the exact authority and base/head delta; never a matrix or equal-depth checklist.

- **Intent fidelity** — trace every material authoritative requirement through behavior, including qualifiers, scope, ordering, exceptions, and negative meaning; keywords and narration are not proof.
- **Behavioral correctness** — material success, failure, and boundary states.
- **Propagation** — every affected caller, consumer, contract, config, doc, and test found by the bounded sweep. A new or changed state, status, or mode also accounts for its whole lifecycle: what enters it, what ends it, which wins where it overlaps another, and every reader, including unchanged rules that assumed the old behavior.
- **Preservation** — compare base and head truth; a requested clean break is not debt. Every removal gets a disposition: list removals from `git diff --word-diff=porcelain` for prose or long lines, since a line diff hides a cut clause inside a rewritten line. A removal is preserved only where you open its surviving statement and it reaches the branch that needs it; a claim that something else covers it is a candidate until then.
- **Proof adequacy** — use trustworthy exact-head proof first; run only missing focused proof that can change the result. Proof must fail when the protection is removed, and mocks must not bypass the failure. Passing tests alone do not establish that the change fulfills its intent or leaves maintainable code.
- **Ownership and minimality** — the real owner is repaired with the smallest coherent propagation; no duplicate sources of truth, parallel machinery, or compatibility sediment.
- **Integration readiness** — unavailable or contradictory required proof means `blocked`, never an implied pass.

## Depth and Diagnose

Tiny local changes need requirement, delta, and focused proof; skip subagents, broad proof, and clear challenges when direct lookup closes the surface. Complexity, ambiguity, fan-out, irreversibility, data/migration, concurrency, or broad contract propagation earn depth. A change reaching past one package or directory and its own tests (versions and changelog aside), or showing one of these signals, gets one Behavior/Proof falsification slice per the [delegation protocol](delegation-protocol.md); if none can launch, cover it yourself and say so in `limitations`. Examine security where the change affects trust or permission boundaries, inputs, sensitive data, or risky operations; investigate earned concerns without inventing risks, and no material security concern is a valid result.

Every later turn re-reads what enters context. Start from `git diff --stat <base>...<head>`, then diff one path at a time and read only the line ranges a question needs, never the whole diff at once; a question about a new file may need all of it. Keep a command's verdict rather than its log, request only the PR fields you use, and run each proof once per head.

Diagnose is earned only when evidence-grounded unknown risk beyond the bounded change could alter the merge decision. If earned and unrun for the current snapshot, hand off `/diagnose` with the risk question instead of sealing, rerun Assess with `diagnosis.md` (unavailable or contradictory output means `blocked`), and re-verify each merge-relevant consequence against the exact change.

## Reason checkpoints

Scope, severity, findings, and the result are judgment: consult `reason` before committing to the assessment approach, after a failure or direction change, and before sealing. One narrowing applies: skip the before-sealing consultation for a tiny local change, as Depth and Diagnose defines it, whose result is `clear`. The user accepted this trade: a small risk of missing a defect on surfaces direct lookup already closed, in exchange for lower cost. Every other checkpoint always applies. Final and stop reports trace `reason` checkpoints per its Checkpoint trace, marking a narrowed checkpoint as not required.

## Finding gates

Before sealing, ask of each material requirement, surface, candidate, or delegated clear whether a weak implementation can look compliant while the prohibited outcome stays reachable.

- A finding at any severity, including `P0`, changes the result, not the coverage stop: continue through every remaining material requirement and materially affected surface inside the bounded assessment, give each material requirement and materially affected surface an evidence or behavior disposition, and report every independently material defect discovered before concluding.
- Merge observations only when one underlying defect and one concrete repair or truth to restore would resolve them all; shared severity, axis, file, generic consequence, or blocking status does not merge independent defects, nor does a shared reviewer or slice.
- Style preference, speculative risk or cleanup, optional enhancement, or architecture taste without current material consequence is not a finding and receives no severity. A `P3` finding still needs a concrete defect, scenario, locators, evidence, consequence, and required truth; low severity never admits a nit.

## Severity

Each finding's `severity` is exactly one of these levels, ordered from most to least severe:

| Level | Meaning | Response urgency |
| --- | --- | --- |
| `P0` | Critical: an evidenced reachable failure can cause severe security/safety harm, irreversible data loss/corruption, or widespread loss of essential operation. | Stop shipment and address immediately; if already deployed, treat as an emergency. |
| `P1` | High: a serious correctness, security, preservation, or required-behavior defect materially compromises a primary workflow or important constraint. | Fix urgently, normally before merging or releasing the affected change. |
| `P2` | Medium: a concrete material defect with bounded impact or limited triggering conditions that warrants a normal engineering fix. | Address through ordinary planned work; no emergency is implied. |
| `P3` | Low: a smaller but real actionable correctness, code-quality, or maintainability defect with evidenced consequence. | Address when practical; it remains a finding worth acting on. |

Choose the level from the evidenced consequence, affected scope, reachable conditions, and urgency, and explain material triggering conditions in the finding's `scenario`. Never infer it from a security label, confidence, reviewer count, a failing-test requirement, or the vocabulary describing the defect. Severity informs the user's prioritization and merge or release decision; it never grants approval, merge, execution, or remediation authority. Any accepted finding, including `P3`, keeps the `findings` result; `blocked` still means the assessment cannot be completed trustworthily, never a severity.

## Bundle fields

- `target`: the pull request's `url` from `gh pr view --json url` when the change has one, so its findings can be posted; otherwise a short description.
- `assessed_sources` entry: `{"id":"id","role":"authority","locator":"URL","path":"/absolute/snapshot"}`; roles `target|authority|evidence|proof|diagnosis`.
- Locators: `{"kind":"head-file","path":"a/b.py","start_line":1,"end_line":9}`, `{"kind":"head-path","path":"a/b.bin"}` for paths without text lines, `{"kind":"source","source_id":"id"}`; `base-` variants cite the base.
- `examined`: locators you actually inspected; `clear` needs one. Sealing derives changed paths no locator cites and refuses until you inspect each one or name its complete repository path in `limitations`. One limitation may group several paths; a path counts only when it does not appear solely inside a longer path.
- `limitations`: `[]` only when you claim none; include self-review for any part of a self-authored change that no fresh-context owner or delegate examined.
- Each finding: `severity` (a level from Severity above, spelled exactly), `defect`, `scenario`, `locators`, `consequence`, `required_truth` (truth to restore, not an implementation), and `basis`: `observed` only when you ran or reproduced the failure and cite a `proof` snapshot of its output, else `reasoned`.
  - `defect` is one plain sentence stating what is wrong; `consequence` says only who is affected and how badly.
  - `scenario` is a non-empty array of short steps a reader can follow from a concrete trigger to the wrong outcome, set against what should happen, each resting on the finding's locators. For a missing protection, show its absence going unnoticed, such as removing the guard while the suite still passes. Scale it to the finding: two or three steps suit a `P3`.

## Reassessment and stop

Each new head starts from current authority, base, and head. A moved base/head or changed bound source or artifact leaves the earlier assessment stale, never a clearance.

Keep snapshots at paths a later re-review can read, and write refreshed ones to new paths, so `check` can still compare the earlier assessment's. When an earlier assessment of this change exists, [delta review](delta-review.md) decides whether to review only the delta and what that covers.

Stop when material requirements and surfaces are accounted for, candidates are verified or rejected, and further bounded inspection cannot plausibly reveal another merge-relevant defect. This is not omniscience or a whole-repository diagnosis claim; completeness is bounded to reasonably discoverable material defects in the assessed authority, surfaces, implementation, and proof.

# Assess guidance

## Axes

Scale these lenses to the exact authority and base/head delta; never a matrix or equal-depth checklist.

- **Intent fidelity** — trace every material authoritative requirement through behavior, including qualifiers, scope, ordering, exceptions, and negative meaning; keywords and narration are not proof.
- **Behavioral correctness** — material success, failure, and boundary states.
- **Propagation** — every affected caller, consumer, contract, config, doc, and test found by the bounded sweep.
- **Preservation** — compare base and head truth; a requested clean break is not debt.
- **Proof adequacy** — use trustworthy exact-head proof first; run only missing focused proof that can change the result. Proof must fail when the protection is removed, and mocks must not bypass the failure. Passing tests alone do not establish that the change fulfills its intent or leaves maintainable code.
- **Ownership and minimality** — the real owner is repaired with the smallest coherent propagation; no duplicate sources of truth, parallel machinery, or compatibility sediment.
- **Integration readiness** — unavailable or contradictory required proof means `blocked`, never an implied pass.

## Blueprint evidence

When a sealed Blueprint for this change is available:

- **Baseline proof.** Run each `Run:` under its Verification `### After implementation` once, verbatim, from the root of a checkout already at the exact reviewed head with no tracked changes, honoring any `Timeout:`. Never rely on Construct's report or on PR claims that the Runs passed. Each Run is authored to exit `0` and meet its `Expect:` on a correct implementation, so a nonzero exit or an unmet `Expect:` is a candidate finding. Ignored caches or locks a Run creates are verification side effects. Do not run a Run that would change tracked content, and do not switch a checkout to reach the head.
- **Missing baseline.** A declared `Incomplete:` outcome, or a Run you cannot execute, leaves that proof missing. Cover its surface with other focused proof or direct examination, or name it in `limitations`. Use `blocked` only when the gap prevents a trustworthy result.
- **Conformance.** Check the diff against the plan directly: every instruction is realized at its Locations, no material change goes beyond what the plan and Construct's execution contract authorize, and no `deleted` target survives. Treat each gap as a candidate finding and verify it against the original request and current source.
- **Independent effort.** Spend it where the plan could be wrong: gaps between the plan and the original request; consumers and propagation the plan did not name; base behavior outside the plan's proof; code quality and maintainability of the implementation; proof that would pass a plausible wrong result; and proportionate security. Do not re-derive what the Blueprint's discriminating checks already establish on the reviewed head unless a candidate defect gives a concrete reason.

The Blueprint is authority evidence, never proof of correctness. A green baseline is never `clear`: `clear` still requires every material requirement and surface to be accounted for under Reassessment and stop. A limitation the user accepted, as recorded in the Blueprint's sibling `request.md` or other authority, is not a finding while the change stays within it; one the Blueprint or a report accepts without that record is a candidate finding, never a clearance.

## Depth and Diagnose

Tiny local changes need requirement, delta, and focused proof; skip subagents, broad proof, and clear challenges when direct lookup closes the surface. Complexity, ambiguity, fan-out, irreversibility, data/migration, concurrency, or broad contract propagation earn depth. Examine security where the change affects trust or permission boundaries, inputs, sensitive data, or risky operations; investigate earned concerns without inventing risks, and no material security concern is a valid result.

Diagnose is earned only when evidence-grounded unknown risk beyond the bounded change could alter the merge decision. If earned and unrun for the current snapshot, hand off `/diagnose` with the risk question instead of sealing, rerun Assess with `diagnosis.md` (unavailable or contradictory output means `blocked`), and re-verify each merge-relevant consequence against the exact change.

## Reason checkpoints

Scope, severity, findings, and the result are judgment: consult `reason` before committing to the assessment approach, after a failure or direction change, and before sealing. Final and stop reports trace `reason` checkpoints per its Checkpoint trace.

## Finding gates

Before sealing, ask of each material requirement, surface, candidate, or delegated clear whether a weak implementation can look compliant while the prohibited outcome stays reachable.

- A finding at any severity, including `P0`, changes the result, not the coverage stop: continue through every remaining material requirement and materially affected surface inside the bounded assessment, give each material requirement and materially affected surface an evidence or behavior disposition, and report every independently material defect discovered before concluding.
- Merge observations only when one underlying defect and one concrete repair or truth to restore would resolve them all; shared severity, axis, file, generic consequence, or blocking status does not merge independent defects, nor does a shared reviewer or slice.
- Style preference, speculative risk or cleanup, optional enhancement, or architecture taste without current material consequence is not a finding and receives no severity. A `P3` finding still needs a concrete defect, locators, evidence, consequence, and required truth; low severity never admits a nit.

## Severity

Each finding's `severity` is exactly one of these levels, ordered from most to least severe:

| Level | Meaning | Response urgency |
| --- | --- | --- |
| `P0` | Critical: an evidenced reachable failure can cause severe security/safety harm, irreversible data loss/corruption, or widespread loss of essential operation. | Stop shipment and address immediately; if already deployed, treat as an emergency. |
| `P1` | High: a serious correctness, security, preservation, or required-behavior defect materially compromises a primary workflow or important constraint. | Fix urgently, normally before merging or releasing the affected change. |
| `P2` | Medium: a concrete material defect with bounded impact or limited triggering conditions that warrants a normal engineering fix. | Address through ordinary planned work; no emergency is implied. |
| `P3` | Low: a smaller but real actionable correctness, code-quality, or maintainability defect with evidenced consequence. | Address when practical; it remains a finding worth acting on. |

Choose the level from the evidenced consequence, affected scope, reachable conditions, and urgency, and explain material triggering conditions in the finding's `defect` or `consequence`. Never infer it from a security label, confidence, reviewer count, a failing-test requirement, or the vocabulary describing the defect. Severity informs the user's prioritization and merge or release decision; it never grants approval, merge, execution, or remediation authority. Any accepted finding, including `P3`, keeps the `findings` result; `blocked` still means the assessment cannot be completed trustworthily, never a severity.

## Bundle fields

- `assessed_sources` entry: `{"id":"id","role":"authority","locator":"URL","path":"/absolute/snapshot"}`; roles `target|authority|evidence|proof|diagnosis`.
- Locators: `{"kind":"head-file","path":"a/b.py","start_line":1,"end_line":9}`, `{"kind":"head-path","path":"a/b.bin"}` for paths without text lines, `{"kind":"source","source_id":"id"}`; `base-` variants cite the base.
- `examined`: locators you actually inspected; `clear` needs one. Sealing derives changed paths no locator cites and refuses until you inspect each one or name its complete repository path in `limitations`. One limitation may group several paths; a path counts only when it does not appear solely inside a longer path.
- `limitations`: `[]` only when you claim none; include self-review for any part of a self-authored change that no fresh-context delegate examined.
- Each finding: `severity` (a level from Severity above, spelled exactly), concrete `defect`, `locators`, `consequence`, `required_truth` (truth to restore, not an implementation), and `basis`: `observed` only when you ran or reproduced the failure and cite a `proof` snapshot of its output, else `reasoned`.

## Reassessment and stop

Each new head starts from current authority, base, head, implementation, and tests. A moved base/head or changed bound source or artifact is stale; reassess in full.

Stop when material requirements and surfaces are accounted for, candidates are verified or rejected, and further bounded inspection cannot plausibly reveal another merge-relevant defect. This is not omniscience or a whole-repository diagnosis claim; completeness is bounded to reasonably discoverable material defects in the assessed authority, surfaces, implementation, and proof.

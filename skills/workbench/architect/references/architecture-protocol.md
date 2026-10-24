# Architecture Protocol

Complete these gates in order. Keep notes internal; `architecture.md` is the sole primary artifact.

**Shared vocabulary**

| Term | Meaning |
|---|---|
| Owner | Repository area responsible for a decision and its invariants. |
| Boundary | Point where responsibility or representation changes. |
| Contract | Caller-visible inputs, outputs, errors, and semantics that must remain stable. |
| Invariant | A condition the selected structure must preserve. |
| Constraint | A repository, runtime, compatibility, operations, ownership, cost, SLO, or risk limit that materially shapes the design. |
| Consequence | A material effect accepted with the selected architecture. |
| Discriminator | The fact or policy that made one materially distinct option win. |
| View | A diagram, contract excerpt, or structural note that prevents a real misunderstanding. |

Use only terms that sharpen the decision.

## 1. Frame the pressure

If the request supplies a concrete architecture target, boundary, subsystem, or current structural pressure, bypass opportunity discovery and restate that target for a reader with no assessment context. If no target is supplied, load [Opportunity Discovery](opportunity-discovery.md) once, then continue here with the qualified target, `no-design-change`, or blocker. Bound the behavior, owner, boundary, exclusions, and decision horizon under design without repository-wide triage. A pressure inside one module or class, such as its responsibilities, collaborators, or interface, is a legitimate target: frame it there rather than widening it into system redesign. Whether the target was supplied or discovered, search by behavior, not only by name, wherever the responsibility under design could already be performed, beyond the target's own bound and exclusions, for every existing mechanism that already performs it, such as another cache, retry loop, translation layer, or owner of the same state or policy. This is a targeted search for one responsibility, not repository-wide triage. Complete when current evidence supports the pressure or no-change outcome, no missing fact can change whether architecture work is justified, and the search has covered every place that responsibility could already live, with each mechanism found noted for gate 4.

## 2. Build direct evidence

Record only evidence needed to trust the decision. Use the direct locator syntax in `architecture-template.md`; distinguish repository, request, runtime, and external evidence. Local evidence may include a line-range SHA-256; sealing computes it when omitted.

Complete when every persisted structural claim cites a defined locator and every missing decision-changing repository fact has been gathered or preserved as an unknown.

## 3. Classify authority

Separate repository facts, Architect-owned technical tradeoffs, user-owned architecture policy, and implementation-planning questions. Gather a missing decision-changing fact as evidence. Architect decides ordinary technical structural tradeoffs. Ask one minimum user question only for irreducible material SLO, compatibility, cost, operations, ownership, or risk policy. Reason output is temporary and never enters `architecture.md`.

Complete when the selected decision does not hide a user-owned policy as a repository fact or push an Architect-owned tradeoff back to the user.

## 4. Select the architecture

Before selecting, account in working notes for each structural lens: move ownership, invert a dependency, split or merge, add or remove an abstraction, narrow a contract, and keep the current structure. Each yields a candidate or a one-line reason it does not apply; no candidate count is required, and lens notes never enter `architecture.md`. Bring a design concept or principle, such as cohesion, coupling, information hiding, or a SOLID principle, only where it explains why a candidate resolves this pressure. None is mandatory, and a principle violation alone is not a pressure.

Choose the smallest structure, at the level where the pressure lives, that resolves the pressure while preserving material invariants and constraints. Account for each existing mechanism noted in gate 1 as the selected owner, a merge target, or excluded with a reason, so the decision consolidates rather than adds parallel machinery; name each owner or merge target with its citation in `Selected architecture` or `Owner / boundary`, and record an excluded mechanism that keeps doing the same job beside the owner under `Consequences`. A choice evidence can rank is yours. When materially distinct candidates remain that evidence cannot yet rank, load [Structural Techniques](structural-techniques.md) before invoking `ideate`. Invoke `ideate` only when no viable structure is apparent or materially distinct candidates remain that evidence cannot rank; obtain the user's choice while its `Selection` is `open`, record that choice as user-owned policy, and treat a `research-limited` result as a blocker. Persist an alternative under `Alternatives and Tradeoffs` only when it stayed materially distinct and live, and persist only the tradeoff and discriminator that affected the decision. State the discriminator that made the selected structure win in `Selected architecture`, or under `Alternatives and Tradeoffs` when a persisted alternative already records it.

Complete when every lens has a candidate or a one-line reason, every existing mechanism noted in gate 1 is accounted for, and the architecture is settled enough that `blueprint` can plan implementation without replaying architecture discovery or re-asking settled authority merely because reasoning history is absent.

## 5. Persist compactly

Draft the adaptive shape in `architecture-template.md`. Include accepted consequences and any material user-owned architecture policy.

Blueprint receives `architecture.md` as settled architecture authority: owner/boundary, invariants/constraints, selected consequences, evidence, incorporated user policy, and any earned view/contract. Blueprint still owns implementation grounding, impact, ordered implementation instructions, verification, rollout, and recovery under its current merged contract. Architecture paths/views are bearings, not automatic edit scope. A genuine architecture contradiction returns to Architect.

## 6. Seal one handoff

Run the seal command in `SKILL.md` workflow step 5. Complete only when the command returns canonical diagnostics on failure or exactly one ignored `.first-four-hours/architectures/<slug>/architecture.md` on success. The command validates shape, direct citations, local evidence ranges/anchors/hashes, repository snapshot binding, and atomic publication. It does not infer coverage, choose architecture, or score prose.

## 7. Hand off without mutation

Complete only when the command emits exactly one `architecture.md`, every local evidence binding verifies, and generated proof binds the current repository snapshot with Architect's version as `scope_version` and the effective evidence root. Never edit the validated draft or finalized artifact. Pass the receipt-valid file to `blueprint`; Architect does not author Blueprint workspace files, route directly to `construct`, or bypass Blueprint's seal-and-stop boundary.

Snapshots exclude only safe canonical .first-four-hours/blueprints/ planning files and sealed .first-four-hours/architectures/<slug>/architecture.md handoffs; neither can be architecture evidence. Foreign, tracked or symlinked namespace content fails closed. Older snapshots that included planning files need resealing, without reopening settled decisions unless current evidence contradicts them. Fresh intake rejects snapshots whose `scope_version` has another major or whose project root is ambiguous; reseal from current evidence at the intended root. Frozen Construct resume checks only the outer receipt/proof envelope and never reinterprets snapshot scope.

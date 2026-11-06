# Bounded Delegation Protocol

When another orchestrated handoff invokes Assess, it owns the independent assessment stage and assessment.md; the upstream owner retains merge and implementation authority. Delegation is optional and must pay for itself: keep tiny or direct assessment local. The Assess owner synthesizes the read-only result; delegation never changes the sealed `assessment.md` contract or its binding.

## Earned delegation

When the harness has the matching agent and it launches, launch a falsification slice as `ffh-reviewer` (or `ffh_reviewer`) and a clear challenge as `ffh-challenger` (or `ffh_challenger`); otherwise, and for any other delegate, launch a generic subagent.

Two delegated subagents per Assess invocation is a ceiling, not a default; zero or one is normal. Every subagent counts: falsification slices, a clear challenge, a replacement for an unusable delegate, a risk specialist, and any subagent a Reason consultation uses. Delegates never delegate. The fresh-context Assess owner of a self-authored handoff is not a delegate: it counts toward no ceiling here and keeps its own.

- **Independent session:** independence comes from the reviewing context, not from a subagent. When the Assess owner did not write or plan the change in its current context, it is already fresh-context and needs no independence delegate.
- **Self-authored change:** when the Assess owner wrote or planned the change in its current context, it does not assess the change there, so the author's reasoning cannot vouch for itself and the assessment does not re-read the authoring context every turn. First tell the user once that running Assess in a fresh session avoids even this handoff. Then launch one generic subagent with the owner's own capability, never a cheap worker, as the fresh-context Assess owner. Its brief holds:
  - the repository root, the exact target and its base and head refs, and a new assessment slug;
  - the absolute path of this skill's `SKILL.md`, which it follows end to end;
  - the user's Assess request verbatim;
  - snapshots of the original request (written verbatim outside the repository when it exists only in this conversation), the authoritative requirements, any available Blueprint, and any current `diagnosis.md` for this change;
  - on a delta re-review, the earlier `assessment.md` path;
  - a statement that it did not write or plan the change, is an independent session, and never hands off again.

  It receives nothing the brief rules below exclude. Where it cannot launch its own subagents, it records an earned clear challenge it cannot run as a limitation; the user accepted this trade. It returns the sealed `assessment.md` path, or the `/diagnose` risk question or blocker it stopped on, plus its Reason checkpoint trace and any open Reason disposition. Run `check` on a returned path and confirm its bound target, base, and head match the brief. Then report per Complete from that checked artifact, adding nothing it does not seal, and relay the trace (as run in fresh context) and every open disposition. Or relay the Diagnose need or blocker. A path that fails `check` or does not match counts as no return. On no return, stop and report that, with a fresh-session `/assess` prompt as the next step; never seal or repair in its place from this context. When no subagent can launch, assess in this context and record the whole change as a self-review limitation.
- **Bounded falsification:** a read-only subagent is earned when a bounded slice improves cost, context, coverage, independent judgment, or parallelism more than briefing and verifying it costs.
- **Clear challenge:** when completed consequential coverage would be `clear` and false-negative cost is meaningful, at most one fresh bounded challenge asks for the strongest missed material defect in that exact scope.

When two slices earn their cost, default to **Contract/Surface** (intent fidelity, propagation, ownership and minimality) and **Behavior/Proof** (behavioral correctness, preservation, proof adequacy, integration readiness). Attach security, concurrency, recovery, or another earned risk lens to one of these slices or keep it owner-local; a lens never becomes an extra delegate, artifact field, or matrix.

Once both slots are used, follow-up and residual coverage stay owner-local, and an earned clear challenge the ceiling leaves unrun is recorded as a limitation. The ceiling never excuses missed material work: examine remaining material scope, or disclose it as a limitation (`blocked` when that gap prevents a trustworthy result); self-authored scope no fresh-context owner or delegate examined is disclosed either way. Diagnose is separately earned investigation, never a third reviewer delegate.

Axes are lenses, not work units: never require one subagent per axis, a fixed reviewer count, panels, voting, recursive Assess, repeated challenge rounds, ledgers, scorecards, cost/token accounting, or a semantic aggregation engine.

## Brief and return

Each subagent receives only a curated packet:
- the exact target, base, and head, or the bounded source;
- snapshots of, or pointers to, the original request, the authoritative requirements, and any available Blueprint, which is authority evidence, never proof, so the delegate checks the diff against the original request as well as the plan;
- the base-to-head diff, or on a delta re-review the earlier-head-to-head diff, each earlier finding's `required_truth`, that assessment's open gaps as [delta review](delta-review.md) defines them, and its `Base revision`;
- its slice or falsification question, with its exclusions; and
- the objective stop and the compact return contract.

Never give a subagent the owner's transcript or exploration notes, the implementer's narrative or self-assessment, PR prose, or prior findings beyond those delta items. It reviews adversarially inside that slice, continues after the strongest defect until independently material defects in scope are exhausted, returns material ambiguity or contradiction instead of broadening authority, and does not delegate.

It always returns its examined scope and any material ambiguity, plus either candidate findings or a compact bounded-clear statement, and nothing else. A candidate finding contains concrete defect, the short steps from trigger to wrong outcome, material consequence, exact authority locator, and exact implementation/proof locator, plus whether it was observed by execution or reasoned; no essays, transcripts, plans, matrices, scores, or confidence.

## Owner verification

Assess accepts or rejects each candidate by the cheapest sufficient authoritative lookup: open the cited locators, try to falsify the candidate, and inspect narrowly only when ambiguity, contradiction, or a new material surface earns it. The owner never repeats a whole delegated slice absent a concrete coverage gap, and covers every material scope no delegate examined. Conflicts resolve against current authority and evidence, never vote, confidence, count, or arrival order. After accepting a defect, follow its propagation only far enough to find independent merge-relevant consequences.

<!-- delegation-projection:begin -->
### Delegation: preserve authority, bound labor

Delegate only when the likely cost, context, coverage, or parallelism gain exceeds coordination overhead; keep tiny or direct work local.

A lifecycle or public-capability handoff makes the receiving agent the semantic owner of that stage, not a cheap helper. The stage owner retains sufficient capability for reliable direct-quality work and owns scope, decisions, authoritative artifacts or results, acceptance, and completion. A nested stage owner may delegate its own bounded support work.

Use a bounded specialist when narrow independent judgment is the point; choose capability proportional to ambiguity and consequence, and let the owner recheck and decide the result. Use a bounded worker only for cheap-to-verify labor. Give it the exact task or question, inputs and scope, authority and exclusions, objective stop, compact verifiable result or proof, and require it to return material ambiguity or contradiction. Prefer the cheapest sufficient selectable worker, but never let it expand scope or authority, make product, architecture, or completion decisions, vote on semantic truth, or delegate again. Workers are read-only by default; a skill-specific write exception requires already-settled semantics, exact scope and proof, cheaper owner inspection than direct work, and explicit owner acceptance.

Parallelize only independent bounded work and reconcile conflicts against current authority and evidence, never confidence, count, votes, or arrival order. When model selection is unavailable, preserve these roles without inventing routing machinery; never encode provider names, prices, or a skill-to-model matrix.

Keep this subsection as the shared source of truth. A standalone package that needs it must receive a mechanically derived local projection plus only its skill-specific trigger, scope, return or proof, and consumption rules; do not hand-copy the doctrine. A direct or no-delegation skill needs no projection.
<!-- delegation-projection:end -->

# Earned Conformance Review

When this review is earned and the harness has an `ffh-conformance` agent (or `ffh_conformance`) that launches, launch the reviewer as that agent; otherwise launch a generic subagent. When you run as `ffh-constructor` (or `ffh_constructor`), the First Four Hours constructor, or otherwise cannot launch a subagent, launch none: report the review as earned and not run, so your caller launches it after you return or reports it as not run.

When an orchestrated handoff invokes Construct, it owns the execution stage and the completion report. The primary agent remains the owner of edits, delta acceptance, repair, attribution, and completion judgment. A Construct run is normally verified by the authored verification and the bounded direct conformance pass. A change meeting any risk clause in SKILL.md's Reconcile and report step earns one fresh, read-only, material-only conformance reviewer; work meeting none earns no reviewer.

Give the reviewer the sealed Blueprint and, in its brief, what it may lack a shell to produce: when the Blueprint has `existing` or `deleted` Locations Git tracks, `git diff HEAD -- <path>...` output with exactly those paths as arguments; every other Location's path, to read whole; and each pre-run state [Safety](safety-and-recovery.md) records, taken from Construct's report when you launch after it. It may read unchanged source itself. Its job is limited to: a missing authored instruction, an unauthorized material delta, a preservation violation judged from those diffs and pre-run states, never from current content alone (unverified, never passed, where a pre-run state is unavailable), or a material contradiction of an authored snippet, mechanism, or order. It does not redesign, widen scope, judge YAGNI, or become another planning stage. Recheck every finding before acting; re-verify any finding mechanically where possible, and return a confirmed semantic necessity to Blueprint. A reviewer is read-only and cannot change the Blueprint or create any execution artifact. No implementation work is delegated: Construct grants no implementation worker and no delegated write. Do not recurse, score, vote, or persist a transcript.

<!-- delegation-projection:begin -->
### Delegation: preserve authority, bound labor

Delegate only when the likely cost, context, coverage, or parallelism gain exceeds coordination overhead; keep tiny or direct work local.

A lifecycle or public-capability handoff makes the receiving agent the semantic owner of that stage, not a cheap helper. The stage owner retains sufficient capability for reliable direct-quality work and owns scope, decisions, authoritative artifacts or results, acceptance, and completion. A nested stage owner may delegate its own bounded support work.

Use a bounded specialist when narrow independent judgment is the point; choose capability proportional to ambiguity and consequence, and let the owner recheck and decide the result. Use a bounded worker only for cheap-to-verify labor. Give it the exact task or question, inputs and scope, authority and exclusions, objective stop, compact verifiable result or proof, and require it to return material ambiguity or contradiction. Prefer the cheapest sufficient selectable worker, but never let it expand scope or authority, make product, architecture, or completion decisions, vote on semantic truth, or delegate again. Workers are read-only by default; a skill-specific write exception requires already-settled semantics, exact scope and proof, cheaper owner inspection than direct work, and explicit owner acceptance.

Parallelize only independent bounded work and reconcile conflicts against current authority and evidence, never confidence, count, votes, or arrival order. When model selection is unavailable, preserve these roles without inventing routing machinery; never encode provider names, prices, or a skill-to-model matrix.

Each turn re-reads your context, so issue every independent read, search, and probe the question could need together, as parallel calls or one command; call alone only when the input depends on an earlier result. Never skip evidence to save calls; split the work rather than produce output too large to show inline.

Keep this subsection as the shared source of truth. A standalone package that needs it must receive a mechanically derived local projection plus only its skill-specific trigger, scope, return or proof, and consumption rules; do not hand-copy the doctrine. A direct or no-delegation skill needs no projection.
<!-- delegation-projection:end -->

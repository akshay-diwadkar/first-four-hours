# Delegation Protocol

When Blueprint planning or another orchestrated handoff consults Ideate, Ideate owns ideation.md and the caller keeps its own decisions. Only the Deep tier delegates.

## Research workers

Launch one worker per survey class, never per candidate, in parallel: as `ffh-researcher` (or `ffh_researcher`) when it launches, else a generic subagent. Give each the goal, scope and non-goals, `Already known:`, its class and playbook guidance, exclusions, and stop condition. Workers stay read-only and never write `ideation.md`; their returns are candidate evidence Ideate verifies before use. Retry one materially incomplete worker once, then record the gap in the `Research:` coverage.

## Fresh challenger

Before sealing, launch exactly one: `ffh-challenger` (or `ffh_challenger`) when it launches, else a generic subagent at least as capable as you. Give it only the draft's text, the goal and criteria, `Already known:`, and three to five load-bearing claims with their sources, withholding your reasoning, and ask for the strongest case that a dropped or unconsidered candidate, or the baseline, should win; it cannot search the web, so verify what it points to. Re-verify each finding and decide. When no subagent launches, research and challenge locally as Standard does and say so in the `Research:` coverage.

<!-- delegation-projection:begin -->
### Delegation: preserve authority, bound labor

Delegate only when the likely cost, context, coverage, or parallelism gain exceeds coordination overhead; keep tiny or direct work local. A subagent that reports its tools unavailable before doing any work did not launch: fall back as when it is absent.

A lifecycle or public-capability handoff makes the receiving agent the semantic owner of that stage, not a cheap helper. The stage owner retains sufficient capability for reliable direct-quality work and owns scope, decisions, authoritative artifacts or results, acceptance, and completion. A nested stage owner may delegate its own bounded support work.

Use a bounded specialist when narrow independent judgment is the point; choose capability proportional to ambiguity and consequence, and let the owner recheck and decide the result. Use a bounded worker only for cheap-to-verify labor. Give it the exact task or question, inputs and scope, authority and exclusions, objective stop, compact verifiable result or proof, and require it to return material ambiguity or contradiction. Prefer the cheapest sufficient selectable worker, but never let it expand scope or authority, make product, architecture, or completion decisions, vote on semantic truth, or delegate again. Workers are read-only by default; a skill-specific write exception requires already-settled semantics, exact scope and proof, cheaper owner inspection than direct work, and explicit owner acceptance.

Parallelize only independent bounded work and reconcile conflicts against current authority and evidence, never confidence, count, votes, or arrival order. When model selection is unavailable, preserve these roles without inventing routing machinery; never encode provider names, prices, or a skill-to-model matrix.

Each turn re-reads your context, so issue every independent read, search, and probe the question could need together, as parallel calls or one command; call alone only when the input depends on an earlier result. Never skip evidence to save calls; split the work rather than produce output too large to show inline.

Keep this subsection as the shared source of truth. A standalone package that needs it must receive a mechanically derived local projection plus only its skill-specific trigger, scope, return or proof, and consumption rules; do not hand-copy the doctrine. A direct or no-delegation skill needs no projection.
<!-- delegation-projection:end -->

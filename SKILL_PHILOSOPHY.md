# Skill Design Philosophy

## Mission

This repository exists to **raise the floor and preserve the ceiling**.

- **Raise the floor:** help a weak agent produce grounded, reliable, useful work it could not produce unaided.
- **Preserve the ceiling:** leave a strong agent free to exercise better judgment, explore superior approaches, and produce exceptional work.

Treat this philosophy as a governing design constraint whenever you create, review, or change a skill.

## The Core Contract

> Give the agent freedom to reason. Give the workflow enough structure to trust the result.

A skill should make the agent's process predictable without making its solution predetermined.

Use **guardrails, not rails**:

- A **guardrail** protects an invariant, exposes a real omission, or proves completion.
- A **rail** forces one path because it is easy to specify or validate.

Prefer guardrails. Remove rails unless the task genuinely has one valid path.

## Ownership

### Agent-owned: discover and decide

The agent owns semantic work:

- interpret the user's real goal;
- inspect the relevant evidence;
- identify scope, uncertainty, ownership, and affected surfaces;
- generate and compare approaches;
- make trade-offs;
- adapt depth to complexity and risk;
- solve the actual problem.

Specify outcomes and invariants. Keep the approach open wherever multiple valid approaches exist.

### Script-owned: verify and bind

Scripts own mechanical guarantees:

- inputs, authority, and permissions;
- artifact shape and typed references;
- evidence existence, exactness, hashes, and freshness;
- dependency consistency;
- safety and scope boundaries;
- deterministic receipts;
- declared completion and verification.

Scripts verify declared truth. Agents discover and decide.

A script should not choose semantic scope, rediscover the repository, invent missing reasoning, or select the best solution unless that choice is the skill's explicit purpose.

### Delegation: preserve authority, bound labor

Delegate only when the likely cost, context, coverage, or parallelism gain exceeds coordination overhead; keep tiny or direct work local.

A lifecycle or public-capability handoff makes the receiving agent the semantic owner of that stage, not a cheap helper. The stage owner retains sufficient capability for reliable direct-quality work and owns scope, decisions, authoritative artifacts or results, acceptance, and completion. A nested stage owner may delegate its own bounded support work.

Use a bounded specialist when narrow independent judgment is the point; choose capability proportional to ambiguity and consequence, and let the owner recheck and decide the result. Use a bounded worker only for cheap-to-verify labor. Give it the exact task or question, inputs and scope, authority and exclusions, objective stop, compact verifiable result or proof, and require it to return material ambiguity or contradiction. Prefer the cheapest sufficient selectable worker, but never let it expand scope or authority, make product, architecture, or completion decisions, vote on semantic truth, or delegate again. Workers are read-only by default; a skill-specific write exception requires already-settled semantics, exact scope and proof, cheaper owner inspection than direct work, and explicit owner acceptance.

Parallelize only independent bounded work and reconcile conflicts against current authority and evidence, never confidence, count, votes, or arrival order. When model selection is unavailable, preserve these roles without inventing routing machinery; never encode provider names, prices, or a skill-to-model matrix.

Keep this subsection as the shared source of truth. A standalone package that needs it must receive a mechanically derived local projection plus only its skill-specific trigger, scope, return or proof, and consumption rules; do not hand-copy the doctrine. A direct or no-delegation skill needs no projection.

## Design Doctrine

### 1. Every requirement pays rent

Every required field, record, phase, reference, command, and validation rule must earn its cost.

It pays rent when it does at least one of these:

- prevents a plausible failure;
- guides an implementation or review decision;
- preserves required behavior;
- exposes a real dependency, affected surface, boundary, or risk;
- enables the next workflow stage;
- proves that required work is complete.

A requirement that only makes the schema look complete is ceremony. Remove or derive it.

Before adding a rule, ask:

> What concrete bad result does this reject or prevent?

### 2. Proportional depth

Match workflow depth to the task.

- **Tiny work:** tiny artifact, narrow evidence, direct verification.
- **Standard work:** decisions, propagation, and dependencies only where they are real.
- **High-risk work:** explicit failure modes, compatibility, rollout, recovery, and ownership.

Complexity, ambiguity, fan-out, irreversibility, and operational risk earn more structure. File count and template symmetry do not.

The common path should stay light. Exceptional branches may carry exceptional rigor.

### 3. Decision-useful artifacts

A valid artifact must be useful to the next agent or human.

Every authored record should help someone decide, implement, verify, recover, or review.

Validation should reject missing correctness, not missing ceremony.

Avoid designs that reward:

- magic words;
- arbitrary record counts;
- repeated statements of the same fact;
- prose written only to satisfy a parser;
- formally complete but operationally empty artifacts.

The artifact is successful when the next stage can act without guessing.

Optimize for downstream task success, not representational completeness.

Add structure only when its absence could cause the next stage to make a plausible mistake, rediscover material reasoning, or guess. Prefer the least structured representation that preserves the decisions and context needed to act correctly; mechanical checkability alone does not justify structure.

### 4. Evidence is proof, not paperwork

Evidence supports decisions and prevents stale or invented claims.

Prefer evidence that is:

- narrow;
- current;
- relevant;
- exact enough to verify;
- sufficient for the decision being made.

Let the agent choose what to inspect. Let scripts verify what the agent cites.

Evidence requirements should focus exploration, not turn validators into repository scanners.

### 5. Derive before asking

Prefer mechanically derived information over agent-authored duplication.

Derive summaries, dependency orders, receipts, indexes, hashes, and diagrams from authoritative records when possible.

Use one **source of truth** for each meaning. A second independently authored representation creates drift.

A document that repeats an easy repository lookup is a **cache**. Cache only what is expensive or impossible to recover by looking:

- unwritten conventions;
- reasons behind decisions;
- known traps;
- cross-file conclusions;
- durable context that the environment does not encode.

Leave one-file and one-command facts in the environment, where they stay current.

### 6. Progressive disclosure

Keep the skill's common path concise and action-oriented.

Inline what every run needs. Place branch-specific rules, examples, domain guidance, and exceptional procedures behind precise context pointers.

A pointer must state:

- what the referenced material provides;
- the exact branch that should load it.

Every required read pays context load. Make it earn that load.

Clear hierarchy helps weak agents attend to the next action and lets strong agents reach deeper material only when useful.

### 7. Checkable completion

Each step needs a completion criterion that distinguishes done from not done.

Prefer criteria that are both:

- **checkable:** the agent can observe whether the condition holds;
- **exhaustive:** the criterion demands all material work, not merely an artifact-shaped output.

Examples:

- weaker: “Review the callers.”
- stronger: “Account for every caller discovered in the bounded ownership sweep.”

Use stop conditions to drive legwork. Do not add extra phases when a sharper completion criterion solves the problem.

### 8. Repair the defect

Diagnostics should name the defect and the smallest credible repair.

A local shape error should lead to a local edit. Missing or stale scope, evidence, ownership, or repository understanding may require targeted re-exploration.

Diagnostics should teach the agent how to improve the result, not merely announce failure.

### 9. Test honestly

Run the smallest relevant deterministic tests first. Expand in proportion to risk. Avoid repeating expensive unchanged suites.

Prefer provider-free fixtures containing:

- human-reviewed complete outputs;
- plausible weak outputs;
- one focused expected failure for each rule;
- assertions tied to the rule's real purpose.

This repository does not use live agent or model harnesses.

Tests may prove structure, evidence binding, deterministic behavior, and fixture coverage. State those claims precisely. Do not present them as proof of universal semantic quality or agent reliability.

### 10. Prune sediment

Skill documents naturally accumulate **sediment**: rules that were once useful, duplicated explanations, stale branches, and defensive prose added “just in case.”

Prune during every meaningful change.

For each line, ask:

- Does it change agent behavior?
- Is it needed on this branch?
- Is this meaning authoritative here?
- Can a leading word replace repeated explanation?
- Can the environment answer this more reliably?
- Can the same protection be derived mechanically?

Delete no-op instructions. Consolidate duplicate meaning. Disclose branch-specific reference. Keep the live path visible.

## Leading Words

Use these concepts consistently across skills, issues, reviews, and repository guidance:

- **Floor:** the minimum quality a weak agent can reliably reach.
- **Ceiling:** the best work a strong agent remains free to produce.
- **Guardrail:** a constraint that protects correctness while preserving valid approaches.
- **Proportional:** depth and burden matched to actual complexity and risk.
- **Decision-useful:** directly helps the next stage act.
- **Proof:** mechanical evidence that a declared fact or completion claim is trustworthy.
- **Source of truth:** the one authoritative representation of a meaning.
- **Derived:** generated from authoritative state instead of restated by the agent.
- **Cache:** documentation that copies information available from the environment.
- **Sediment:** stale or redundant guidance that obscures the live workflow.

Prefer these positive targets over long lists of forbidden behavior. Use hard prohibitions only for non-negotiable safety or repository rules, and pair them with the desired behavior.

## Change Gate

Before approving a skill change, answer:

1. Which realistic failure does this prevent?
2. Does the reliability gain justify its context and cognitive load?
3. Can the guarantee be derived instead of authored?
4. Does it raise the floor without lowering the ceiling?
5. Can an agent satisfy the rule while still producing a bad result?
6. Is the burden proportional to task complexity and risk?
7. Is the script verifying truth, or replacing judgment?
8. Does each new record or section pay rent?
9. Is there exactly one source of truth?
10. Does the test prove only what it claims?
11. Is branch-specific material progressively disclosed?
12. What can be removed or simplified now?

A change is ready when these answers are clear.

## Drift Signals

Simplify the skill when:

- artifacts grow without becoming more actionable;
- syntax work overtakes problem understanding;
- validation rewards preferred wording rather than evidence or meaning;
- tiny and high-risk tasks receive the same depth;
- scripts start choosing semantic scope or solutions;
- multiple artifacts restate the same truth;
- context grows mainly to explain the contract itself;
- formally valid outputs remain useless to the next stage;
- strong agents lose valid problem-solving options;
- new machinery compensates for unclear instructions or completion criteria.

Treat drift as a design problem. Improve the language, hierarchy, or ownership boundary before adding another mechanism.

## Definition of Excellent

An excellent skill:

- raises the floor;
- preserves the ceiling;
- keeps semantic judgment agent-owned;
- makes important omissions and contradictions hard to miss;
- uses scripts for proof, safety, consistency, and completion;
- scales its burden to the task;
- keeps one source of truth;
- discloses complexity only when its branch fires;
- produces decision-useful artifacts;
- succeeds in the next workflow stage, not merely in validation.

The objective is not maximum structure.

The objective is:

> **Maximum real-world task success with the minimum structure required to trust the result.**

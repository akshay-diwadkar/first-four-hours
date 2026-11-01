# Challenge and rehearsal

One separate fresh-context subagent challenges every draft before handoff, at its tier. Before launching it, consult `reason` in owner context, one pass without a subagent: attack the draft's most load-bearing premise and its verification against the Construct Verification section below, to catch defects before the challenger does.

## Tier

A draft is **elevated** when it shows any of these, and **standard** otherwise:

- a Location creating, changing, or deleting a file that runs as code (script, validator, test, runtime) or that one reads as configuration or fixtures;
- a budgeted or deadline gate over something the plan edits, such as token-budgeted guidance or deadline-bound tests;
- a changed contract another skill, package, or service consumes, or Locations in more than one of them (docs and changelog entries describing the change do not count);
- an irreversible or outward-facing effect (deleting data, migrating state, publishing, pushing, calling an external service);
- a change to Blueprint's or Construct's seal runtime.

Read these signals from the draft, never from how easy the work seems; one you cannot rule out counts. The tier alone sets the challenger's depth and model, whatever its ambiguity: a standard challenger gets the [Challenger brief](challenger-brief.md) on the cheapest sufficient selectable model; an elevated one also gets [Elevated attack](elevated-attack.md), on a model at least as capable as the planner. Without model selection, both use the model you have.

## One fresh challenge

Launch the challenger as a separate subagent with fresh context; your own re-read does not replace it. If no separate subagent can be launched, stop without sealing and report that the required challenge could not run. Give the challenger the authoritative request and answers, the draft `blueprint.md`, the relevant source identity, the exact evidence pointers, the [planning contract](planning-contract.md), the [Challenger brief](challenger-brief.md), this file's Tier and Requirement trace, the repository's planning-trap list when its guidance names one, and the Verification section of `references/execution-contract.md` in the Construct skill installed beside Blueprint; without Construct, the planning contract's Verification purity paragraph stands in for it. Add a branch reference only when the draft uses its branch: [Declared text](declared-text.md) for Exact, Frozen, or Proof run declarations, [Ideate in planning](ideate-in-planning.md) when the request records an Ideate selection, [Executable contracts](executable-contracts.md) for a command whose dispatch, interpreter, or environment setup matters, [Incomplete gates](incomplete-gates.md) for an environment-sensitive gate, and [Architecture intake](architecture-intake.md) for supplied architecture. Do not give it the README, [Seal receipts](seal-receipts.md), this file's other sections, or the planner's reasoning transcript. Brief it with what to read, never with premises to confirm or conclusions to expect.

## Repair and re-check

Re-verify every finding against the authoritative request and current source, and weigh it by current user authority, evidence, and real consequence; a plan's own non-goal never rejects a finding that names a required outcome. Merge only true duplicate symptoms; accept, reject, or preserve uncertainty from evidence rather than confidence or wording. Closure must identify the repaired plan instruction or command and the evidence or fully decided branch that defeats the counterexample; unsupported closure and unresolved load-bearing uncertainty block seal. A finding that needs a new fact earns one targeted bounded exploration, never a sweep; a newly material user-owned choice returns to intent closure. When a repair changes direction or a load-bearing premise fails, you own the replacement decision and repair. Locally re-trace the repaired plan for interaction errors among the repairs, and reread each Exact or Frozen block a repair changed as the file now holds it, because an edit can turn an escape sequence into a real line break or break a fence. Then remove or merge work that no longer earns its cost while keeping every decision and instruction the executor needs. Keep a declined finding's reason only when it prevents material rediscovery, as an ordinary Current State fact. A second fresh challenge is earned only when repairs replace the plan basis or architecture, or when the challenged tier missed a Tier signal the draft has or a repair adds (then elevated); any other independent review is earned only by a named material residual risk, never by a security, recovery, or concurrency label alone.

## Requirement trace

Before sealing, trace every clause of the authoritative request, and every imported architecture invariant, constraint, and policy. A change obligation traces to the instruction that realizes it and the Completion Condition that states it, whose `Shown by` proof would fail without it, or whose named owner settles it when the condition starts `Owner gate:`. A clause that is itself an owner or human acceptance traces only to an `Owner gate:` Completion Condition naming that owner and needs no instruction; any change such a clause also requires is a change obligation with its own instruction. A keep obligation traces to an explicit preservation disposition (a preservation rule in the instruction that touches its surface, or a Completion Condition), plus a discriminating Run only when a plausible compliant implementation could break it. Any other clause with no realizing instruction or preservation disposition is under-scoped; a clause outside an `Owner gate:` that a plausible implementation could violate without failing its `Shown by` proof or another authored Run is unproven; both block seal. Planner and challenger judge every wording deliverable and Completion Condition, with its proof, against what each clause it carries requires, read from the request itself, never the plan's restatement: Exact text and pins prove bytes, not meaning, so one narrowing or dropping a clause, even if changed or trimmed after the challenge, is under-scoped.

## Seal gate

Seal only when all are true:

- decision-critical repository claims are grounded;
- every request clause and imported invariant traces completely, as the requirement trace defines;
- [Attack the problem](planning-contract.md#attack-the-problem)'s stop holds for changed behavior;
- no known gap weakens a requested outcome or load-bearing invariant unless the authoritative request records the user's acceptance;
- where completion or a resume relies on earlier recorded state or a relationship that an earlier run of this work established, it is reread at its source, and proof fails an implementation that trusts a stale record or a missing relationship;
- current consumers, preservation, and safety boundaries are accounted for;
- the plan is minimum-sufficient;
- every decision takes the planning contract's required form;
- every acceptance condition not marked `Owner gate:` has an executable path;
- supported adversarial findings have evidence-backed closure in the repaired plan;
- the separate fresh-context challenge ran at the draft's tier;
- every authored Run and Proof run meets the planning contract's Verification purity, so Construct cannot stop on its writes;
- no step or Run forces the executor to discover or choose an additional repair, scope, policy or authority, ownership, validation or typing scope, exception or budget override, compatibility, or other semantic decision;
- verification is discriminating and proportionate.

If substantive judgment is still required anywhere, the Blueprint is not ready to seal. After sealing, stop.

# Adversarial challenge

One separate fresh-context subagent challenges every draft before handoff, at its tier; it is never skipped because the change looks small.

## Tier

A draft is **elevated** when it shows any of these, and **standard** otherwise:

- a Location creating, changing, or deleting a file that runs as code (script, validator, test, runtime) or that one reads as configuration or fixtures;
- a budgeted or deadline gate over something the plan edits, such as token-budgeted guidance or deadline-bound tests;
- a changed contract another skill, package, or service consumes, or Locations in more than one of them (docs, Atlas pages, and changelog entries describing the change do not count);
- an irreversible or outward-facing effect (deleting data, migrating state, publishing, pushing, calling an external service);
- a change to Blueprint's or Construct's seal runtime.

Read these signals from the draft, never from how easy the work seems; one you cannot rule out counts. The tier alone sets the challenger's depth and model, whatever its ambiguity: a standard challenger gets the brief below on the cheapest sufficient selectable model; an elevated one also gets [Elevated attack](elevated-attack.md), on a model at least as capable as the planner. Without model selection, both use the model you have.

## One fresh challenge

Launch the challenger as a separate subagent with fresh context; your own re-read does not replace it. If no separate subagent can be launched, stop without sealing and report that the required challenge could not run. Give the challenger the authoritative request and answers, the draft `blueprint.md`, the relevant source identity, the exact evidence pointers, the [planning contract](planning-contract.md), this contract, the repository's planning-trap list when its guidance names one, and the Verification section of `references/execution-contract.md` in the Construct skill installed beside Blueprint; without Construct, the planning contract's Verification purity paragraph stands in for it. Add a branch reference only when the draft uses its branch: [Declared text](declared-text.md) for Exact, Frozen, or Proof run declarations, [Ideate in planning](ideate-in-planning.md) when the request records an Ideate selection, [Executable contracts](executable-contracts.md) for a dispatch-sensitive command, [Incomplete gates](incomplete-gates.md) for an environment-sensitive gate, and [Architecture intake](architecture-intake.md) for supplied architecture. Do not give it the README, [Seal receipts](seal-receipts.md), or the planner's reasoning transcript. Brief it with what to read, never with premises to confirm or conclusions to expect.

The challenger is bound by the planning contract's Probe, don't prototype rule; it may run current-tree safe probes and Blueprint's own `check`, and writes nothing beyond a probe's own side effects.

Core question:

> This Blueprint was sealed, a mediocre executor built it literally without useful engineering judgment, and review rejected the result. Write that review: how is the result wrong, incomplete, unsafe, unnecessarily broad, or unverifiable?

Seed it from the planning traps the plan touches and any review findings the request carries. First read the Tier signals from the draft yourself; a signal present when you were not given Elevated attack is a finding. Walk the draft in step order, tracking what exists after each step and judging each Run at its phase (Before implementation precedes every instruction): a Proof run or Run needing something (a file, a target its runner selects or reads, a tool) not yet there, or working only outside how Construct launches it, is a finding even when it passes now. For every material instruction, construct a **compliant-but-bad implementation**, such as an open decision, a dropped outcome or consumer, a wrong premise, an undecided input or exit path, missing preservation or Atlas propagation, unearned scope, or proof that passes a wrong result. Check verification form too: each Run executes verbatim, each Expect is judgeable from its Run's output and tells completion from a plausible failure, each condition's `Shown by` proof exists and can show it, owner-only acceptance carries `Owner gate:`, and selection covers the whole planned diff, including renamed and deleted sides.

Attack decisions and proof, never plan code's compile, lint, or type correctness. The challenger continues after the first finding through the remaining material scope and reports every independently material gap found in the bounded pass. It advises only: it never rewrites the Blueprint, chooses scope, or owns design.

Derive every applicable counterexample from source, current-tree probes, and the authored command path, including unchanged seams. Re-derive at least the plan's most load-bearing premise yourself from source, and through the authored command's public entrypoint when that premise concerns command behavior; the planner's probe is not that evidence. Trace commands as Commands and evidence and, when its branch applies, Executable contracts require (read it if not given), including fixture selection when tests, fixtures, or package surfaces change, and check for an exit-code contradiction wherever an Expect admits nonzero exit. When no such risk applies, no disposition record is earned; do not manufacture work for a simple plan. Whatever the plan's size, hold at least the authored command likeliest to write to Verification purity: trace its actual write surface from source or a probe that rule allows, and test that its check reads independent source truth.

For each material finding name the instruction, command, or completion condition; the compliant-but-bad result; decisive evidence or missing fact; and the smallest closure obligation; a missing behavior proof closes only as the planning contract's Step proof allows. An outcome no source or current-tree probe can settle remains a finding until it meets the planning contract's Probe, don't prototype rule. A restated checklist or an unsupported assertion that a command works is not a finding or closure proof, and an authored Run alone never closes a load-bearing finding.

Challenge at least one plausible failure in each materially distinct branch. State untested limits.

## Repair and re-check

Re-verify every finding against the authoritative request and current source, and weigh it by current user authority, evidence, and real consequence; a plan's own non-goal never rejects a finding that names a required outcome. Merge only true duplicate symptoms; accept, reject, or preserve uncertainty from evidence rather than confidence or wording. Closure must identify the repaired plan instruction or command and the evidence or fully decided branch that defeats the counterexample; unsupported closure and unresolved load-bearing uncertainty block seal. A finding that needs a new fact earns one targeted bounded exploration, never a sweep; a newly material user-owned choice returns to intent closure. When a repair changes direction or a load-bearing premise fails, you own the replacement decision and repair. Locally re-trace the repaired plan for interaction errors among the repairs, and reread each Exact or Frozen block a repair changed as the file now holds it, because an edit can turn an escape sequence into a real line break or break a fence. Then remove or merge work that no longer earns its cost while keeping every decision and instruction the executor needs. Keep a declined finding's reason only when it prevents material rediscovery, as an ordinary Current State fact. A second fresh challenge is earned only when repairs replace the plan basis or architecture, or when the challenged tier missed a Tier signal the draft has or a repair adds (then elevated); any other independent review is earned only by a named material residual risk, never by a security, recovery, or concurrency label alone.

## Requirement trace

Before sealing, trace every clause of the authoritative request, and every imported architecture invariant, constraint, and policy. A change obligation traces to the instruction that realizes it and the Completion Condition that states it, whose `Shown by` proof would fail without it, or whose named owner settles it when the condition starts `Owner gate:`. A clause that is itself an owner or human acceptance, such as a cold read after implementation, traces only to an `Owner gate:` Completion Condition naming that owner and needs no instruction; any change such a clause also requires is a change obligation with its own instruction. A keep obligation traces to an explicit preservation disposition (a preservation rule in the instruction that touches its surface, or a Completion Condition), plus a discriminating Run only when a plausible compliant implementation could break it. Any other clause with no realizing instruction or preservation disposition is under-scoped; a clause outside an `Owner gate:` that a plausible implementation could violate without failing its `Shown by` proof or another authored Run is unproven; both block seal. Beyond each condition's `Shown by` proof, keep the trace in working context, never in the artifact.

## Seal gate

Seal only when all are true:

- user-owned ambiguity is closed;
- decision-critical repository claims are grounded;
- all material engineering and design decisions are settled;
- every request clause and imported invariant traces completely, as the requirement trace defines;
- every producible input state, exit path, and invariant-violation path of changed behavior is decided;
- no known gap weakens a requested outcome or load-bearing invariant unless the authoritative request records the user's acceptance;
- where completion or a resume relies on earlier recorded state or a relationship that an earlier run of this work established, it is reread at its source, and proof fails an implementation that trusts a stale record or a missing relationship;
- current consumers, preservation, and safety boundaries are accounted for;
- the plan is minimum-sufficient;
- implementation instructions are concrete enough for a mediocre executor;
- every decision takes the planning contract's required form;
- every acceptance condition not marked `Owner gate:` has an executable path;
- supported adversarial findings have evidence-backed closure in the repaired plan; unresolved load-bearing uncertainty blocks seal;
- the separate fresh-context challenge ran at the draft's tier;
- every authored Run and Proof run meets the planning contract's Verification purity, so Construct cannot stop on its writes;
- no step or Run forces the executor to discover or choose an additional repair, scope, policy or authority, ownership, validation or typing scope, exception or budget override, compatibility, or other semantic decision;
- verification is discriminating and proportionate.

If substantive judgment is still required anywhere, the Blueprint is not ready to seal. After sealing, stop. A changed request or answer means a fresh draft and workspace; a frozen request or sealed Blueprint is never edited in place.

# Challenge and rehearsal

## Tier

A plan is **Critical** when its decisions show any of these:

- a change to a validator, a shared runtime, or Blueprint's or Construct's seal runtime;
- a deadline gate whose measured headroom the change can plausibly consume;
- a changed contract that another skill, package, or service parses or executes;
- an irreversible or outward-facing effect (deleting data, migrating state, publishing, pushing, calling an external service).

Otherwise it is **Standard** when a consumer outside the changed package, or a propagation to another file, matters, or check reports a reach hit the plan neither edits nor names in Facts as left alone, else **Quick**. A skill version raises no signal. Read signals from the decisions, not from how easy the work seems.

## Desk check

For each Proof run, then each Run, in step order:

- **Exists:** everything it reads, selects, or imports exists now or an earlier step creates it.
- **Launches:** its argv works as Construct launches it: no shell, repository root, inherited environment, the interpreter that resolves there. Probe it, or an existing target in the same form.
- **Passes:** each `Expect:` holds on the plan's own drafted bytes and a correct implementation of this plan alone, and each check preview reads as intended at both edges.
- **Fits:** it stays within every suite-size cap, validator allowlist, budget, pinned version, and deadline the change touches, with measured value and headroom recorded.

## Challenge

- **Quick:** check that no hidden choice is left, every clause ID has a step and a Run, and no proof passes a wrong result.
- **Standard:** run the [Challenger brief](challenger-brief.md) yourself, one compliant-but-bad implementation per decision, backing each with a fresh observation.
- **Critical:** one fresh challenge, launched once the draft passes `check`; your own re-read does not replace it. Use `ffh-challenger` (or `ffh_challenger`) when it launches, else a model at least as capable as yours; if none launches, stop unsealed and report it. Launch exactly one, giving it only the request and answers, the draft, the [Challenger brief](challenger-brief.md), the repository's planning-trap list, and the three to five load-bearing premises you name with evidence pointers; withhold your reasoning. Wait for its review, then repair.

One user request gets at most one fresh challenge, amendments included, counting other independent reviews and drafts carried to a fresh workspace; repair against the findings you have. One returning no review stops you. When later repairs would replace the basis or architecture, stop unsealed and report the failing premise. A Critical signal found later earns the challenge if none ran, else run the brief's Critical re-enumeration yourself.

## Repair

Re-verify each finding against the request and current source, weighing user authority, evidence, and consequence rather than confidence. Closure names the repaired instruction and the evidence or decided branch defeating the counterexample; unsupported closure blocks seal. A needed fact earns one bounded exploration; ask all user-owned choices at once, amend the request in place ([Earlier plans](earlier-plans.md#commands)), and repair only what the answers change. Reread each changed declared block as the file holds it, and drop work that stopped earning.

## Requirement trace

Before sealing, trace each clause of the authoritative request (of a diagnosis, assessment, or test-audit handoff, its selected findings, which you name to the challenger) and each imported architecture invariant, constraint, and policy. A change obligation traces to its instruction and the Trace item whose proof would fail without it, or whose `Owner gate:` owner settles it; a keep obligation traces to a preservation rule or Trace item, proved when a plausible implementation could break it. A clause without either is under-scoped, and one a plausible implementation could break unnoticed is unproven; both block seal. Planner and challenger judge every wording deliverable and Trace item, with its proof, against what each clause it carries requires, read from the request itself, never the plan's restatement: Exact text and pins prove bytes, not meaning, so one narrowing or dropping a clause, even if changed or trimmed after the challenge, is under-scoped.

## Seal gate

Seal only when every rule in this file and the planning contract holds, including:

- no known gap weakens a requested outcome or load-bearing invariant unless the authoritative request records the user's acceptance;
- where completion or a resume relies on earlier recorded state or a relationship that an earlier run of this work established, it is reread at its source, and proof fails an implementation trusting it;
- the desk check passed and the tier's challenge ran.

If substantive judgment is still required anywhere, the Blueprint is not ready to seal. After sealing, stop.

# Challenge and rehearsal

Every draft gets an owner walk, your pre-challenge `reason` consultation: run the [Challenger brief](challenger-brief.md) and Construct's Verification section yourself, re-deriving the load-bearing premise from source and backing each compliant-but-bad case with a fresh observation. An elevated draft also gets one fresh challenge.

## Tier

A draft is **elevated** when it shows any of these, else **standard**:

- a Location creating, changing, or deleting code (script, validator, test, runtime) or configuration or fixtures something reads, unless the draft is tiny (planning contract) and changes one source file plus tests exercising only it, none a validator or shared runtime or configuration;
- a budgeted or deadline gate whose limit changes or whose headroom the change can plausibly consume;
- a changed contract another skill, package, or service consumes, or Locations in more than one (docs and changelog excepted);
- an irreversible or outward-facing effect (deleting data, migrating state, publishing, pushing, calling an external service);
- a change to Blueprint's or Construct's seal runtime.

A skill version raises no signal. Read signals from the draft, not from how easy the work seems; one you cannot rule out counts.

## One fresh challenge

For an elevated draft, launch the challenger as a separate fresh-context subagent; your own re-read does not replace it. Use `ffh-challenger` (or `ffh_challenger`) when it launches, else a model at least as capable as yours; if none launches, stop unsealed and report it. Give it the request and answers, the draft, evidence pointers, the [planning contract](planning-contract.md), the [Challenger brief](challenger-brief.md), this file's Tier and Requirement trace, the planning-trap list, Construct's Verification section, and each reference whose branch the draft uses; never your reasoning or premises to confirm.

## Repair and re-check

Re-verify each finding against the request and current source, by user authority, evidence, and consequence, never confidence. Closure names the repaired instruction and the evidence or decided branch defeating the counterexample; unsupported closure blocks seal. A needed fact earns one bounded exploration, and a user-owned choice returns to intent closure. Re-trace repairs, reread each changed declared block as the file holds it, and drop work that stopped earning.

One user request gets at most one fresh challenge, counting other independent reviews and drafts carried to a fresh workspace, so never rechallenge; one returning no review stops you, and only a new request recording the user's answer resets the count. When later repairs would replace the basis or architecture, stop unsealed and report the failing premise. A Tier signal found later earns the challenge if none ran, else run the brief's elevated re-enumeration yourself.

## Requirement trace

Before sealing, trace each clause of the authoritative request (of a diagnosis or assessment handoff, its selected findings, which you name to the challenger) and each imported architecture invariant, constraint, and policy. A change obligation traces to its instruction and the Completion Condition whose proof would fail without it, or whose `Owner gate:` owner settles it; a keep obligation traces to a preservation rule or condition, proved when a plausible implementation could break it. A clause without either is under-scoped, and one a plausible implementation could break unnoticed is unproven; both block seal. Planner and challenger judge every wording deliverable and Completion Condition, with its proof, against what each clause it carries requires, read from the request itself, never the plan's restatement: Exact text and pins prove bytes, not meaning, so one narrowing or dropping a clause, even if changed or trimmed after the challenge, is under-scoped.

## Seal gate

Seal only when every rule in this file and the planning contract holds, including:

- no known gap weakens a requested outcome or load-bearing invariant unless the authoritative request records the user's acceptance;
- where completion or a resume relies on earlier recorded state or a relationship that an earlier run of this work established, it is reread at its source, and proof fails an implementation trusting it;
- the owner walk ran, plus an elevated draft's fresh challenge.

If substantive judgment is still required anywhere, the Blueprint is not ready to seal. After sealing, stop.

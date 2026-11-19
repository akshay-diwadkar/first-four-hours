# Challenge and rehearsal

Every draft gets an owner walk: the desk check below, then the load-bearing premise re-derived from source. A standard draft's walk also runs the [Challenger brief](challenger-brief.md), backing each compliant-but-bad case with a fresh observation; an elevated draft leaves the brief to its one fresh challenge.

## Desk check

Rehearse Construct's Verification section on paper. For each Proof run in instruction order, then each Run, confirm:

1. **Exists.** Everything it reads exists now or an earlier instruction creates it.
2. **Launches.** Its argv works as Construct launches it: no shell, repository root, only Construct's inherited environment. Probe its launch safely on the current tree, a planned target through an existing one of the same form; read [Executable contracts](executable-contracts.md) when that cannot settle dispatch.
3. **Passes on the drafted bytes.** Its `Expect:` holds against the drafted Exact and Frozen text and every other planned file it scans.
4. **Fits the limits.** It stays within every cap, allowlist, pinned value, and validator rule the change touches, per the planning contract's Repository traps.

Rerun it after every repair.

## Tier

A draft is **elevated** when it shows any of these, else **standard**:

- a Location creating, changing, or deleting a validator, a shared runtime, configuration or fixtures read by anything other than the confined package's own tests, or code (script, test, runtime) not confined to one package or directory whose own tests exercise it directly;
- a budgeted or deadline gate whose limit changes or whose headroom the change can plausibly consume;
- a changed contract another skill, package, or service consumes, or Locations in more than one (docs and changelog excepted);
- an irreversible or outward-facing effect (deleting data, migrating state, publishing, pushing, calling an external service);
- a change to Blueprint's or Construct's seal runtime.

A skill version raises no signal. Read signals from the draft, not from how easy the work seems; one you cannot rule out counts.

## One fresh challenge

For an elevated draft, launch the challenger as a separate fresh-context subagent; your own re-read does not replace it. Use `ffh-challenger` (or `ffh_challenger`) when it launches, else a model at least as capable as yours; if none launches, stop unsealed and report it. Give it the request and answers, the draft, evidence pointers, the [planning contract](planning-contract.md), the [Challenger brief](challenger-brief.md), this file's Desk check, Tier, and Requirement trace, the planning-trap list, Construct's Verification section, [Each turn](delegation-protocol.md#delegation-preserve-authority-bound-labor), and each reference whose branch the draft uses. Withhold your reasoning and any premise you want confirmed. Launch it before your owner walk and, if your harness allows, walk while it works; edit the draft only after its review, then repair all findings together.

## Repair and re-check

Re-verify each finding against the request and current source, weighing user authority, evidence, and consequence rather than confidence. Closure names the repaired instruction and the evidence or decided branch defeating the counterexample; unsupported closure blocks seal. A needed fact earns one bounded exploration; ask all user-owned choices at once, amend the request in place ([Earlier plans](earlier-plans.md#commands)), and repair only what the answers change. Reread each changed declared block as the file holds it, and drop work that stopped earning.

One user request gets at most one fresh challenge, amendments included, counting other independent reviews and drafts carried to a fresh workspace; repair against the findings you have. One returning no review stops you. When later repairs would replace the basis or architecture, stop unsealed and report the failing premise. A Tier signal found later earns the challenge if none ran, else run the brief's elevated re-enumeration yourself.

## Requirement trace

Before sealing, trace each clause of the authoritative request (of a diagnosis, assessment, or test-audit handoff, its selected findings, which you name to the challenger) and each imported architecture invariant, constraint, and policy. A change obligation traces to its instruction and the Completion Condition whose proof would fail without it, or whose `Owner gate:` owner settles it; a keep obligation traces to a preservation rule or condition, proved when a plausible implementation could break it. A clause without either is under-scoped, and one a plausible implementation could break unnoticed is unproven; both block seal. Planner and challenger judge every wording deliverable and Completion Condition, with its proof, against what each clause it carries requires, read from the request itself, never the plan's restatement: Exact text and pins prove bytes, not meaning, so one narrowing or dropping a clause, even if changed or trimmed after the challenge, is under-scoped.

## Seal gate

Seal only when every rule in this file and the planning contract holds, including that no known gap weakens a requested outcome or load-bearing invariant unless the authoritative request records the user's acceptance.

If substantive judgment is still required anywhere, the Blueprint is not ready to seal. After sealing, stop.

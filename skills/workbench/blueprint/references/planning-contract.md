# Planning contract

**Hidden-choice test:** if two executors competent at local coding but without design authority, following the wording faithfully, could produce materially different behavior, control flow, interfaces, data shape, ordering, compatibility, preservation, verification, or test cases, the plan is not yet implementation-complete.

## The rent rule

> Admit a material planned addition only when a current outcome, grounded preservation boundary, required propagation, safety/recovery requirement, or credible verification would fail without it.

Future usefulness, genericity, symmetry, elegance, imagined callers, and "while we are here" earn nothing. Defend only across a real trust boundary: in the user's own checkout and tools, tamper detection or signing earns nothing, while refusing unauthorized or destructive actions and protecting unrelated work still bind. YAGNI is not smallest diff or least detail, and not permission to omit current consumers, preservation, safety, recovery, compatibility, or meaningful proof; executor detail that prevents a plausible material mistake pays rent.

## Intent closure

For a child of a parent or epic issue, copy each constraint the parent sets for its children verbatim into the request before preparing and give the challenger the parent's text.

Close every known gap or get the user's recorded acceptance: a requested outcome or load-bearing invariant failing for some producible input, state, configuration, or environment, including one a supported finding names, is a gap however rare or low-consequence. Record the user's answer by amending the request in place ([Earlier plans](earlier-plans.md#commands)); acceptance only in chat, Goal, a report, a non-goal, or a risk is unrecorded. A prediction carried by authored verification is not a gap.

## Approach and scope

Goal's scope names the trust boundary and protected behavior, and non-goals only where someone would reach past them. A non-goal bounds the plan's additions, never a requested outcome, preserved obligation, or consumer. Reuse a current mechanism only once its load-bearing assumptions hold.

## Repository traps

Account for every trap the change touches in the repository's own planning-trap list, when its guidance names one. Search the repository for each edited path and any tool writing a hash, receipt, or copy of it; for each check, validator, loader, or packaging rule enumerating any directory holding a new, deleted, or renamed path, or its file type; for the old value of any changed version or identifier others compare against; and for the registrations, allowlists, and vendored copies of any reused mechanism; plan each refresh or companion edit as a step.

## Behavior, not mechanism

Specify behavior: the outcome and its edge cases. Fix a mechanism, such as a pattern, formula, algorithm, or I/O mode, only when something outside the code requires it, such as a format another tool parses or an exact user-facing string, and state that reason. An "X or Y" whose options behave differently is an open choice, including one a repair adds.

## Commands and evidence

Establish prerequisites through the path that launches the command: executable, arguments, working directory, state, tools, credentials, sandbox permissions, quoting, and environment. Construct runs every Run and Proof run as argv without a shell, from the repository root, with only its own inherited environment, so probe load-bearing commands that way. A safe probe answers one question from the unmodified tree, with no installs, mutations, external access, or planned change; it may leave what the tool writes on its own (ignored caches, locks, removed temporary roots), never a tree copy you make. Read [Executable contracts](executable-contracts.md) when dispatch, runtime, or environment can change correctness, or the plan changes tests, fixtures, helpers, or package surfaces, or a Run selects a subset of tests. Load-bearing executable, phase, prerequisite, or selection claims need source tracing or a safe probe, or readiness is blocked; label other predictions. A passing seal proves no semantic claim.

## Implementation instructions

Implementation-complete means decision-complete, not code-complete: settle every decision and the proof exposing a wrong outcome, leaving local coding to the executor. Write ordered `### N.` steps in README's sealed shape; `check` enforces their declaration lines. A specified step states its decisions and only the constraints a plausible executor would get wrong; size it to about one function, ordered so none depends on a later one.

Decide in prose, with short pseudocode only where prose cannot settle control flow, ordering, or exit paths, backticking each existing helper and inventing no call; beyond an earned anchored edit, leave target-language code and tests to the executor. Data a validator, loader, or schema reads must pass its acceptance rule, traced from source against the drafted bytes, and match a same-kind sibling's keys. Read [Declared text](declared-text.md) before declaring Exact, Frozen, or Proof run text.

**Probe, don't prototype.** Planner and challenger probe only the current tree: neither applies declared text, writes planned code or tests, or checks a planned end state anywhere, scratch copies and memory included; Blueprint's `check` and seal are not that. Record a spike, the smallest current-tree probe for one question, as a fact. A claim only an end-state run could settle is a labelled prediction, carried when load-bearing by an authored Run, Proof run, or `Red:` with a decided branch for its foreseeable failure. An After implementation Run that settles one checks it on hard inputs and names it on a `Prediction:` line with its fallback, decided in full and touching no declared block, or `stop and return to Blueprint`; it must fail by exit within its Timeout, since a Construct timeout is unsafe. Draft and trim Exact text to fit, measuring the draft, never by applying it; deleting existing rule meaning to fit a budget is a semantic change needing a stated reason.

## Step proof

An existing green check that already exposes the wrong outcome is the step's proof, without `Red:`. Add proof only for a concrete gap or realistic failure, as [Declared text](declared-text.md) directs; a mechanical Exact step may rest on its exact text. Proof has no per-clause quota, and a behavior step stays specified rather than made Exact to avoid proving it. Shape every added or changed test by `temper`'s test design when that skill is installed.

## Conditional branches

Every acceptance condition needs a credible path from the planned state. If the change can foreseeably fail a later gate, establish headroom before seal or author a branch whose measurable trigger leads to already-decided actions, such as exact changes and a rerun; "investigate or replan" is not a branch, and naming a risk does not close it. Resealing during execution is a planning failure unless the repository changed or the contradiction was unknowable. A stop on a failed prediction is the loop working: its amendment plans against the built code with the observed fact in Facts. When a prediction's failure would reshape the design, the first plan builds only the risky slice.

## Verification and completion

A proof that can pass while acceptance remains false rejects nothing. Every authored Run must exit `0` within its Timeout on a correct implementation of this plan alone, and no `Expect:` admits a nonzero exit; report a conditional outcome as a value. Record the current-tree result of any Run reaching beyond the diff (full suites, linters, validators) from a safe probe of the exact command, or a source trace when probing is unsafe, as checkable values, and check each planned file's drafted text against every Run that scans it; narrow a Run failing for reasons the diff does not own to a scope still covering every planned surface, or plan the authorized repair. For a budgeted gate, record measured value and headroom, with a decided branch when the change can consume it. Read [Incomplete gates](incomplete-gates.md) when a gate could end incomplete for an environmental reason.

Author verification against the request's clauses, in README's Run grammar, which `check` enforces. Each `Expect:` states the exact observable result; add a `Timeout:` only when the default is wrong, and a `### Before implementation` baseline only when it earns its cost.

**Verification purity.** Construct stops as `safety-contradiction` when a Run or Proof run changes the Git index, a Git-visible entry, or a plan-bound path (a Location, a Source, or this task's workspace files, ignored or not), so an authored command writes no Git-visible or plan-bound content and nothing in `.git`. Make each observation-only, configured through its own arguments (Construct adds only `PYTHONDONTWRITEBYTECODE=1`), or, by default, a reader of output an Implementation step generates at declared Locations, checked against independent source truth. Establish the write surface from source or a probe of the exact argv with guarded caches absent; a check reading only build output verifies nothing. After a `verification.mutated_workspace` stop, amend per [Earlier plans](earlier-plans.md).

Trace each clause not marked `Owner gate:` to a discriminating check naming how a plausible wrong implementation fails; exercising changed code is not acceptance. Proof relying on prior-run state includes a stale or missing case, and proof covers materially distinct supported branches. The Trace names each clause once, by ID, with the steps and the Run or Proof run that fails without it; mark one only a named owner or human can settle `Owner gate:` naming that owner. Risks / Recovery needs a consequential failure with a real recovery path. Each executable guard an invariant relies on needs a case only it rejects.

## Source and worktree binding

Plan against the exact inspected state. Declare a dirty target you change as an `existing` Location, binding its dirty bytes, and leave unrelated dirty work untouched. Cite decision-critical repository files no step edits as `**Source:**` lines under Facts; the seal binds their bytes and each `new` path's absence, and only that bound state decides freshness, not HEAD movement. Cite only repository files outside the `.first-four-hours/blueprints/` workspace as evidence.

# Validate a repository change

Return to the [contributor guide](README.md) for the change workflow. The [versioning and validation policy](https://github.com/akshay-diwadkar/first-four-hours/blob/main/REPO_VERSIONING.md) owns required proof and its limits. The [ownership manifest](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/test-ownership.json) maps paths to finite profiles, the [runner](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/test_ownership.py) executes them, and the [budget supervisor](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/validation_budget.py) enforces the public deadline and cleanup.

Select validation from the changed surfaces and affected behavior. Domain membership alone never broadens testing.

## Choose the smallest proof

Inspect existing tests and owner profiles first. Reuse sufficient deterministic proof. Add a test only for a named realistic defect or uncovered acceptance behavior, and briefly explain the gap and the wrong result it catches in the PR description.

Skill-specific tests, including integrations, belong under `tests/skills/<skill>/`. Shared tests under `tests/repository/` or `tests/skill_protocol/` protect genuinely common mechanisms. The [testing policy](https://github.com/akshay-diwadkar/first-four-hours/blob/main/REPO_VERSIONING.md) defines the collected-case ceilings per skill, for shared coverage, and for the complete suite, including parametrized rows, as well as the runtime bounds.

A ceiling is not a quota. When slots are full, strengthen an existing coherent scenario or replace lower-value coverage while preserving essential proof. Do not hide independent cases in loops or move skill-specific coverage into the shared allowance. Reason is instruction-only; shared metadata, reference, and authority checks cover it without artificial runtime tests.

## Select, then run

Run the examples below from the repository root after the setup in [Contributing](https://github.com/akshay-diwadkar/first-four-hours/blob/main/CONTRIBUTING.md). They illustrate command syntax, not recorded results. The `origin/main` examples assume that it is the intended, freshly updated comparison base; use the actual base for your branch.

Inspect selection before running the affected profiles:

```bash
python tools/validation/test_ownership.py run --base-ref origin/main --format json --dry-run
```

Run the required change-scoped validation:

```bash
python tools/validation/test_ownership.py run --base-ref origin/main --format json
```

The base-ref command reads changes from the merge base through the current worktree and includes untracked, nonignored additions. Rename and delete sides remain selectable. Account for the complete final diff, including helpers, fixtures, package surfaces, and documentation.

For focused work, select an explicit surface:

```bash
python tools/validation/test_ownership.py run --path docs/README.md --format json
```

`--path` is a focused selection aid; it does not establish that every final changed surface has been covered. Add an exact regression node with `--test` only when existing proof leaves a concrete gap. This retained node illustrates the syntax; it is not an extra check required for every contribution:

```bash
python tools/validation/test_ownership.py run --base-ref origin/main --test tests/repository/test_progressive_disclosure.py::test_reference_checks_reject_broken_skill_docs_and_atlas_links --format json
```

`--test` requires an exact pytest node, not a module path. An owner profile may already include that node; the runner deduplicates the selection.

## Finish required verification

The required run combines the selected owner profiles with the complete repository validator and critical instruction-rule checks. Each live pytest module needs a whole-module owner target, so new cases enter the full gate. The runner collects the selected union once to enforce case limits, then executes it under the supervisor. The [runner source](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/test_ownership.py) owns execution details.

Use the complete union for the final-revision full proof required by policy:

```bash
python tools/validation/test_ownership.py run --all --format json
```

`--all` is used without `--base-ref` or `--path`. A passing full union on the final relevant revision also satisfies the change-scoped requirement. Reuse that proof rather than rerun its checks unchanged.

After a failure or repair, automatically run only invalidated checks and previously unexecuted cases, then obtain the required passing full run for the final relevant revision. Do not add a second broad suite to the repair loop. Ordinary direct pytest invocation and bypassing supervision with private environment markers are unsupported.

## Read the result and recover

A dry run's `plan.valid: true` and empty selection errors establish that the selection is accepted. They do not mean the tests ran.

A passing execution requires successful executed checks and a final `validation-budget` record with `status: passed`, `complete: true`, and a successful worker. A completed pass with `slow: true` remains passing; it exceeded the advisory target. The [policy](https://github.com/akshay-diwadkar/first-four-hours/blob/main/REPO_VERSIONING.md) owns the advisory target and hard deadline, and the [supervisor](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/validation_budget.py) owns enforcement.

Failed, skipped, unexecuted, deadline-exhausted, or cleanup-incomplete work never counts as passing. Keep the actual result and any missing proof in the report. Unknown, deferred, overlapping, unsafe, or policy-drift paths fail closed: repair the actual ownership or policy mismatch before rerunning. Do not use fallback selection.

Run only one bounded validation command in a checkout at a time. A `verification_already_running` result is incomplete: wait for the other command to finish before a later invocation. Do not delete its lock or weaken the check. Retrying an unchanged incomplete command is not evidence of a pass.

## Recover the budget without weakening proof

Use the measured cost of fixtures, subprocesses, and repeated setup to choose a repair. Reduce that work, reuse immutable setup with isolated case copies, or remove or replace demonstrably redundant proof. Preserve essential operations, refusals, installed and integration behavior, and the current supervised runner. A permanent telemetry or benchmark framework is not part of routine validation.

Keep the [maintained ceilings](https://github.com/akshay-diwadkar/first-four-hours/blob/main/REPO_VERSIONING.md). Do not raise deadlines, weaken required proof, or append another broad suite to accommodate growth. Parametrization alone does not save runtime unless setup work is reduced. A `pytest.raises` check protects behavior even without a literal `assert`; blanket documentation-test deletion is likewise unjustified.

The repository uses no live model, provider, or agent harness. Deterministic tests establish the mechanics and evidence they exercise, not semantic scores or universal agent performance.

## Measure guidance and declare readiness

Before editing a skill's `SKILL.md` or owned references, measure current guidance:

```bash
python tools/validation/measure_context_load.py --format json
```

Read each affected skill's `top_level` and `references` metrics from the first stdout line: `measured`, `limit`, and `headroom`. Negative headroom means over budget even though report mode exits zero. For the pass/fail verdict, use:

```bash
python tools/validation/measure_context_load.py --check
```

The [measurement source](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/measure_context_load.py) and [recorded budgets](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/context-load-budgets.json) own these facts. Planning traps in the [versioning policy](https://github.com/akshay-diwadkar/first-four-hours/blob/main/REPO_VERSIONING.md) explain draft `--blueprint` estimation, its Exact-only coverage, and the headroom required before execution. Estimate from the draft without applying it to a copy of the tree.

Remove sediment, consolidate meaning, and move exceptional detail behind precise references. Preserve required meaning and the [pinned instruction clauses](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tests/repository/mandatory_skill_rules.json); do not raise budgets or compress away behavior to fit. The [instruction checker](https://github.com/akshay-diwadkar/first-four-hours/blob/main/tools/validation/instruction_rules.py) already runs through required validation.

A PR is ready for review only with complete required proof, policy-correct versions, affected projections and documentation updated, and remaining owner judgments or limitations disclosed. A machine pass cannot settle the usefulness or factual meaning of authored guidance. Report that distinction honestly.

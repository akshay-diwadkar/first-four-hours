# Repository Versioning and Validation

Read this file before changing skills, packaging, validators, dependencies, runtimes, or release configuration.

## Branch and Release Authority

* Create or switch to a dedicated branch before implementation.
* Never merge a pull request.
* Version only affected skills.
* Determine each version from the final user-visible diff against the merge base.
* Set the version once after the implementation scope is stable.
* Do not increment it again for CI fixes, review rework, or later pre-merge commits unless the required Semantic Versioning level changes.
* If the required level changes, recalculate from the version on the merge base.
* Use the highest-impact applicable change.

## Skill Versions

Changes under `skills/<domain>/<skill>/` use Semantic Versioning:

* **Major:** breaks a previously supported behavior, input, output, workflow, integration, or compatibility guarantee.
* **Minor:** adds a backward-compatible capability.
* **Patch:** corrects behavior or distribution without breaking previously supported use.
* **None:** does not affect observable skill behavior or distribution.

Update only the affected skills' `metadata.version` in `SKILL.md`, and record each changed skill and its new version under `## [Unreleased]` in `CHANGELOG.md`. `VERSION` changes only when a release is prepared (see [Release Metadata](#release-metadata)).

Unmodified skills retain their versions.

Repo-only tests, documentation, formatting, and CI changes require no bump unless they change installation, packaging, release output, or distributed behavior.

If implementation scope is narrowed, lower or remove any provisional bump so the final version accurately represents the delivered change.

## First Four Hours v1 Baseline

The First Four Hours baseline reset `VERSION`, every skill's `metadata.version`, and every contract version the repository owns to `1.0.0` once, as one breaking change. Keep these values at `1.0.0` until the First Four Hours baseline is established; the rules above then apply from v1. Old internal versions are not accepted for compatibility: artifacts sealed under them are resealed by their producing skill. The first release publishes the `## [Unreleased]` entry in `CHANGELOG.md` as `1.0.0` without an increment.

## Contract Versions

A skill's version is the version of everything it owns. An artifact, handoff, receipt, bundle, template, or state file that records a version records its producing skill's `metadata.version`. A consumer accepts a recorded `MAJOR.MINOR.PATCH` version that shares the major of the producer version it was built against and refuses every other value, so a breaking format change is a major skill bump. Do not add a version to an artifact that has none.

When a skill's version changes, set every contract version constant and template value that skill owns to the new version, including vendored and synchronized copies, and keep each consumer's built-against version on the producer's major. `validate_repository.py` lists these declarations and fails when one disagrees with its owning skill or when that skill's `metadata.version` is not a plain `MAJOR.MINOR.PATCH` version its consumers accept.

Formats with no owning skill keep `1.0.0` under their canonical source: `tools/skill_protocol/runtime.py` owns `protocol_version`, whose consumers accept the same major; `tools/validation/test_ownership.py` owns the ownership manifest and selection record, `tools/validation/measure_context_load.py` the context budgets, and `tools/validation/validate_repository.py` `invocation-policy.json`, each requiring exactly its current value.

## Release Metadata

Each version has one owner. A skill's `metadata.version` in `SKILL.md` is that skill's version. `VERSION` holds the repository release version: one `MAJOR.MINOR.PATCH` value for the release as a whole, never a list of skill versions. `CHANGELOG.md` is the one release history. It follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/): newest release first, an `## [Unreleased]` section for merged changes not yet released, and only the categories that have entries (Added, Changed, Deprecated, Removed, Fixed, Security).

* A change that bumps a skill version, or changes installation, packaging, release output, or distributed behavior, adds a short user-visible entry under `## [Unreleased]`. An entry for a skill names the skill and its new version. An entry for a breaking change states what users must do.
* To prepare a release, set `VERSION` from the last released version by the highest-impact change among the `## [Unreleased]` entries, using the Major, Minor, and Patch rules above. Rename `## [Unreleased]` to `## [<VERSION>] - <YYYY-MM-DD>` with the actual release date, add a new empty `## [Unreleased]` above it, and tag the release `v<VERSION>`. The GitHub release notes reuse that changelog entry.
* The README release badge reads the latest GitHub release; it holds no version to update.
* Change a requirements file only when the packages it declares change. Each skill's `requirements.txt` declares only that skill's packages, so the skill installs alone. `tools/validation/release-requirements.txt` declares the validation environment: it includes the skill requirements files and adds the validation tools.

## Validation

The one required validation command names the base it is measured against:

```bash
python tools/validation/test_ownership.py run --base-ref <base> --format json
```

It runs the owner profiles for changed paths plus the complete repository validator and critical instruction-rule checks under one supervised deadline: a run over several test files first collects the whole selection once to enforce the case limits, then runs the files in at most four concurrent pytest processes. The full union covers every retained pytest module without global pytest discovery. Add the exact regression node whose failure exposes the changed behavior in the same run:

```bash
python tools/validation/test_ownership.py run --base-ref <base> --test <tests/path.py::test_name> --format json
```

Use the full union once when full repository proof is required:

```bash
python tools/validation/test_ownership.py run --all --format json
```

A passing full union for the final revision also satisfies the change-scoped requirement. Do not repeat its checks. After a repair, run only invalidated checks and previously unexecuted cases automatically. Obtain one passing full run for the final revision; do not repeat an unchanged passing run.

Each run uses a private temporary root and removes it before reporting success; the finite runner does not read or write pytest's persistent cache.

The owner manifest is the source of truth for path ownership and routine test profiles. Unknown, deferred, overlapping, unsafe, or policy-drift paths fail closed. Each live pytest module in the inventory must be a whole-module target in at least one profile, so adding a case to a registered module automatically adds it to the full gate. Profiles may share test dependencies; their union executes each case once. Deleted and renamed paths remain selectable by their Git diff sides. Editing a pytest module selects its owner's profile; it does not additionally require naming a node from that module. Python support files such as helpers and `conftest.py` still require valid ownership and syntax, and select their owner's profile, but the selector does not prove that any selected target imports, reads, or executes them. When a support-file behavior matters to an acceptance condition, identify its actual consumer from source or add/select an exact regression for the concrete gap. Use `--test` to select an exact existing regression or a new one when the change exposes a concrete coverage gap. It does not require a new test for every change. A successful routine run ends ordinary verification; run a bounded optional diagnostic only for a named risk.

### Adding or changing tests

Inspect the current tests and owner profiles first. Add a test only for a specific realistic defect or uncovered acceptance condition; explain that gap and the incorrect behavior it catches briefly in the PR description. No separate justification document is needed. Documentation, formatting, and mechanical refactors do not automatically require new tests.

**Three tests is a ceiling, not a quota.** Do not manufacture scenarios to fill slots. When a skill already has three collected cases, strengthen an existing coherent scenario or replace lower-value coverage. Never routinely append a fourth case, raise the caps, extend the timeout, or move skill coverage into the shared allowance. If essential coverage cannot fit, report the concrete conflict instead of silently cutting protection or hiding independent cases in loops.

Use the slots for actual operations and important safety boundaries. Assert observable behavior: a valid artifact, correct operation, preserved protected work, an unauthorized action refused without writes, or stale evidence rejected. Keep independently meaningful scenarios separately collected.

Avoid implementation-detail mocks, repeated successful workflows, incidental wording or formatting checks, fixture/specimen inventories, catalog completeness, exhaustive schema permutations, and speculative edge cases. Shared checks must prove a repository-wide or common protocol mechanism, not provide extra skill coverage. Mock external providers when needed, not the operation or result whose correctness the test claims.

Prefer actual callable functions and minimal deterministic fixtures. Use real subprocesses when isolation, standalone command wiring, authored execution, or process containment is the behavior being proved. Reuse immutable setup with isolated case copies and delete fixtures/helpers that surviving cases no longer need. A new pytest module requires a whole-module owner target.

The complete repository suite must actually pass within 120 seconds, including startup, selection, collection, execution, cleanup, and reporting. Aim for a healthy pass within 80 seconds. Testing and repairs proceed automatically; stopping at the deadline is incomplete verification, never a passing result.

## Planning traps

Planners read this list while grounding a change in this repository:

* Context budgets: before changing agent-loaded guidance (`SKILL.md` or `references/`), read each skill's `measured`, `limit`, and `headroom` for `top_level` and `references` from the first stdout line of `python tools/validation/measure_context_load.py --format json`; `--check` prints only the verdict, and negative headroom means over the limit. Measure a draft without building it or writing a helper script: `python tools/validation/measure_context_load.py --blueprint .first-four-hours/blueprints/<task>/blueprint.md` prints on its first stdout line, for each skill whose guidance a `**Exact:**` block edits, each metric's `measured`, `delta` (drafted minus replaced tokens; a new file adds its whole text), `estimated`, `limit`, `headroom`, `spans`, and `fits`. It reads only the draft's Implementation instructions and exits 1 when they do not parse or a block edits a skill with no recorded budget. Splice boundaries can shift each edited span's count by a few tokens (at most 3 observed), so `fits` requires at least 4 tokens of headroom per edited span. It counts only Exact blocks: leave headroom for any specified (non-Exact) guidance edit. Never apply a draft to a copy of the tree to measure it.
* Whole-module ownership ([Adding or changing tests](#adding-or-changing-tests)): a new pytest module needs its own owner target; pinning an old node cannot cover later cases.
* Full skill suites ([Suite size cap](#suite-size-cap)): strengthen or replace a case, never add a fourth.
* Proof runs and `Red:`: `test_ownership.py` packs whole selected test files into at most four pytest processes, each run with `-x`, so after a process's first failing case its remaining cases, possibly in other files, appear in `unverified_cases`, not `failed_cases`. A skipped case never completes, so it is reported unverified and the run does not pass. `--base-ref` and `--path` select each changed path's whole owner profile, which absorbs any `--test` node in it. A Proof run that declares `Red:` therefore names its one regression node with `--test` and neither `--base-ref` nor `--path`: it then runs only that node and `tests/repository/test_routine_validation.py::test_live_repository_metadata`, in separate processes unless the node is in that same file, where both share one `-x` process and a failure of whichever runs first leaves the other unverified; the red is that node in `failed_cases`. A test that runs a Python script through `tools/validation/python_test_support.py::run_python` executes it in the test's own interpreter, so its failure can surface with a different exit code or diagnostic than in a real subprocess. A platform-bound regression branches on the platform inside its body, as `tests/skills/blueprint/test_blueprint_contract.py` does, never by skipping.
* Selection probes: add `--dry-run` to an authored `test_ownership.py run` command to probe its selector without running tests. The first stdout line is the `"event":"plan"` record: `"valid":true` with empty `errors` means the runner accepts the selection, and a rejected selector, such as `--test` given a file instead of an exact pytest node, is named in `errors` and exits nonzero. A dry run still takes the verification lock: a first line that is a `validation-budget` record with `reason` `verification_already_running` is an incomplete probe, not a rejection, so repeat it once no other validation runs. A node the plan creates does not exist yet, so probe an existing node in the same form instead.
* Break-the-code checks: prefer an input fixture that exposes the named wrong outcome. Otherwise write one, only for the planning contract's named gap, as assertions inside the owned scenario whose assertion it guards, after, in execution order, any assertion that exposes the `Red:` defect (a case stops at its first failing assertion); it is not a separate case. Load a mutated in-memory or `tmp_path` copy under a unique module name and call that module's own function on it directly; a mutation reachable only through another module's import is not plannable this way. Never patch the shared module; nested validation commands are unsupported. First assert the mutation anchor occurs exactly once, so a refactor fails loudly; this is the one accepted exception to avoiding implementation-mirroring assertions.
* Blueprint and Construct each vendor `scripts/blueprint_runtime.py` with no sync tool; plan identical edits to both copies. The Construct lifecycle test fails when they differ, but a change-scoped run of the Blueprint copy alone does not select it, so a plan changing either copy authors `run --all` or names that lifecycle node with `--test`.
* Runtime discovery: `tools/validation/validate_runtime_discovery_policy.py`, run by `validate_repository.py`, scans every non-Atlas `skills/<domain>/<skill>/scripts/*.py` for repository discovery (its `FORBIDDEN` patterns: `git ls-files`, `git grep`, `rglob`, a `**/` glob, `os.walk`, recursive `rg`/`grep`). Each match fails unless `tools/validation/runtime-discovery-exceptions.json` approves `<path>:<pattern name>`.
* Protocol path inputs: `tools/skill_protocol/runtime.py` resolves every `path` input, following links, before the skill script receives it (an existing path with `resolve(strict=True)`, a `future` path through `_safe_future_path`'s nearest existing ancestor). A skill-script check on how a path was spelled, such as a link or relative form, never sees that spelling through the CLI.
* The first bounded validation command in a checkout (any `tools/validation/` script run through `validation_budget.bounded_main`) creates the ignored `.scratch/verification-budget.lock`. Construct's mutation guard binds ignored files, so a Run that creates it stops as unsafe: run `python tools/validation/validate_repository.py` once as a planning probe in the checkout Construct will use, running it there if that is a different checkout, and record in Current State that the lock exists.
* Every bounded command takes that lock, so a second validation command running in the same checkout makes the next one exit with `reason` `verification_already_running`. It comes only from concurrency, never from planned code, so it is not an environment-sensitive gate to narrow, and no Run other than the final `run --all` may declare it. Run no other validation command in the checkout while Construct executes. If contention still occurs on any other bounded command, including a Proof run, stop the invocation without rerunning and return the final record to the caller as evidence of an environmental block, not a code failure; any further execution is a fresh Construct invocation once no other validation runs.
* `run --all` is load-sensitive against its deadline. Its declarable `Incomplete:` signature is environmental: lock contention (`reason` `verification_already_running`, another command holds the lock), or deadline exhaustion with `reason` `work_deadline` or `report_deadline`, an empty `failed_cases` list, and either `worker_exit` null or `worker_exit` 0 with no `unverified_cases`. Other reasons, a nonzero `worker_exit`, and unverified cases after a clean worker exit can come from planned code. `report_deadline` masks earlier reasons, and a deadline cannot tell host load from a planned slowdown, hang, or process leak, so whether the deadline outcome may be declared follows the rule in `skills/workbench/blueprint/references/incomplete-gates.md`. Leave that Run's `Timeout:` unset or at least 240 seconds, well past the 120-second public deadline.

## Suite size cap

The permanent testing ceilings are **three collected cases per skill**, **12 shared cases**, and **48 cases in the complete suite**. Parametrized rows and skill-specific integration scenarios count. These are execution counts, not function counts. Normal test changes may not raise any ceiling, hide independent inputs in loops/helpers, or relabel skill-specific cases as shared.

All skill-specific tests, including integrations, must live under `tests/skills/<registered-skill>/`. Shared checks belong only under `tests/repository/` or `tests/skill_protocol/`. Live pytest modules under `tests/integration/`, `tests/shared/`, directly under `tests/`, or under unknown skill names are refused. The same classifier enforces these locations during ownership inventory validation and pytest collection; there is no default shared bucket. Historical deleted/renamed paths remain selectable against the base and do not become prohibited live modules merely because they existed there.

`tools/validation/test-ownership.json` declares `limits.max_gated_items`, which must be a positive integer no greater than 48. The collection hook independently enforces three per skill and 12 shared, before any test body executes. Missing or invalid limits fail closed. Every retained module must be covered by a whole-module owner target so new cases cannot remain outside the full gate.

Repository pytest must use the supervised ownership runner. The root test hook rejects ordinary direct pytest invocation before execution, preventing accidental bypass of the deadline and collection rules. Do not set the supervisor's private environment markers yourself or disable its hooks.

Each executable skill uses at most three independently meaningful scenarios for its operations and safety boundaries, preserving the retained validity core. Reason is instruction-only and is checked through shared repository metadata, reference, and authority validation. Do not pad it with artificial runtime tests. These checks prove the tested operations and invariants, not universal agent quality or every supported edge.

Keep only minimal deterministic data required by retained scenarios. Delete replaced tests, unused helpers, duplicate integrations, specimen bookkeeping, and fixture corpora that no longer serve those scenarios. Do not preserve them as hidden opt-in suites. Secondary coverage is intentionally retired and must be identified in the deletion commit.

Critical instruction-only safety rules have one home in `tests/repository/mandatory_skill_rules.json`. The single live repository case checks their presence and discoverability with normalized whitespace. That is not a claim of agent compliance or sandbox enforcement.

## Time budgets and verdicts

Every complete repository verification pass has a **120-second maximum**. The combined skill and shared tests must finish within that limit, including startup, selection, collection, execution, cleanup, and reporting. Dependency preparation is separate. Aim for a healthy full pass within 80 seconds.

Testing, repairs, and subsequent runs proceed automatically without approval. There is no cumulative task allowance, reservation ledger, renewal command, or permission prompt. Old local allowance records have no effect on verification.

The supervisor uses a nonblocking kernel lock to permit one command at a time. It stops test work at 110 seconds and reserves the remaining ten seconds for process-tree termination, cleanup, and reporting. Deadline exhaustion is incomplete verification; unexecuted or skipped checks never count as passing. Success requires completed passing checks and confirmed cleanup. Stopping at the deadline alone does not satisfy the requirement for a passing full suite.

Consume the final `event: validation-budget` record as the authoritative verdict. It names the canonical `repo_root` and ownership `manifest` and reports failed and unverified cases. Intermediate plan and pytest execution records do not prove verification completeness. The ownership CLI always uses its own checkout and manifest; root and manifest overrides are unsupported. Malformed case reports are incomplete verification and are removed before reporting.

Prioritize actual successful operations and meaningful unsafe-state refusals. Remove unnecessary fixture bookkeeping, duplicate workflows, syscall-detail mocks, and implementation-mirroring assertions. Reuse immutable setup with isolated case copies; use filesystem fixtures when Git identity is not the behavior under test. Retain real subprocesses for standalone command wiring, authored verification, and process containment.

Use built-in pytest duration output from the normal pass to identify expensive setup. Do not add a benchmark framework or extend the deadline. After repairs, run affected checks automatically and obtain one final passing full run. A passing full suite also satisfies change-scoped verification.

Nested public validation commands remain unsupported. Use direct check functions inside the supervised process. Do not disable collection or deadline hooks to obtain a passing result.

Supported optional commands are:

```bash
python tools/validation/measure_context_load.py --check
python tools/validation/measure_context_load.py --format json
python tools/validation/measure_context_load.py --blueprint <draft>
python tools/validation/validate_repository.py
python tools/validation/run_mypy.py --skill <name>
python tools/validation/run_mypy.py --test <tests/path.py>
python tools/validation/run_mypy.py --path <source.py>
python tools/validation/run_mypy.py --repository-tooling
python tools/validation/validate_skills_cli_install.py --agent <agent>
python tools/validation/validate_claude_plugin_install.py
```

The mypy command requires an explicit positive scope. The Skills CLI installation check uses `npx` and registry access. The Claude Code plugin installation check needs the `claude` CLI and installs into a temporary Claude Code configuration. After a repair, rerun only the invalidated authored command and report the scope it checked. Do not invoke global pytest discovery as another required suite.

Before declaring repository readiness, install release requirements and run the required command above. Run repository validation when repository metadata, package rules, release inputs, or sync contracts change. Run collection installation for an agent when package distribution changes, and the Claude Code plugin installation check when the marketplace, plugin grouping, or skill membership changes. No skill version bump is required for repository-only tests, validators, documentation, or release dependency changes unless the distributed package or behavior changes.

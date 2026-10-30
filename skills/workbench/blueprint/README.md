# Blueprint

`blueprint` turns an authorized request into one sealed, implementation-complete `.first-four-hours/blueprints/<task-slug>/{request.md,blueprint.md}`. [SKILL.md](SKILL.md) owns the planning workflow; this file owns the workspace commands and the sealed shape. Readiness relies on grounded agent judgment over executable contracts and evidence; the seal verifies only artifact shape and binding.

Prepare the task-scoped workspace, which freezes the resolved request bytes into the sibling `request.md`, writes the initial `blueprint.md` scaffold from the task name, and returns canonical paths; preparation never replaces an existing `blueprint.md`. In a Git repository it also adds, when missing, the `.git/info/exclude` rule that keeps `.first-four-hours/blueprints/` ignored. The `--request-file` input is pre-planning input, not planning output: pass an upstream handoff where it was sealed, and write a request Blueprint resolves (user answers, an Ideate selection, an architecture source declaration) outside the repository, which stays read-only apart from the writes `SKILL.md` lists:

```bash
python scripts/prepare_blueprint_workspace.py \
  --repo-root /absolute/repo \
  --request-file /absolute/authoritative-request.md \
  --task-name "<task name>"
```

Author only `blueprint.md`, in place with ordinary file edits: quote each replaced text from the current file and let `check` catch anchor mistakes. Never write a helper script, generator, or scratch copy to produce the plan. Check it at any point with the same inputs and `check` in place of `run`: it reports exactly the diagnostics the seal would and writes nothing, and its `result` says `"check_only": true`, so a passing check is not a seal. Run `check` and `run` only with `--format json` as shown: human-format output is unsupported for them because it prints the same `complete` status for a passing check and a seal. Then seal it with a provider-free mechanical proof:

```bash
python scripts/cli.py --repo-root /absolute/repo \
  --input request_file=/absolute/repo/.first-four-hours/blueprints/<task-slug>/request.md \
  --input draft_file=/absolute/repo/.first-four-hours/blueprints/<task-slug>/blueprint.md --format json run
```

A successful seal's `result.blueprint_path` is the sealed file's absolute path; its frozen `request.md` is the sibling. The envelope lists no `artifacts`.

A sealed Blueprint is immutable; progressed execution fails closed, so request meaning changes need a fresh draft and workspace.

Before repairing a diagnostic, read the reference that owns it: [Declared text](references/declared-text.md) for `block.*`, `frozen.*`, `declaration.malformed`, and a `proof.*` about an instruction's Proof run or `Red:` line; [Incomplete gates](references/incomplete-gates.md) for `verification.incomplete.*`; and [Seal receipts](references/seal-receipts.md) for `receipt.*` and a `proof.*` about the Blueprint proof or its receipts. Every other diagnostic's rule is in this file or the [planning contract](references/planning-contract.md).

## Sealed contract

Line 1 is the HTML-comment contract marker `blueprint-contract: <version>`, where preparation writes Blueprint's own version and any version with the same major is accepted; the H1 title follows as the next non-empty line. The document holds:

- `Goal` — only a short approvable summary (approach, load-bearing invariants, what changes, what does not, main risks, user-accepted gaps), with no separate list of what must be true when the work is done;
- `Current State` — only implementation-relevant repository facts and `**Source:**` citations of existing decision-critical repository files;
- `Implementation` — ordered `### N.` instructions, each declaring one or more `**Location:**` lines, each citing exactly one target (one backticked `path` or `path::symbol` per line) followed by its explicit `**State:** existing|new|deleted` line, plus exact changes, preservation rules, and each decision in the form the [planning contract](references/planning-contract.md#implementation-instructions) requires;
- `Verification` — `Run:` commands with observable `Expect:` results, each of which must exit `0` on a correct implementation, an optional `Incomplete:` line after an `Expect:` naming an environmental incomplete outcome, plus an optional before-implementation baseline only when it earns its cost and still exits `0`; a pre-change red observation is `Current State` evidence, never an authored command;
- `Completion Conditions` — each required outcome's one statement, as a concrete example ending `Shown by` its proof in the form the [planning contract](references/planning-contract.md#verification-and-completion) sets; a condition only a named owner or human can settle starts with `Owner gate:` and names that owner instead, and Construct reports it as pending, never attempting or claiming it; and
- `Risks / Recovery` — only when a real recovery path is earned.

An instruction may also declare step proof that Construct checks mechanically: `**Exact:**` textual data or anchored edits, or `**Frozen:**` proof data, for one of its own Location paths, and at most one `**Proof run:**` with its `Expect:`. The [planning contract](references/planning-contract.md) decides when each is earned, and Declared text when a `Red:` or break-the-code check is. When declaring any of them, read [Declared text](references/declared-text.md) for their grammar, reserved-label spelling, and the seal's simulation. Before declaring an `Incomplete:` outcome, read [Incomplete gates](references/incomplete-gates.md).

Sealing appends two generated receipts as the final two lines; never author a receipt-prefixed line. [Seal receipts](references/seal-receipts.md) owns their format, the proof Construct consumes, and the runtime's list of checks.

The seal enforces authored State: an `existing` or `deleted` target must be a repository-contained regular file and a `new` target must be absent (a broken symlink counts as occupied), so a mistyped path fails closed instead of silently becoming a create. A `deleted` target's spelling crosses no link or alias (`location.deleted.link`), because Construct proves that spelling absent. A `**Source:**` naming a deleted file through any spelling, link, or case or Unicode normalization variant the filesystem folds to the same directory entry fails as `source.deleted`; a hardlinked twin is a separate surviving entry and stays citable.

Exactly one implementation-complete plan per task directory. The document must be simple to consume: no planner transcript, exploration report, challenge report, or internal reasoning enters it.

Verification commands keep only mechanics that independently pay rent: one backticked exact command per `Run:` (the executor runs it verbatim from the repository root); chaining rejection because one `Run` is one command with one observable `Expect`; direct rejection of recognizable shell-interpreter command modes so a `Run` remains one directly executable argv command; a narrow directly recognizable set of mutating Git subcommands (`add`, `apply`, `checkout`, `cherry-pick`, `clean`, `commit`, `merge`, `mv`, `push`, `rebase`, `reset`, `restore`, `revert`, `rm`, `stash`, `switch`, `update-index`) kept out of verification so proof never mutates history, publication, index, or worktree; placeholder rejection so ceremony cannot pass shape; and an optional positive `Timeout:` (default 900 seconds) that bounds proof execution. `### Before implementation` stays optional when a baseline earns it, and its Runs exit `0` like every other authored Run; `### After implementation` is required.

Contract markers and receipts of another major, the retired `plan-contract` marker, sidecar filenames, and retired `**Evidence:**` / `**Locator:**` declaration labels fail closed without translation.

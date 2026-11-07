# Blueprint

`blueprint` turns an authorized request into one sealed, implementation-complete `.first-four-hours/blueprints/<task-slug>/{request.md,blueprint.md}`. [SKILL.md](SKILL.md) owns the planning workflow; this file owns the workspace commands and the sealed shape.

Prepare the task-scoped workspace, which freezes the resolved request bytes into the sibling `request.md`, writes the initial `blueprint.md` scaffold from the task name, and returns canonical paths; preparation never replaces an existing `blueprint.md`. The `--request-file` input is pre-planning input, not planning output: pass an upstream handoff where it was sealed, and write a request Blueprint resolves (user answers, an Ideate selection, an architecture source declaration) outside the repository, which stays read-only apart from the writes `SKILL.md` lists. A sealed Assess `assessment.md` with result `findings` is such a handoff: pass `--input handoff_item=1,3` to every `check` and `run` to plan only those findings, all when omitted. Its selected findings are the request's clauses and settled evidence: cite none again in Current State, and re-confirm only that each defect still occurs in the current tree:

```bash
python scripts/prepare_blueprint_workspace.py \
  --repo-root /absolute/repo \
  --request-file /absolute/authoritative-request.md \
  --task-name "<task name>"
```

Author only `blueprint.md`, with ordinary file writes and edits, never a shell command. Write the first full draft in one write over the prepared scaffold, keeping its fixed shell lines unchanged; afterwards repair with targeted edits that quote each replaced text from the current file, or rewrite the whole file in one write when a repair touches most of it, and let `check` catch anchor and shell mistakes. Every turn re-reads your whole context, so filling the plan through a long series of small edits multiplies its cost. Never write a helper script, generator, or scratch copy to produce the plan. Check it at any point with the same inputs and `check` in place of `run`: it reports exactly the diagnostics the seal would and writes nothing, and its `result` says `"check_only": true`, so a passing check is not a seal. Run `check` and `run` only with `--format json` as shown: human-format output is unsupported for them because it prints the same `complete` status for a passing check and a seal. Then seal it with a provider-free mechanical proof:

```bash
python scripts/cli.py --repo-root /absolute/repo \
  --input request_file=/absolute/repo/.first-four-hours/blueprints/<task-slug>/request.md \
  --input draft_file=/absolute/repo/.first-four-hours/blueprints/<task-slug>/blueprint.md --format json run
```

A successful seal's `result.blueprint_path` is the sealed file's absolute path; its frozen `request.md` is the sibling. The envelope lists no `artifacts`.

For a replan, `carryover` reports an earlier sealed plan's bound files, writing nothing and refusing an edited plan:

```bash
python scripts/cli.py --repo-root /absolute/repo --input predecessor_file=/absolute/earlier/blueprint.md --format json carryover
```

`result.entries` gives each Source's and existing or deleted Location's `path`, `role`, and `status`: `unchanged`, `changed`, or `missing`.

A sealed Blueprint is immutable; progressed execution fails closed, so request meaning changes need a fresh draft and workspace.

Each diagnostic names its fix; before repairing one, read its rule's owner: [Declared text](references/declared-text.md) for `block.*`, `frozen.*`, `declaration.malformed`, and a `proof.*` about an instruction's Proof run or `Red:` line; [Incomplete gates](references/incomplete-gates.md) for `verification.incomplete.*`; otherwise this file or the [planning contract](references/planning-contract.md).

## Sealed contract

Line 1 is the HTML-comment contract marker `blueprint-contract: <version>`, where preparation writes Blueprint's own version and any version with the same major is accepted; the H1 title follows as the next non-empty line. The document holds:

- `Goal` — only a short approvable summary (approach, load-bearing invariants, what changes, what does not, main risks, user-accepted gaps), with no separate list of what must be true when the work is done;
- `Current State` — only implementation-relevant repository facts and `**Source:**` citations of existing decision-critical repository files;
- `Implementation` — ordered `### N.` instructions with their `**Location:**` and `**State:**` declarations, exact changes, preservation rules, and each decision in the form the [planning contract](references/planning-contract.md#implementation-instructions) requires;
- `Verification` — `Run:` commands with observable `Expect:` results, an optional `Incomplete:` line after an `Expect:`, and an optional `### Before implementation` baseline, under the Run rules below;
- `Completion Conditions` — each required outcome's one statement, as a concrete example ending `Shown by` its proof, or an `Owner gate:` condition, in the form the [planning contract](references/planning-contract.md#verification-and-completion) sets; and
- `Risks / Recovery` — only when a real recovery path is earned.

An instruction may also declare step proof that Construct checks mechanically: `**Exact:**` or `**Frozen:**` text for one of its own Location paths, and at most one `**Proof run:**`. The [planning contract](references/planning-contract.md)'s Step proof decides when step proof is earned; [Declared text](references/declared-text.md) owns the rest.

Sealing appends two generated receipts as the final two lines; Construct consumes them. Never author, move, or edit a receipt-prefixed line.

Exactly one implementation-complete plan per task directory. The document must be simple to consume: no planner transcript, exploration report, challenge report, or internal reasoning enters it.

Each `Run:` holds one backticked exact command with no placeholder and none of the mutating Git subcommands `add`, `apply`, `checkout`, `cherry-pick`, `clean`, `commit`, `merge`, `mv`, `push`, `rebase`, `reset`, `restore`, `revert`, `rm`, `stash`, `switch`, or `update-index`, so proof never mutates history, publication, index, or worktree. An optional positive `Timeout:` (default 900 seconds) bounds proof execution, and `### After implementation` is required. The planning contract's [Verification and completion](references/planning-contract.md#verification-and-completion) owns every other Run rule.

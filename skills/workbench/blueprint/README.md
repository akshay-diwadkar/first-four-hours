# Blueprint

`blueprint` turns an authorized request into one sealed, implementation-complete `.first-four-hours/blueprints/<task-slug>/{request.md,blueprint.md}`. [SKILL.md](SKILL.md) owns the planning workflow; this file owns the every-run workspace commands and the sealed shape.

Prepare the task-scoped workspace, which freezes the resolved request bytes into the sibling `request.md`, writes the initial `blueprint.md` scaffold from the task name, and returns canonical paths; preparation never replaces an existing `blueprint.md`. The `--request-file` input is pre-planning input, not planning output: pass an upstream handoff where it was sealed, and write a request Blueprint resolves (user answers, an Ideate selection, an architecture source declaration) outside the repository, which stays read-only apart from the writes `SKILL.md` lists. Assess and Temper handoffs pass `handoff_item` to every `check` and `run` per [Architecture intake](references/architecture-intake.md#assessment-and-test-audit-handoffs). Prepare with:

```bash
python scripts/prepare_blueprint_workspace.py \
  --repo-root /absolute/repo \
  --request-file /absolute/authoritative-request.md \
  --task-name "<task name>"
```

Author only `blueprint.md`, with ordinary file writes and edits, never a shell command. Write the first full draft in one write over the prepared scaffold, keeping its fixed shell lines unchanged; afterwards repair once, in one consolidated set of targeted edits that quote each replaced text from the current file, or one whole-file write when the repair touches most of it, and let `check` catch anchor and shell mistakes. Never write a helper script, generator, or scratch copy to produce the plan. Check it at any point with the same inputs and `check` in place of `run`: it reports exactly the diagnostics the seal would and writes nothing, and its `result` says `"check_only": true`, so a passing check is not a seal. Run `check` and `run` only with `--format json` as shown: human-format output is unsupported for them because it prints the same `complete` status for a passing check and a seal. Then seal it with a provider-free mechanical proof:

```bash
python scripts/cli.py --repo-root /absolute/repo \
  --input request_file=/absolute/repo/.first-four-hours/blueprints/<task-slug>/request.md \
  --input draft_file=/absolute/repo/.first-four-hours/blueprints/<task-slug>/blueprint.md --format json run
```

A successful seal's `result.blueprint_path` is the sealed file's absolute path; its frozen `request.md` is the sibling. The envelope lists no `artifacts`.

Replans, Construct-stop amendments, and request changes: [Earlier plans](references/earlier-plans.md#commands).

Each diagnostic names its fix; before repairing one, read its rule's owner: [Declared text](references/declared-text.md) for `block.*`, `frozen.*`, `trace.*`, `goal.tier`, `plan.size`, `declaration.malformed`, and a `proof.*` about an instruction's Proof run or `Red:` line; [Incomplete gates](references/incomplete-gates.md) for `verification.incomplete.*`; otherwise this file or the [planning contract](references/planning-contract.md).

## Sealed contract

Line 1 is the HTML-comment contract marker `blueprint-contract: <version>`, where preparation writes Blueprint's own version and any version with the same major is accepted; the H1 title follows as the next non-empty line. The document holds:

- `Goal` — a few sentences: approach, load-bearing invariants, scope, main risk, user-accepted gaps, and one `**Tier:** quick`, `standard`, or `critical` line;
- `Facts`, optional — only facts the executor cannot see by opening the files it edits (probe results, budgets and headroom, consumers elsewhere, traps, user answers) and `**Source:**` citations of decision-critical files no step edits;
- `Decisions`, optional — numbered non-obvious choices, each with its reason;
- `Implementation` — ordered `### N.` instructions with their `**Location:**` and `**State:**` (`new`, `existing`, or `deleted`; a removed file is `deleted`, not a `**Source:**`) declarations and only what two faithful executors could do differently, in the form the [planning contract](references/planning-contract.md#implementation-instructions) requires;
- `Verification` — `Run:` commands with observable `Expect:` results, an optional `Incomplete:` line after an `Expect:`, and an optional `### Before implementation` baseline, under the Run rules below; `V1` names the first Run in this section, `V2` the second;
- `Trace` — one `- R1 → 2, 3 · V1` line per request clause: its ID, the steps that carry it, and the Run (`V<n>`) or step Proof run (`P<step>`) that fails without it, or `Owner gate: <owner>` for one only a named owner can settle, with an optional note after an em dash; `check` refuses an item citing no step or authored proof, and a request clause numbered `R<n>` with no item; and
- `Risks / Recovery`, optional — only when a real recovery path is earned.

The whole plan stays within its tier's budget: 6KB for Quick, 12KB for Standard, 20KB for Critical.

An instruction may also declare text that Construct applies and checks mechanically: `**Exact:**` for a new file, `**Edit:**` or `**Replace:**` for an existing one, their `**Frozen:**` forms for proof text, all for its own Location paths, and at most one `**Proof run:**`. The [planning contract](references/planning-contract.md)'s Step proof decides when step proof is earned; [Declared text](references/declared-text.md) owns the rest.

Sealing appends two generated receipts as the final two lines; Construct consumes them. Never author, move, or edit a receipt-prefixed line.

Exactly one implementation-complete plan per task directory. The document must be simple to consume: no planner transcript, exploration report, challenge report, or internal reasoning enters it.

Each `Run:` holds one backticked exact, direct command: no placeholder, chaining, shell interpreter, or mutating Git subcommand (`add`, `apply`, `checkout`, `cherry-pick`, `clean`, `commit`, `merge`, `mv`, `push`, `rebase`, `reset`, `restore`, `revert`, `rm`, `stash`, `switch`, or `update-index`, which `check` refuses as `verification.git.mutation`), so proof never mutates history, publication, index, or worktree. An `Expect:` follows each Run, with an optional positive `Timeout:` (default 900 seconds) between them, and `### After implementation` is required. The planning contract's [Verification and completion](references/planning-contract.md#verification-and-completion) owns every other Run rule.

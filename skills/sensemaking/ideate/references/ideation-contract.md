# Ideation Contract

Exact `ideation.md` format. Python enforces structure and syntax only; idea quality, relevance, novelty, and truthful prose remain agent obligations.

## Structure

```text
# Ideation: <goal>
## Goal
## What to do
## Viable options
## What would change the answer
## Exploration
## Evidence
## Suggested follow-up   ← omit when absent
```

Title first line with non-empty goal. Headings in canonical order, once each. Required records are the whole floor: add another line only when a consumer acts on it. Write headings, labels, and values for a reader who has never seen this contract: plain words, no internal codes.

## Deterministic rules

### Goal

Required non-empty fields:

```text
- Goal:
- Decision criteria:
- Scope / non-goals:
- Already known:
```

`Already known:` names what the user already knows, has tried, or ruled out, and the answers anyone gives first: the bar an option must clear to count as new.

### What to do

The decision section: a reader who knows nothing of this format acts from it alone. Two required fields:

```text
- Outcome: recommended direction | run an experiment first | research limit reached
- Final choice: yours to make | made by you — <choice; source> | delegated — <scope; source>
```

Agent-owned:
- `recommended direction` → evidence/authority supports a recommendation for the next intended commitment, whether that is an alternative, a combination of alternatives, or a coherent causal/dependency path. It cannot rest on an unverified hypothesis or empty evidence.
- `run an experiment first` → one testable observation could materially change the conclusion or next commitment before stronger commitment.
- `research limit reached` → insufficient coverage for a defensible stronger outcome.

`Final choice:` records who makes the final choice; it never restates the recommendation:
- `yours to make` → the user still chooses. The recommendation is advice, not approval or implementation authority.
- `made by you — <choice; source>` → the user explicitly chose before sealing; cite where (for example a contextual evidence row) and do not ask again.
- `delegated — <scope; source>` → the user explicitly delegated the final choice; Ideate chose within that scope. A request for a recommendation, or delegation of a research blocker, is not delegation of the final choice.

The sealer requires one of these values and a note after `made by you` or `delegated`; their truth stays agent-owned.

After the fields, required prose states, in plain language grounded in the decision criteria and verified evidence, either:
- **A recommendation:** the recommended direction or path, its material trade-offs, and the viable choices left while the choice is `yours to make`. Under `made by you` or `delegated`, still give the evidence-supported recommendation and flag any divergence from the recorded choice, which stands; OR
- **What to do before choosing:** when evidence does not justify the next intended commitment, the experiment to run and what each result would mean, or what research could not establish and what would lift that limit, with the current trade-offs and no manufactured winner.

For a path search, with or without a fork, state why the recommended order beats the competing orderings. Ranking and comparison tables are optional and used only when they materially aid alternative search.

### Viable options

Required. Each surviving candidate, ordering, or path gets its own `###` subsection holding only what distinguishes it under the decision criteria, opening with `- Beyond known:` and what it adds beyond `Already known:`, or `none —` and why it stays viable. Path options describe causal, dependency, or strategy progression inside the problem only, never an implementation plan or schedule.

Write each decisive experiment as one line, `- Cheapest decisive experiment: <action>; metric: <metric>; pass/fail: <rule>; duration: <bound>; cost/effort: <bound>` (or `- Next experiment:` with the same components); `run an experiment first` needs one. Support bases, when used, require valid prefixes (`evidence-backed:`, `assumption-backed:`, `hypothesis:`).

### What would change the answer

Required, the one such record: the strongest challenge to What to do, the condition under which another candidate, ordering, or the baseline would win, and the uncertainty that remains.

### Exploration

Required: one line per dropped candidate, `- <candidate> — <decision criterion it lost on>`, or one line saying why none was dropped. The survey map, lens results, and search shape stay in the ledger.

### Evidence

Evidence opens with the required research record:

```text
- Research: settled | diminishing returns | unavailable sources | user limit — <coverage; limitations>
```

It starts with why research stopped (`settled` when more search could not change the answer, `diminishing returns`, `unavailable sources`, or `user limit`), then ` — ` and the coverage: each survey class searched, or why it was skipped, the sources used, and what was unavailable or user-excluded. The sealer refuses an ideation with no External evidence row naming a source unless research stopped for `user limit`, whose coverage then names the user's web opt-out, or `unavailable sources`, whose coverage names why web research could not be done; record a web search that found nothing relevant as an External evidence row saying so.

Evidence rows sit in tables under three optional fixed subsections; the subsection names the source kind, so rows carry no ID or code. Every table line in Evidence sits under one of them, below its exact header; these subsections and headers appear nowhere else.

- `### Local evidence` — repository files. Header: `| Claim | Source path | Locator | Verification |`. Path: a regular file under `--repo-root`; non-empty locator/verification; `hash-verified` needs the file's current SHA-256.
- `### External evidence` — publications and other outside sources. Header: `| Finding | Source | Locator | Date/freshness | Relevance |`.
- `### Contextual evidence` — user facts that are neither repository files nor publications. Header: `| Claim | Source description | Locator | Verification |`; non-empty locator/verification.

Elsewhere, cite evidence by what it is, such as its source and finding, never by a number or invented code; an `evidence-backed:` support basis names the evidence it rests on.

### Suggested follow-up

Optional. Never route directly to `construct`.

### Prohibited (deterministic)

Diff/patch code blocks.

### Receipt

The sealer appends `<!-- ideation-handoff: <version>; sha256: <digest> -->` as the final line, where `<version>` is Ideate's version.

### Workspace

The sealer writes only `.first-four-hours/ideations/<slug>/ideation.md` inside `--repo-root`. For a Git target it adds `/.first-four-hours/ideations/` once to worktree-local `.git/info/exclude`, never `.gitignore`, and reports `git_ignored`; a non-Git target reports `false`. Workspace files are never evidence, material surfaces, or command cwd: no evidence row may cite `.first-four-hours/ideations/`, and the sealer rejects a local row that does. The draft stays outside the repository and installed skill.

## Guidance

### Framing

Ask what problem the stated goal serves and whether a reframed goal would remove it; such a reframe is a candidate, and a rejected one is noted in `Scope / non-goals:`.

### Generation

Generate from the survey, not memory: each mechanism it found becomes a candidate or a ledger line saying why not. Name the obvious defaults first, `Already known:` plus answers a typical agent gives first; they stay eligible. Then probe the gaps with lenses: simplify or eliminate the requirement; invert or relax a constraint within your authority; transfer from a distant field; combine mechanisms whose strengths cover each other; shift who acts, when, or who decides; recover from failure instead of preventing it; keep the baseline. More ideas or personas add little variety; the survey supplies it. Collapse duplicates by mechanism, then forbid the defaults and every candidate so far and generate again. Done when every survey mechanism and lens has a ledger line and the forbidden pass ran.

Pick the search shape by problem: **alternative**, approaches to one goal chosen alone or combined; **path**, where sequencing and prerequisites dominate; **path with a fork**, a sequence with a fork to resolve. For a path, propose competing orderings too: risk-first, value-first, reversible-first, dependency-forced, cheapest-learning-first.

### Saturation

Identify the dominant discriminator: the cheapest credible observation, decision, or authority that could change the conclusion or next commitment. After the second round, stop when:
- remaining possibilities collapse to the same mechanism or causal/dependency path;
- one direction or path is supported across all material evidence-backed discriminators;
- remaining variation is downstream or cosmetic;
- distinguishing evidence or authority is genuinely unavailable; or
- more search cannot plausibly change the conclusion or next commitment.

### Challenge

- **Quick:** check the draft against each pre-seal check.
- **Standard:** argue the strongest case for the best losing candidate beyond the known set and for the baseline, each backed by a fresh source, then repair.
- **Deep:** one fresh challenger per [Delegation protocol](delegation-protocol.md); repair against its findings.

### Possibility space and feasibility

Look beyond mechanisms the repository already uses. An option is not disqualified only because it is unimplemented here or lacks project-specific validation; label its support basis honestly (`assumption-backed:` or `hypothesis:`) and judge feasibility and fit against the user's constraints. A technically plausible option that breaks a user constraint or is infeasible for the project is not viable.

### Blocker routing

Classify each blocker before asking:
- **Evidence-owned:** Gather a decision-changing observation.
- **Ideate-owned:** Decide directly using criteria and authority.
- **Materially user-owned:** Ask the minimum action-changing questions together, in the intake batch when visible then. If the user delegates that blocker ("you decide"), decide it within Ideate authority.
- **Unavailable or untestable evidence:** Preserve uncertainty: use `run an experiment first` for one testable decision-changing discriminator or `research limit reached` for insufficient/unobtainable coverage.

### Consumption

Return the sealed path to the user or invoking owner. A consumer reads What to do and Viable options without replaying research. While the final choice is `yours to make` it presents the recommendation and viable choices and obtains the user's final selection before committing; `made by you` and `delegated` stand without asking again. Inside Blueprint planning, Ideate is a bounded consultation that returns this result to the planner, not a separate upstream stage. Ideate never plans or implements.

### Reason boundary

Reason, consulted only when judgment is stuck, cannot choose Ideate's conclusion or next commitment; Ideate re-verifies its evidence, and only the accepted consequence persists in `ideation.md`.

## Pre-seal checks

Repair the draft until each holds:
- Every material conclusion, number, or absolute claim (such as "100%") traces to an evidence row or a calculation from one, or is labelled an estimate, `assumption-backed:`, or `hypothesis:`.
- Each source a material conclusion rests on was opened, is the work cited, and states the row's finding at the passage its Locator names; a search result or abstract alone does not count. Trace a secondary source to its primary, checked the same way, or mark the row secondary and untraced. A row you could not open says so; label its conclusion as above.
- Every viable option beyond `Already known:` was searched for prior art (who built or tried it, and what happened) in every source research could use; an evidence row records that search, even when nothing turned up.
- Each viable option opens with its `- Beyond known:` line.
- A recommendation built only from known or obvious answers names, for each candidate beyond them, the decision criterion it lost on; fewer sources is not a criterion.
- When What to do makes the next commitment depend on an experiment's result, Outcome is `run an experiment first`.
- The draft fits its tier's size, and prose holds no file-edit instructions.

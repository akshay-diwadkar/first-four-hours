# Ideation Contract

- [Structure](#structure)
- [Deterministic rules](#deterministic-rules)
  - [Handoff](#handoff)
  - [Evidence](#evidence)
  - [Exploration](#exploration)
  - [Conclusion](#conclusion)
  - [Open questions / next discriminator](#open-questions--next-discriminator)
  - [Optional downstream action](#optional-downstream-action)
  - [Prohibited (deterministic)](#prohibited-deterministic)
  - [Receipt](#receipt)
  - [Workspace](#workspace)
- [Guidance](#guidance)
  - [Framing](#framing)
  - [Generation](#generation)
  - [Search shapes and lenses](#search-shapes-and-lenses)
  - [Dominant discriminator and search saturation](#dominant-discriminator-and-search-saturation)
  - [Possibility space and feasibility](#possibility-space-and-feasibility)
  - [Blocker routing](#blocker-routing)
  - [Consumption](#consumption)
  - [Reason boundary](#reason-boundary)
- [Agent obligations (not machine-judged)](#agent-obligations-not-machine-judged)

Exact `ideation.md` format. Python enforces structure and syntax only; idea quality, relevance, novelty, and truthful prose remain agent obligations.

## Structure

```text
# Ideation: <goal>
## Handoff
## Evidence
## Exploration
## Conclusion
## Open questions / next discriminator
## Optional downstream action   ← omit when absent
```

Title first line with non-empty goal. Headings in canonical order, once each. Required records are the whole floor: add another line only when a consumer acts on it.

## Deterministic rules

### Handoff

Required non-empty fields:

```text
- State: decision-ready | experiment-first | research-limited
- Selection: open | user-selected — <choice; source> | delegated — <scope; source>
- Goal:
- Decision criteria:
- Scope / non-goals:
- Research: condition met | diminishing returns | unavailable sources | user limit — <coverage; limitations>
```

Agent-owned:
- `decision-ready` → evidence/authority supports a recommendation for the next intended commitment, whether that is an alternative, a combination of alternatives, or a coherent causal/dependency path.
- `experiment-first` → one testable observation could materially change the conclusion or next commitment before stronger commitment.
- `research-limited` → insufficient coverage for a defensible stronger state.

`Selection:` records who owns the final choice; it never restates the recommendation:
- `open` → the user still selects. The Conclusion's recommendation is advice, not approval or implementation authority.
- `user-selected — <choice; source>` → the user explicitly chose before sealing; cite where (for example a contextual evidence row) and do not ask again.
- `delegated — <scope; source>` → the user explicitly delegated final selection; Ideate selected within that scope. A request for a recommendation, or delegation of a research blocker, is not delegation of final selection.

The sealer requires one of these values and a note after `user-selected` or `delegated`; their truth stays agent-owned.

`Research:` is the one research record. It begins with why research stopped (`condition met`, `diminishing returns`, `unavailable sources`, or `user limit`), then ` — ` and the coverage: playbooks and sources used, what was searched, and what was unavailable, skipped, or user-excluded. `decision-ready` cannot rest on an unverified hypothesis or empty evidence. Individually verified findings or completed source collection do not determine aggregate readiness; sufficiency for the next intended commitment remains agent-owned.

### Evidence

Evidence rows sit in tables under three optional fixed subsections; the subsection names the source kind, so rows carry no ID or code. Every table line in Evidence sits under one of them, below its exact header; these subsections and headers appear nowhere else.

- `### Local evidence` — repository files. Header: `| Claim | Source path | Locator | Verification |`. Path: a regular file under `--repo-root`; non-empty locator/verification; `hash-verified` needs the file's current SHA-256.
- `### External evidence` — publications and other outside sources. Header: `| Finding | Source | Locator | Date/freshness | Relevance |`.
- `### Contextual evidence` — user facts that are neither repository files nor publications. Header: `| Claim | Source description | Locator | Verification |`; non-empty locator/verification.

Elsewhere, cite evidence by what it is, such as its source and finding, never by a number or invented code; an `evidence-backed:` support basis names the evidence it rests on. Tracing each material conclusion to a row is an agent obligation: the sealer checks rows, not citations.

### Exploration

Exploration opens with the divergence record, required in every search:

```text
Search shape: alternative | path | composed
- Obvious defaults:
- Simplify/eliminate:
- Invert/relax an authorized constraint:
- Domain transfer:
- Combine mechanisms:
- Actor/timing/control:
- Failure recovery:
- Preserve baseline:
```

A `path` or `composed` shape also requires `- Risk-first:`, `- Value-first:`, `- Reversible-first:`, `- Dependency-forced:`, and `- Cheapest-learning-first:`. Each lens line names the candidate or ordering it yielded, or reads `not applicable — <one-line reason>`; `- Obvious defaults:` always names at least one answer. The sealer checks only that each line exists outside HTML comments and is non-empty.

Then `### Dropped` lists each dropped candidate with a one-line reason, and each surviving candidate, ordering, or path gets its own subsection holding only what distinguishes it under the decision criteria. Path and composed exploration describe causal, dependency, or strategy progression inside the problem only, never an implementation plan or schedule.

Write each decisive experiment as one line, `- Cheapest decisive experiment: <action>; metric: <metric>; pass/fail: <rule>; duration: <bound>; cost/effort: <bound>` (or `- Next experiment:` with the same components); the sealer checks only lines with one of these labels and requires every bound non-empty. Support bases, when used, require valid prefixes (`evidence-backed:`, `assumption-backed:`, `hypothesis:`).

### Conclusion

Clear synthesis and rationale grounded in stated decision criteria and verified evidence. Supports either:
- **Recommended direction / path:** when evidence or authority supports a lead alternative, a combination of alternatives, or a causal path, give the recommendation, its material trade-offs, and the viable choices left to the user under `Selection: open`. Under `user-selected` or `delegated`, still give the evidence-supported recommendation and flag any divergence from the recorded choice, which stands; OR
- **Unresolved synthesis / next commitment:** when evidence does not justify the next intended commitment, summarize current trade-offs and the next decisive discriminator or research limit without manufacturing a winner.

For a path or composed search, state why the recommended order beats the competing orderings. Ranking and comparison tables are optional and used only when they materially aid alternative search.

### Open questions / next discriminator

Required non-empty field `- What would change the answer:`, the one record of what would change the answer: the strongest challenge to the Conclusion, the condition under which another candidate, ordering, or the baseline would win, and the uncertainty that remains.

### Optional downstream action

Optional. Never route directly to `construct`.

### Prohibited (deterministic)

Diff/patch code blocks.

### Receipt

The sealer appends `<!-- ideation-handoff: <version>; sha256: <digest> -->` as the final line, where `<version>` is Ideate's version.

### Workspace

The sealer writes only `.first-four-hours/ideations/<slug>/ideation.md` inside `--repo-root`. For a Git target it adds `/.first-four-hours/ideations/` once to worktree-local `.git/info/exclude`, never `.gitignore`, and reports `git_ignored`; a non-Git target reports `false`. It fails closed on a non-top-level Git root, an unresolved or unsafe exclude path, a tracked `.first-four-hours/ideations/` namespace in any letter case, a symlinked or non-regular `.first-four-hours/` or workspace entry, or other files in `.first-four-hours/ideations/<slug>/`. Workspace files are never evidence, material surfaces, or command cwd: no evidence row may cite `.first-four-hours/ideations/`, and the sealer rejects a local row that does. The draft stays outside the repository and installed skill.

## Guidance

### Framing

Before generating, ask what problem the stated goal serves and whether a reframed goal would remove that problem. A reframe that would becomes a candidate, usually under Simplify/eliminate; note a rejected reframe in `Scope / non-goals:`.

### Generation

Diverge before judging feasibility, in every domain. Generate a wide, cheap candidate set from the lenses before research; research then tests, extends, or eliminates candidates and may add new ones, so candidates are never limited to what research found. First ideas tend to be the typical ones, so name them on the `Obvious defaults:` line first and make every other causal lens look past them: a default stays an eligible candidate but fills no other causal lens line except `Preserve baseline:`, which names the status quo even when it is also a default, and a lens that yields nothing beyond the defaults reads not applicable with its reason. After the lenses, imagine every candidate so far forbidden and add whatever then appears. Collapse duplicate mechanisms. Evaluate only survivors in depth: compare each against the lead and the baseline rather than scoring it alone, and recombine parts of survivors that won on different criteria into a further candidate. Record every dropped candidate with a one-line reason, in alternative and path searches alike. No idea count is imposed: generation is complete when every lens is accounted for and the forbidden-set pass has run.

### Search shapes and lenses

Choose the search structure that best fits the problem:
- **Alternatives:** approaches to one goal that can be chosen alone or combined, with no required order, evaluated against decision criteria, impact, risk, effort, and confidence; recommend a combination when evidence supports it.
- **Paths:** ordering, dependency, or multi-step problems where sequencing and prerequisites dominate; trace milestones, prerequisites, sequencing rationale, genuine forks, and dead ends avoided.
- **Composed:** a sequence with an architectural fork that needs option resolution, or an option whose selection continues into a causal or strategy progression.

Causal-divergence lenses, for every search:
- **Obvious defaults:** Name at least one answer a typical agent would give first, so the other lenses look past them; this line is never not applicable.
- **Simplify/eliminate:** Remove requirement or bypass problem.
- **Invert/relax an authorized constraint:** Only alter constraints within Ideate’s delegated authority.
- **Domain transfer:** State the problem without its domain's nouns, then borrow from a distant field that solved that abstracted problem.
- **Combine mechanisms:** Pair mechanisms whose strengths cover each other's weaknesses, such as a quick common route with a careful fallback.
- **Actor/timing/control:** Shift who acts, whose view counts, when it happens, or who decides.
- **Failure recovery:** Shift from preventing failure to limiting it or recovering from it.
- **Preserve baseline:** Keep current/status-quo approach as a legitimate candidate when available evidence does not justify intervention.

Sequencing lenses, for path and composed searches; each proposes a competing ordering, never a justification of an order already chosen:
- **Risk-first:** Retire the step most likely to fail first.
- **Value-first:** Deliver the most valuable outcome earliest.
- **Reversible-first:** Take reversible steps before irreversible commitments.
- **Dependency-forced:** Follow the order prerequisites impose.
- **Cheapest-learning-first:** Start with the cheapest step that resolves the largest unknown.

### Dominant discriminator and search saturation

When possibilities remain, identify the dominant discriminator: the cheapest credible observation, decision, or authority that could materially change the conclusion or next commitment. Once every lens is accounted for and the forbidden-set pass has run, stop search when:
- remaining possibilities collapse to the same mechanism or causal/dependency path;
- one recommended direction or coherent causal/dependency path is supported across all material evidence-backed discriminators;
- remaining variation is downstream or cosmetic;
- distinguishing evidence or authority is genuinely unavailable; or
- more search cannot plausibly change the conclusion or next commitment.

### Possibility space and feasibility

Look beyond mechanisms the repository already uses. An option is not disqualified only because it is unimplemented here or lacks project-specific validation; label its support basis honestly (`assumption-backed:` or `hypothesis:`) and judge feasibility and fit against the user's constraints. A technically plausible option that breaks a user constraint or is infeasible for the project is not viable.

### Blocker routing

Classify each blocker before asking:
- **Evidence-owned:** Gather a decision-changing observation.
- **Ideate-owned:** Decide directly using criteria and authority.
- **Materially user-owned:** Ask exactly one minimum action-changing question through Reason, or directly when Reason is unnecessary. If the user delegates that blocker ("you decide"), decide it within Ideate authority.
- **Unavailable or untestable evidence:** Preserve uncertainty: use `experiment-first` for one testable decision-changing discriminator or `research-limited` for insufficient/unobtainable coverage.

### Consumption

Return the sealed path to the user or invoking owner. A consumer reads `State`, `Selection`, the Conclusion, and the viable options in Exploration without replaying research. Under `Selection: open` it presents the recommendation and viable choices and obtains the user's final selection before committing; `user-selected` and `delegated` stand without asking again. Inside Blueprint planning, Ideate is a bounded consultation that returns this result to the planner, not a separate upstream stage. Ideate never plans or implements.

### Reason boundary

A Reason challenge targets a consequential researched provisional conclusion or load-bearing claim; Reason cannot choose Ideate's conclusion or next commitment.

## Agent obligations (not machine-judged)

Truthful support prose and lens accounting, honest dropped-candidate reasons, substantive criteria application and adversarial reasoning, honest research-stop recording, no fabricated precision, no file-edit instructions in artifact prose.

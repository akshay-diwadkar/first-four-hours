# Audit method

## Triage first

Spend mutant runs only where cheap evidence points. Use the repository's own tools and history, never a new framework:

- per-test durations, such as `pytest --durations=0`, the runner's timing report, or CI step timings;
- per-test coverage contexts, where the runner records them, for tests covering the same lines;
- tests with no assertion, that assert only on mocks of the code under test, or that assert wording or formatting;
- CI reruns and retry markers for flaky tests;
- the same scenario repeated across unit, integration, and end-to-end levels.

Each surviving candidate names its tests, the behavior they claim to protect, and the cheapest command that runs them.

## Selections

A selection is a named argv command run from the root of the copy, such as `["python", "-m", "pytest", "-q", "tests/test_cart.py"]`, with a `timeout_seconds`; no two share an argv. `suite` is required and runs the whole suite the user pays for. Every selection must pass unmutated, and each is timed, so a flaky test cannot be one: select a stable subset and cite the rerun evidence in a `rework` rationale. Use relative paths only: an absolute path or an editable install runs the real repository instead of the copy, which fails a kill claim but makes a survival claim pass falsely, so a `vacuous` or `gap` rationale shows its selection runs the copy's code. The copy skips `.git` and `__pycache__`; set `copy_git` when tests need Git, and list large paths no test reads in `copy_exclude`.

## Mutants

A mutant is one exact replacement in one non-test source file whose `old` text occurs exactly once; keep `old` on one line, since checkouts may use either line ending. Change one behavior a correct test could observe while everything else still works: a flipped comparison, an off-by-one bound, a dropped branch, a wrong constant. A mutant that breaks import, syntax, or every test proves nothing and makes every test look redundant.

## Findings

A finding's kind fixes what the seal replays for each mutant it lists:

| Kind | Selections | Replayed |
| :--- | :--- | :--- |
| `redundant` | `candidate`, `guard` | candidate kills; guard kills |
| `vacuous` | `candidate`, `guard` | candidate survives; guard kills |
| `gap` | `guard`, `witness` | guard survives; witness kills |
| `rework` | `candidate`, `guard` | candidate kills |

`guard` must kill the mutants once the change lands: for `redundant` and `vacuous`, the tests that stay, never the candidate's files nor another such finding's candidate; for `gap`, the tests that will hold the new test; for `rework`, the tests that will hold the faster or stable replacement, possibly the candidate itself. `witness` is any command, such as a probe outside the suite, showing the mutant is observable. Mutants for `redundant` and `vacuous` change the behavior the candidate claims to test. A `rework` without mutants rests on its rationale and measured times. Every finding names its `tests` and a `rationale` citing triage evidence.

## Budget

Record the user's target as `budget.seconds`, null when they set none, with `budget.kind` `local` for `suite` time or `ci` for CI time, and their words in `budget.basis`. Order findings by time saved per protection kept, and say in the summary when they cannot reach the budget.

## Verify

`verify` copies the current tree, runs `suite` and each selected finding's guard unmutated, then requires every selected mutant killed by its guard. It fails when a mutant's `old` text is gone, a selection fails unmutated, or, with a `redundant`, `vacuous`, or `rework` finding selected, `suite` runs more than 10% plus one second slower than the audited baseline. It reports the time saved, and a `local` budget's verdict, as values: timing is noisy, and one batch may not reach the budget alone.

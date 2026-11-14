# Temper

`/temper` audits an existing test suite to cut what it costs to run while keeping, or raising, the faults it catches. It proves every finding by replaying small deliberate faults, called mutants, against your tests, and seals the findings in `test-audit.md` for [`/blueprint`](blueprint.md) to plan from. It belongs to the Workbench domain.

## When to use it

- A test suite takes long enough, or costs enough in CI, that you feel it on every change.
- Agents have been adding tests faster than anyone reviews them, and you suspect many protect little.
- You want to know which behaviors no test protects.

## When to use something else

- To write or fix a test as part of a change, plan the change with [`/blueprint`](blueprint.md); it shapes the tests it plans by `/temper`'s test design rules.
- To find why a test fails, use [`/diagnose`](diagnose.md).
- To review a finished change, use [`/assess`](assess.md).

## How to start it

Type `/temper`, or ask in plain words for a test-suite audit; the agent may also start `/temper` when your request is about a slow or bloated suite, but not for writing or fixing individual tests. For example (illustrative):

```text
/temper : Our pytest suite takes 40 minutes in CI and most of it is integration tests. Get it under 10 minutes without losing protection.
```

## What happens

1. `/temper` asks for your budget, the suite or CI time you want, unless you already gave one. It never invents a target.
2. It triages cheaply with your project's own tools: per-test run times, coverage overlap, tests with no assertions or that mock the code they claim to test, flaky reruns, and the same scenario repeated at several levels.
3. Only for those candidates, it writes mutants: small changes to your source code, such as a flipped comparison, that a correct test should catch.
4. It seals the audit. The seal copies your project to a throwaway folder outside it and replays every finding there: a redundant test and the tests that stay both catch its mutants, a vacuous test catches none of the mutants the remaining tests catch, and a gap's mutant slips past the suite while a probe shows it matters. A claim that does not replay blocks the seal. Your project is never edited.

## What you get

A sealed `test-audit.md` in the ignored folder `.first-four-hours/test-audits/<slug>/`, with numbered findings of four kinds: `redundant` and `vacuous` tests to remove, `gap`s to cover, and tests to `rework` because they are slow or flaky. Each finding lists its tests, its mutants, and the measured time of each command. Ask `/blueprint` to plan one finding or a batch. After `/construct` makes the change, the plan reruns `/temper`'s `verify`, which fails if the remaining tests stop catching any of those findings' mutants, or if a trimmed suite runs clearly slower (more than 10% plus one second) than the audit measured. It reports the seconds saved, rather than requiring a saving, because timing is noisy.

## When it stops

If a command fails on the unchanged copy, or a claim does not replay, the seal refuses and names the finding, the mutant, and the command; `/temper` repairs the bundle or drops the finding, never the expectation. A command that reaches your real project, through an absolute path or an editable install, never sees the copy's mutants: that fails a claim that a test catches a mutant, but can let a `vacuous` or `gap` claim that a mutant slips through pass falsely, so `/temper` shows that each such finding's command runs the copy's code. `/temper` asks before running anything that uses shared or billable resources or production data.

## Why it's built this way

**The failure it prevents.** Agents check their work by writing tests, and keep writing them. Some are complex yet do not test the behavior you want; others test things that need no test. Each one costs CPU time and CI money on every change, and after enough agent work a large repository can take an hour to test. Rewriting such a suite around focused tests that prove behavioral faults works, but it should not take a hard limit on test count to stop the pile from growing back.

**What it refuses, and why.** It never deletes or adds a test itself: `/blueprint` plans the change and `/construct` makes it. It never accepts a finding on its own word: every claim is a mutant the commands catch or miss, replayed by a script. It sets no test-count limit; your budget is time, and any limit is a ceiling, not a quota.

**Floor and ceiling.** A weaker agent must ground every finding in replayed mutants and measured times, so it cannot remove protection on opinion. A stronger agent decides which tests are worth examining and which mutants mean something; that judgment stays its own.

## Related skills

[`/blueprint`](blueprint.md) plans the findings you name and uses `/temper`'s test design rules whenever it plans tests. [`/construct`](construct.md) carries out the plan and runs `/temper`'s `verify`. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[`/temper`'s contract](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/temper/SKILL.md)

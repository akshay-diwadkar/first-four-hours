# Find out which tests actually catch anything

Every change came with tests, which felt responsible. Months later the suite is slow, many tests check the same thing, and a few would still pass if you broke the code they claim to test. Twelve green ticks, and no idea which of them protect anything.

Agents check their work by writing tests, and keep writing them. Some assert nothing that matters, some mock the very code they test, some repeat a scenario another level already covers. Deleting tests by feel removes protection along with the waste. Temper proves each finding with mutants: small deliberate faults in your source that a good test should catch, replayed in a throwaway copy of your project. Blueprint then plans the change from those findings, and Construct makes it and reruns Temper's check.

## Use this when

- The suite takes long enough, or costs enough in CI, that you feel it on every change.
- Agents have been adding tests faster than anyone reviews them, and you suspect many protect little.
- You want to know which behavior no test protects.

## Use something else when

- You need to write or fix one test as part of a change: [Plan a change before your agent starts editing](plan-a-change.md). Blueprint shapes the tests it plans by Temper's test design rules.
- A test fails and you do not know why: [Fix the bug without patching the symptom](fix-a-bug.md).

## Steps

1. Start Temper with your budget: the suite or CI time you want. It never invents a target.
2. Read the sealed `test-audit.md`. Its findings are `redundant` or `vacuous` tests to remove, `gap`s where behavior goes unprotected, and tests to `rework` because they are slow or flaky. Each lists its tests, its mutants, and measured times. Temper never edits your project.
3. Ask Blueprint to plan one finding or a batch, naming them.
4. Carry out the sealed plan with Construct, as in [Plan a change before your agent starts editing](plan-a-change.md). The plan reruns Temper's `verify`, which fails if the remaining tests stop catching those findings' mutants.

## A worked scenario

*Illustrative: FreshCart is a made-up online grocery service, and this is not a recorded run. Excerpts are shortened.*

FreshCart's CI now takes long enough that engineers push and go to lunch. Søren Lindqvist, FreshCart's platform engineer, owns the pipeline. Most of the growth came from agent-written tests, and last month a broken discount rule shipped while every test was green. The shortcut on Søren's list is to delete the slowest files and see what complains.

```text
/temper : FreshCart's test suite takes too long in CI and a broken discount rule shipped last month with every test green. Get CI under 15 minutes without losing protection, and tell me what nothing tests.
```

Temper times each test, checks coverage overlap, and looks for tests with no meaningful assertion or that mock the code they claim to test. For the suspects, it writes mutants, such as flipping the comparison in the discount threshold, and replays them in a copy of the project. Two findings, shortened:

```markdown
## Finding 3

- Kind: `vacuous`
- Title: test_apply_discount asserts only that a mock was called
- Tests: tests/pricing/test_discounts.py::test_apply_discount
- Candidate: `discount-mock-test`
- Guard: `pricing-suite`

The test replaces apply_discount with a mock, so it passes whatever the discount code does.

### Mutants

- `discount-rounding` in `freshcart/pricing/discounts.py`, rounds the discounted price: round → floor; candidate `discount-mock-test` survived, guard `pricing-suite` killed

## Finding 7

- Kind: `gap`
- Title: nothing tests the minimum basket for a discount
- Tests: none
- Guard: `pricing-suite`
- Witness: `threshold-probe`

Both `pricing-suite` and `suite` pass when the minimum basket check is inverted.
```

Finding 3 is fast, so deleting slow files by hand would have kept it, and it protects nothing the rest of the pricing suite does not already catch. Finding 7 is the shape of last month's bug: a mutant that inverts the discount threshold slips past the whole suite, and only Temper's probe catches it.

```text
/blueprint : Plan findings 3 and 7 in .first-four-hours/test-audits/freshcart-ci-time/test-audit.md.
```

Blueprint plans the vacuous test's removal and a real threshold test shaped by Temper's test design rules. Construct makes the change and reruns Temper's `verify`: the remaining tests catch every planned finding's mutants, and it reports the seconds saved.

## You are done when

Construct's report shows every instruction applied, the plan's verification passed, including Temper's `verify`, and the diff matching the plan, and you have settled its owner gates. A smaller suite is not the signal; a suite that still catches every planned finding's mutants is.

## If it goes wrong

- Temper will not seal: a command failed on the unchanged copy, or a claim did not replay. Its report names the finding, the mutant, and the command ([Temper](../skills/temper.md)).
- Temper asks before running something that uses shared or billable resources or production data: that decision is yours ([Temper](../skills/temper.md)).
- Temper's `verify` fails after the change: the remaining tests no longer catch a finding's mutants, so the plan removed protection. Take Construct's evidence back to a new `/blueprint` ([Construct](../skills/construct.md)).

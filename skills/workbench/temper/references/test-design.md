# Test design

A test earns its place by catching a realistic fault that nothing cheaper already catches. Apply these rules whenever a test is written, changed, kept, or removed.

## Keep or add a test only when

- it fails for a named, realistic defect or an uncovered acceptance condition that would otherwise reach users or a later stage;
- it observes behavior where consumers see it: returned values, persisted state, emitted errors, or calls across a real boundary;
- no existing test already fails for the same fault; strengthen that test instead.

## Shape

- Use the smallest scope that still exposes the fault: a function call before a process, a process before a service, a service before an end-to-end flow. Climb a level only when the fault lives in the wiring between levels.
- Mock only what the test does not claim, such as external services, clocks, randomness, or the network; never the operation or result whose correctness it asserts.
- Assert the observable result of one behavior, not that code ran.
- Keep it deterministic and isolated: no order dependence, sleeps, shared mutable state, wall-clock time, or live network. A flaky test is a defect to fix or remove, never to retry.
- Keep fixtures minimal and reuse them immutably; delete fixtures and helpers no surviving test uses.

## Do not add

- checks of wording, formatting, field order, or framework behavior;
- tests that restate the implementation: private calls, call counts, internal data shapes;
- a second test for a covered fault at a slower level;
- exhaustive permutations, or edge cases no realistic input produces;
- inventory or completeness checks over fixtures and catalogs.

## Cost

Suite time and CI minutes are paid on every change. Prefer replacing a slow test with a faster one that catches the same faults. A count or time limit is a ceiling, not a quota: never add tests to fill it, and when a needed test does not fit, report the conflict instead of dropping protection.

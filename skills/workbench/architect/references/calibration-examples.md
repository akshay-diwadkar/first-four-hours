# Calibration Examples

Paths are illustrative. Both examples use the [Handoff Template](architecture-template.md) shape; the [Worked Example](worked-examples.md) shows a system-level boundary instead.

## Class-level target

The pressure lives inside one class, and an existing owner already does part of its job, so the decision merges into that owner instead of adding a helper.

```markdown
# Architecture Decision: Separate Export Formatting From Upload Retry

## Context

`ReportExporter` builds CSV rows, names output files, and retries uploads with its own backoff loop, so a change to retry policy edits a formatting class. The decision covers this one class and its upload call; report contents, the storage provider, and other exporters are outside it. `user-request` `reports/exporter.py:12-58`

## Decision

- Selected architecture: `ReportExporter` keeps formatting and file naming and sends uploads through the existing `with_retry` wrapper, which already owns backoff for outbound calls; its private retry loop merges into that owner rather than moving to a new helper. The discriminator is that one retry owner already exists and its configurable attempt limit covers this upload's five attempts. `reports/exporter.py:40-58` `net/retry.py:1-30`
- Owner / boundary: `net/retry.py` owns retry and backoff policy, `ReportExporter` owns report shape, and the boundary is the upload call. `net/retry.py:1-30` `reports/exporter.py:40-58`
- Invariants / constraints: An upload is still attempted at most five times, and a final failure still reaches the caller as `UploadFailed`. `reports/exporter.py:40-58` `tests/test_exporter.py:20-34`
- Consequences: Later changes to the shared retry policy also reach report uploads. `net/retry.py:1-30`

## Evidence and Uncertainty

Only this class and the shared retry owner are in scope. The decision moves one responsibility at the class's upload call, so no system-level view is needed. `reports/exporter.py:12-58` `net/retry.py:1-30`

## Evidence Ledger

- source: request | locator: user-request | claim: ReportExporter has become hard to change; decide how its responsibilities should be divided.
- source: code | locator: reports/exporter.py:12-58 | anchor: class ReportExporter | claim: The class formats rows, names files, and runs its own upload retry loop.
- source: code | locator: reports/exporter.py:40-58 | anchor: for attempt in range(5) | claim: The private loop retries an upload up to five times with doubling delays and raises UploadFailed.
- source: code | locator: net/retry.py:1-30 | anchor: def with_retry | claim: The shared wrapper owns doubling backoff for outbound calls and takes the attempt limit as a parameter.
- source: test | locator: tests/test_exporter.py:20-34 | anchor: test_upload_gives_up | claim: Tests assert five attempts and UploadFailed after the last one.
```

## No-design-change outcome

The supplied target shows no owner, boundary, dependency, or state consequence, so gate 1's evidence supports a no-change outcome and nothing goes to `blueprint`.

```markdown
# Architecture Decision: Keep Shared Helpers In One Module

## Context

The request asks whether `utils/helpers.py` should be split into per-domain modules. The decision covers that module and its importers; renaming and formatting are outside it. `user-request` `utils/helpers.py:1-64`

## Decision

- Selected architecture: no-design-change. The module holds six small pure functions with no shared state, each imported only by its own callers, and recent history shows no change that had to edit it together with an unrelated domain. The only pressure found is a layout preference, which is not a structural consequence. `utils/helpers.py:1-64` `billing/invoice.py:1-5` `git log --name-only -n 200 -- utils/helpers.py at 3f9c2ab`
- Owner / boundary: Each function's importers own its use; the module is a namespace, not an owner of policy or state. `utils/helpers.py:1-64`
- Invariants / constraints: None, because no structure changes. `utils/helpers.py:1-64`
- Consequences: The module stays as it is, and no implementation target goes to `blueprint`. `utils/helpers.py:1-64`

## Evidence and Uncertainty

Checked the module, its importers, and its recent history. Splitting it would move code without changing an owner, boundary, or dependency direction. `utils/helpers.py:1-64` `billing/invoice.py:1-5` `git log --name-only -n 200 -- utils/helpers.py at 3f9c2ab`

## Evidence Ledger

- source: request | locator: user-request | claim: Decide whether utils/helpers.py should be split into per-domain modules.
- source: code | locator: utils/helpers.py:1-64 | anchor: def | claim: Six small pure functions with no module-level state.
- source: code | locator: billing/invoice.py:1-5 | anchor: from utils.helpers import | claim: A typical importer uses only the helpers it needs.
- source: runtime | locator: git log --name-only -n 200 -- utils/helpers.py at 3f9c2ab | claim: No commit touching the module also edited it for more than one domain.
```

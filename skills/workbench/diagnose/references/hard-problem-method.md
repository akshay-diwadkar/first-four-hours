# Hard-Problem Method

Load when the cause is not visible by reading code: performance, resource use, hangs, data- or environment-dependent behavior, intermittent failures, regressions, or "works in X, fails or is slow in Y". The [finding gate](diagnosis-techniques.md#finding-gate) still decides acceptance.

## 1. Pin the symptom

State it as a measurement: metric, magnitude, scope, onset. First separate slow (progressing), stuck (no progress), and thrashing (retrying, spilling, swapping); their cause spaces barely overlap. Get a progress signal before theorizing.

## 2. Establish the reference

Use a known-good comparator when one exists: another person's run, an earlier version, a smaller input, another environment. Verify comparability before trusting the gap: same input bytes, same measurement boundary, same conditions. Without a comparator, use a first-principles expected cost as the reference.

## 3. Locate before explaining

Decompose the end-to-end path into stages and measure each. The stage that owns the gap bounds the hypothesis space. Check its shape: uniform slowness, skew (a few stragglers), or a serial bottleneck (one worker busy, the rest idle).

## 4. Inventory differences from captured facts

A claim such as "same configuration" is a hypothesis to verify, not evidence: the requested configuration is not the built artifact. Capture the same facts from both sides with the same probe, then diff them across code and invocation, the artifact as built, data shape and volume, environment and versions, and runtime conditions. Look especially for hidden multipliers: work repeated per member, fold, replica, retry, row, or batch; artifacts reloaded per call; parallel workers oversubscribing shared cores; work serialized onto one process; and cost that scales with a size that differs between the sides.

## 5. Rank hypotheses by what they can explain

For each hypothesis, keep temporarily its mechanism, motivating difference or observation, predicted observation, and the magnitude it could explain. Drop any hypothesis that cannot explain the observed magnitude or location. Order the rest by plausibility and explanatory magnitude against probe cost. When the symptom is speed or resource use and a surviving hypothesis is a configuration setting, load [Configuration Performance](configuration-performance.md).

## 6. Run discriminating probes

For a regression with a known-good revision, reading history is usually cheaper than executing: `git log -S` or `-G` on the symptom's identifiers, `git log -L` over the owning function, `git blame`, and `git diff <good> <bad>` over the stage that owns the gap often name the responsible change as `history` or `command` evidence. Bisect only what history leaves ambiguous, and skip history when the difference inventory points outside version control, such as a dependency or environment change.

Prefer probes whose outcome splits the remaining hypotheses: swap experiments (A's artifact in B's environment and the reverse), bisection over the difference inventory, minimization that preserves the ratio, and profiling or stack samples of the slow stage. Write the predicted outcome per hypothesis before running. Control confounders such as warm caches and concurrent load, and repeat when variance is plausible. Run each of these, bisection included, and step 7's interventions only as a [non-mutating probe](diagnosis-techniques.md#non-mutating-probes) allows.

When evidence lives where you cannot execute, hand the user one probe at a time: exact code or commands, where to run it, what to save, and what each plausible outcome would mean. Saved outputs become `capture` evidence under the declared `evidence_root` per the [Diagnosis Contract](diagnosis-contract.md).

## 7. Confirm by intervention

A cause is `demonstrated` when changing it moves the symptom in the predicted direction and roughly the predicted magnitude, and restoring it restores the symptom where cheap. Otherwise it is `inferred`; record that as the finding's `cause_status`.

## 8. Account for the whole effect

If demonstrated causes explain only part of the gap, the remainder is still open; independent causes often stack. Continue, or record the residual gap.

## Stop

Stop when demonstrated causes account for the effect, or when the next discriminating probe needs access, compute, or authority you lack. Record evidenced eliminations a competent next investigator would otherwise pursue in `ruled_out`, and each next discriminating probe with its expected outcomes in `open_probes`. When a probe must run later, seal this interim diagnosis; a later pass treats it as orientation only, re-verifies what it relies on, and authors a fresh bundle.

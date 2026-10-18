# Improvement Evidence

## Baseline and leverage

Establish enough current baseline, constraint, friction, or headroom to distinguish real leverage from hypothetical cleanup. Use the cheapest trustworthy observation: existing timings, CI logs, repeated developer workflow cost, dependency constraints, local command output, code paths showing duplicate work, or focused current source evidence. Quantitative measurement is required only when qualitative current evidence cannot establish material consequence.

Prefer local current evidence. External documentation may confirm a versioned capability, support window, or ecosystem constraint after a local target exists; it never selects a finding by popularity or best-practice appeal.

## Acceptance boundary

Accept an improvement finding only through the [finding gate](diagnosis-techniques.md#finding-gate), with this baseline as its evidence of cost, constraint, friction, or headroom against the requested objective.

If measurement is inconclusive, unavailable, or decision-changing, record a material limitation or blocker. Do not convert uncertainty into a plan-ready finding. Diagnose identifies what materially deserves change and why; Blueprint owns implementation mechanism, ordered instructions, and proof.

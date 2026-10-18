# Diagnosis Techniques

Investigate proportionally, in this order:

1. Establish the current target/snapshot exactly as the [Diagnosis Contract](diagnosis-contract.md) requires.
2. Identify this target's material high-level risk or leverage boundaries: where downside, cost, constraint, or improvement headroom would matter most and where current evidence makes it plausible.
3. Inspect the highest-value evidence paths across those boundaries first.
4. Trace deeper only where observed risk, cost, constraint, or leverage evidence requires it.
5. Disconfirm each plausible explanation or opportunity via the cheapest separating observation.
6. Accept evidenced findings or state material limitations — what was examined and what was not — instead of exhaustive scans. **Bounded completeness:** continue while another independently material in-bounds hypothesis or surface can plausibly add an actionable finding or materially change the conclusion.

## Finding gate

Promote a candidate only through one neutral gate: current evidenced downside, cost, constraint, friction, or directly evidenced headroom; a credible causal or ownership/boundary explanation; and a consequence sufficient to make acting on it worthwhile. Aesthetic or architecture preference, generic best practice, hypothetical cleanup, or imaginable speedup without current evidenced downside or leverage is never promoted; Architect owns structural selection.

Before accepting any cause, even one visible in code, name the most plausible rival explanation and the observation that rules it out; record that elimination in `ruled_out` when a competent next investigator would otherwise pursue it. If no observation rules the rival out, the cause stays `inferred`: name the rival in `limitations` and add an `open_probes` entry that would separate them.

An improvement finding needs present-state evidence of cost, constraint, friction, or headroom against the requested objective. Quantification is required only when the decision depends on it; qualitative evidence can pass when it directly establishes material leverage. Missing decision-changing measurement remains a limitation/blocker, never a speculative finding.

Keep all independently material accepted findings from the bounded pass. Only merge manifestations sharing one underlying cause/ownership boundary and material consequence. Differing causes/boundaries or independently actionable consequences remain separate; shared file, area, or generic consequence cannot merge them.

External documentation or another project's incident may support a mechanism or direction but never alone establishes this project's cause. Cite it only when relevant, and match version-sensitive claims to the environment's actual versions.

## Missing facts

Pursue the cheapest decision-changing evidence path first; interpretation and acceptance stay diagnosis-owned. Ask through `reason` one minimum question only for irreducible user-only expected-behavior, operational, or policy facts. Re-verify a Reason result against current evidence and decide; persist only its accepted consequence, never Reason state or artifacts.

## Advisory directions

In the final report, offer a possible direction for a finding only when evidence supports it and it would help. Tie it to the finding and its evidence, and state material caveats or tradeoffs. It is a lead to investigate, not a recommendation, design, plan, authorization, or proof that it works. Without support, omit it or name the missing evidence or next discriminator; no finding needs one. Directions stay out of `diagnosis.md`, which carries evidence, not remedies; a next discriminator still belongs in `open_probes`.

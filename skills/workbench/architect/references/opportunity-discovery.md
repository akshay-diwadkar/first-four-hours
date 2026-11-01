# Opportunity Discovery

## Bound the pass

Derive the smallest useful exploration from the request, current project files/source, architecture docs or ADRs, ownership notes, and bounded relevant history.

State the boundary, exclusions, material unknowns, and stop condition only as far as needed to avoid a blind spot or endless search.

Optional read-only evidence workers are earned only when separate bounded scopes materially reduce a real blind spot. Assign each a narrow question and scope. The primary re-verifies every material observation before accepting it.

## Candidate gate

Promote only a structural candidate with current or credible near-term consequence, such as recurring propagation burden, conflicting ownership, distributed invariants or lifecycle, wrong dependency direction, leaky abstraction, repeated caller burden, structural testability friction, duplicated state or policy, or a real capability blocked by current structure. Load [Structural Techniques](structural-techniques.md) before promoting or rejecting a candidate: it gives cheap history and import evidence for these signals and discriminators for weighing them.

Reject naming or style preference, doctrine, healthy unconventional structure, hypothetical reuse, unsupported speculation, and isolated defects. Concrete current defects belong to `diagnose` unless the user supplied the defect as the architecture target.

Keep multiple candidates only while materially distinct structural choices remain live: owner, boundary, dependency direction, state ownership, lifecycle, caller-visible contract, abstraction, or consolidation. Do not rank with scores, confidence labels, deterministic tie-breakers, or discovery order. If choices remain tied, preserve the honest discriminator, unknown, or blocker.

Reason is not discovery or candidate-generation authority. Consult shared `reason` at its judgment checkpoints, including before committing to `target | no-design-change | blocker`; temporary Reason output never enters `architecture.md`.

## Outcomes and stops

Stop when one qualified target clearly dominates, remaining differences are cosmetic or downstream implementation choices, the cheapest missing discriminator cannot currently be obtained, no candidate demonstrates structural consequence, or further search cannot plausibly change `target | no-design-change | blocker`.

When a target qualifies, enter the Architecture Protocol with that target and cite the evidence that qualified it. When nothing qualifies, draft the same `architecture.md` handoff with selected architecture `no-design-change`; cite the bounded evidence checked and explain why no current or credible near-term structural consequence justifies architecture work. If a material discriminator is unavailable, report the blocker or unknown in `Evidence and Uncertainty` rather than manufacturing architecture work.

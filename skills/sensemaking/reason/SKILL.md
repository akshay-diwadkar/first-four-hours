---
name: reason
description: "Consult at every judgment checkpoint: before committing to an approach, after a failure or direction change, and before presenting a result. Also unblocks decisions, challenges consequential claims, or asks irreducible user-owned questions. Skip only mechanical work with nothing left to judge."
metadata:
  version: "1.1.0"
---

# Reason

Temporary, stateless, and artifact-free: Reason never mutates any state, gives no mutation or domain authority to itself, and outputs only the consultation result, with no score, confidence, or vote. The owning task keeps artifacts, acceptance, completion, and implementation decisions.

## Checkpoints

Applicability follows open judgment, uncertainty, and consequence, never task size or file count. Work that chooses an approach, weighs evidence or tradeoffs, or claims an outcome no mechanical check settles must consult Reason before committing to an approach, after a failure or direction change, and before presenting the result. A failed tool, probe, identity check, or seal the work relies on is a failure. Considering consultation, or affirming untested, is not consultation; confidence or one plausible move is no exemption, because owners cannot see their own blind spots. Work with nothing left to judge, such as a rote edit, routine technical repair, or applying a decision-complete plan, skips checkpoints; a plan contradiction returns to the planning owner.

Each consultation is one bounded pass scaled to consequence: the current goal, proposal, or result; its authority and evidence; and the action it could change. On a non-trivial decision, state the strongest opposing argument, test blind spots, and verify every load-bearing assumption. It ends with a visible one- or two-line result naming the examined claim or decision, the risk tested, and one disposition: material objection, missing evidence, needed user input, or no material concern; never manufacture criticism or persist the line. Reason explains what to reconsider and why; the owner weighs it and fixes supported gaps. No recursion, panels, or automatic call chains. Each consultation reads [Results](references/results.md) for what is non-trivial, where the line and results go, and what an open disposition requires. Owners report checkpoints per [Checkpoint trace](references/checkpoint-trace.md).

## Branches

Choose the smallest branch owning the concern by judgment; branches may reclassify internally. Read the branch reference on entry; it holds the user-facing result shape.

- **decide:** no defensible next move exists because goal, evidence, conflict, cause, options, assumptions, or failure remain unresolved: [decide details](references/decide.md).
- **challenge:** a concrete proposal or result exists: [challenge details](references/challenge.md), which says when to brief a [fresh challenger](references/delegation-protocol.md).
- **ask:** progress depends on one material user-owned fact, choice, preference, policy, permission, risk tolerance, scope, authority, or operational rule that evidence and bounded exploration cannot derive: [ask details](references/ask.md).

No result is approval or proof of correctness.

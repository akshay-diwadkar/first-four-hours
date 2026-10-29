---
name: architect
description: Decide repository-grounded architecture before blueprint planning; use for boundary, dependency-direction, state ownership, abstraction, consolidation, module or class structure, subsystems, or no-targets.
metadata:
  version: "1.0.1"
---

# Architect

## Authority

Decide architecture. If no target is supplied, run [Opportunity Discovery](references/opportunity-discovery.md) before selecting target, `no-design-change`, or blocker. Seal ignored `.first-four-hours/architectures/<slug>/architecture.md` for `blueprint`; do not edit implementation files.

Stop at architecture. Never classify implementation tier, perform a full propagation sweep, prescribe file-level edits, write test or execution blueprints, order migrations or rollout, or attack an implementation. Those responsibilities belong to `blueprint`. Paths and optional views are evidence bearings, not edit instructions.

## Workflow

1. Follow [Architecture Protocol](references/architecture-protocol.md). Consult `reason` before committing to an approach, after a failure or direction change, and before sealing. Load [Structural Techniques](references/structural-techniques.md) only where the protocol or discovery points to it.
2. Use [Bounded Delegation Protocol](references/delegation-protocol.md) only for optional evidence workers or earned specialist review.
3. Draft from the [Handoff Template](references/architecture-template.md).
4. Use [Worked Example](references/worked-examples.md) only for optional alternatives, user policy, or view calibration, and [Calibration Examples](references/calibration-examples.md) before framing a target inside one module or class or selecting any structure other than `no-design-change`.
5. Seal once:

```bash
python /absolute/skill-root/scripts/cli.py --repo-root /absolute/repo \
  --input draft=/absolute/architecture-draft.md \
  --input slug=<architecture-slug> --format json run
```

Persist settled structural truth: pressure or no-change outcome, owner/boundary, constraints, selected architecture, consequences, evidence, trust-relevant unknowns, and any user-owned policy.

## Completion

Complete only when the command returns `status: complete` with `result.path` at `.first-four-hours/architectures/<slug>/architecture.md`; report `result.git_ignored`. If sealing fails, repair the named draft or workspace conflict and rerun. If evidence changed, refresh and seal against the new snapshot. Final and stop reports trace `reason` checkpoints per its Checkpoint trace. End with one optional next step fitting this outcome: a fenced, self-contained prompt naming any repository, issue, PR, or artifact it needs, or say none is needed. Only a "yes" starts it, via any skill it names, but the user runs a `charter`, `diagnose`, or `ticket` step as its `/<skill>` command.

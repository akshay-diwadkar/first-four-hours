---
name: construct
description: "Implement an existing sealed `blueprint.md`; run its Verification; report completion, incomplete verification, or contradiction; skip planning-required work."
metadata:
  version: "1.0.0"
  implicit-authority: sealed-blueprint
---

# Construct

## Authority

Construct persists no execution state and creates no execution artifact. Blueprint owns every planning decision; Git worktree state owns the implementation delta. Discovery is evidence, not authority: it cannot expand a sealed Blueprint beyond Atlas upkeep. The Blueprint stays byte-for-byte unchanged. Preserve unrelated dirty work; execution requires a Git worktree. Scripts prove mechanics only; the agent owns attribution, scope truth, and completion.

## Command

```bash
python <construct>/scripts/cli.py --repo-root <repo> --input blueprint_file=<blueprint.md> --input phase=before --format json verify
```

Judge criteria first; follow `next_command` when present, else `required_action`.

## Smooth execution loop

1. **Intake.** Read [Execution contract](references/execution-contract.md) once, then run `verify` before for fresh work, `status` for resume. For dirty targets, non-Git paths, concurrent, destructive, or recovery work read [Safety](references/safety-and-recovery.md). Uncertain progress requires caller reconciliation. Read the whole Blueprint before editing.
2. **Implement** each `### N.` in order. `apply` writes declared blocks, never by hand: with `Red:`, `apply` Frozen, `prove` red, confirm it shows that defect, then `apply` Exact. Implement the rest, then `prove` green with the caller-held next unused attempt and follow its forward guidance. Repair only what Blueprint settles; otherwise stop as `plan-contradiction`.
3. **Verify.** After Atlas upkeep, run `verify` phase `after`; judge every `Expect:`. Repair locally only when Blueprint fixes the answer, then `reverify` from the earliest invalidated Run line. A shown declared `Incomplete:` outcome ends as `verification-incomplete` after step 4. Else stop with plan-contradiction evidence. Timeout or mutation failures are unsafe, never `reverify`.
4. **Reconcile and report.** Compare the final diff against the sealed Blueprint once: every instruction realized, no unauthorized change, constraints preserved. When earned, an [Earned Conformance Review](references/delegation-protocol.md) confirms it. Report instructions, upkeep repairs and listed pointers, proof and before-implementation verification results, each after-implementation Run with its `Expect:` and whether its output met it, unrecoverable red gaps, notices, and whether protected paths and HEAD are unchanged.

## Exceptions

Stopping ends the Construct run: `plan-contradiction`, `protected-work-conflict`, or `safety-contradiction`, reported with exact evidence. The execution contract's Stopping section owns what happens next.

Final and stop reports end with one optional next step fitting this outcome, after a stop its recovery owner's: a fenced, self-contained prompt naming any repository, issue, PR, or artifact it needs, or say none is needed. Only a "yes" starts it, via any skill it names, but the user runs a `charter`, `diagnose`, `pr`, or `ticket` step as its `/<skill>` command.

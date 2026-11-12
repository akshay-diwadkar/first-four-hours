# Construct handoff

This caller role starts only after the user's yes to a Construct step, outside Blueprint's planning authority. Construct owns the run, its report, and its rules; you only observe, never amending, resealing, or repairing the plan or the change.

## Launch

Record `git rev-parse HEAD`, `git status --porcelain=v1 --untracked-files=all`, and `git hash-object` of the sealed `blueprint.md`, its `request.md`, and each listed path outside its `**Location:**` paths and workspace (a rename by its new path, a missing file as absent): that is protected work. Launch the harness's `ffh-constructor` (or `ffh_constructor`) when it launches, else a generic subagent, with the Construct prompt unchanged plus: return the full final or stop report, its next-step prompt, and whether a conformance review was earned, run, or earned but not launched.

## Confirm, then report

The returned report is a claim; confirm it from the repository before reporting, judging by the installed Construct skill's `SKILL.md`. A failed check leaves the run unconfirmed:

- Rerun the recorded commands: moved HEAD, a changed protected path, `blueprint.md`, or `request.md`, or a new entry outside the Locations and workspace fails, next step Construct's `safety-contradiction` recovery.
- Completion or `verification-incomplete`: run that skill's `scripts/cli.py` `verify` with phase `after` and judge every `Expect:` yourself. Completion stands only when every Run passes and meets its `Expect:`; `verification-incomplete` stands when the output shows its declared `Incomplete:` outcome or a pass. Otherwise it fails, next step a fresh Construct run.
- A stop, or no recognizable report: run bare `status`, report its result beside the stop, and name any contradiction with the reported stop point.
- Conformance: launch an earned review the run skipped (a silent report never means not earned) as its `delegation-protocol.md` directs and recheck each finding, or, when no subagent launches, report it earned and not run. A confirmed finding means the run is not complete; next step a fresh Construct run when the plan settles the fix, else a Blueprint amendment citing it.

Relay Construct's report and stop classification unchanged, then each check's result, ending with exactly one next step: Construct's, unchanged, when confirmed; otherwise yours, showing Construct's as superseded.

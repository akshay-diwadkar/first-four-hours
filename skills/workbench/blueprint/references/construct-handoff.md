# Construct handoff

This caller role starts only after the user's yes to a Construct step, outside Blueprint's planning authority: Construct owns the run and its report, your checks only observe, and you never amend, reseal, or repair the plan or the change yourself.

## Launch

Record `git rev-parse HEAD` and `git status --porcelain=v1 --untracked-files=all`, then `git hash-object` of the sealed `blueprint.md`, its `request.md`, and each listed path that is neither one of its `**Location:**` paths nor in its workspace, taking a rename's new path and recording a missing file as absent: those paths are protected work. Launch the harness's `ffh-constructor` (or `ffh_constructor`) when it launches, else a generic subagent. Brief it with the Construct prompt unchanged, adding: return Construct's full final or stop report, with its next-step prompt and whether a conformance review was earned, run, or earned but not launched.

## Confirm, then report

The returned report is a claim; confirm it from the repository before reporting:

- Rerun the recorded commands. The run is not confirmed when HEAD moved, a protected path, `blueprint.md`, or `request.md` changed, or a new entry is neither a `**Location:**` path nor in the workspace; its next step is Construct's `safety-contradiction` recovery.
- For a reported completion or `verification-incomplete`, run the installed Construct skill's `scripts/cli.py` `verify` with phase `after` and judge every `Expect:` yourself. Completion stands only when every Run passes and meets its `Expect:`; `verification-incomplete` stands when the output shows its declared `Incomplete:` outcome or a pass. Otherwise the run is not confirmed, with a fresh Construct run as its next step.
- For a reported stop, or no recognizable report, run bare `status` and report its result beside it, naming any contradiction with the reported stop point.
- Decide from the installed Construct skill's `references/delegation-protocol.md` whether its conformance review was earned; a silent report never means not earned. Launch an earned review the run did not run as that file directs, and recheck each finding. A confirmed finding means the run is not complete: its next step is a fresh Construct run on the same plan when that plan settles the fix, else a Blueprint amendment with the finding as evidence. When no subagent launches, report the review as earned and not run.

Then relay Construct's report and stop classification unchanged, followed by each check above and its result. End with exactly one next step: Construct's, unchanged, when the run is confirmed; otherwise yours, with Construct's shown as superseded.

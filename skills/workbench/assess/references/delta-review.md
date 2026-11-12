# Delta review

Read this when an earlier assessment of this change exists under `.first-four-hours/assessments/`; use the most recently sealed one.

Review the delta when `check` passes an earlier assessment of this change or refuses it only with `result.target_moved`, its result was not `blocked`, its `Head revision` is an ancestor of this head, and the authoritative requirements are unchanged. A repair plan made from an earlier assessment's findings leaves the authoritative requirements unchanged unless its request adds or changes a requirement; a limitation the user accepted in that request does not change them. The delta covers:

- every change from that head to this one, under the axes, and whatever those changes propagate to;
- whether each earlier finding's `required_truth` now holds;
- each open gap: any limitation of that assessment, or path or surface it left unexamined, except a path its `limitations` record as not re-inspected because an earlier assessment examined it;
- changes from that assessment's `Base revision` to the current base that touch the change's paths or contracts, whether or not they are merged in.

In `limitations`, name the assessment's head and each path you carry forward, recording that it was not re-inspected because an earlier assessment examined it, so a `clear` reads as clear for the delta on top of that assessment, and state as a gap each open gap you did not close and anything in the delta you left unexamined. A defect you notice in unchanged code is still a finding.

Assess the whole change instead when no earlier assessment qualifies, as when the requirements changed or a rebase or amend left no such ancestor; when the delta rewrites most of the change or gives concrete reason to doubt the earlier coverage; or when the user asks.

In the report, also say the result covers only the delta on top of the earlier assessment, naming its head, and that `limitations` names what was not re-inspected.

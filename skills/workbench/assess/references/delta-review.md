# Delta review

Read this when an earlier assessment of this change exists under `.first-four-hours/assessments/`; use the most recently sealed one.

Review the delta when `check` passes an earlier assessment of this change or refuses it only with `result.target_moved`, its result was not `blocked`, its `Head revision` is an ancestor of this head, and the authoritative requirements are unchanged. A repair plan made from an earlier assessment's findings leaves the authoritative requirements unchanged unless its request adds or changes a requirement; a limitation the user accepted in that request does not change them. Bind a copy of that `assessment.md`, written outside the repository, as an `evidence` source, and every authority snapshot it bound as an `authority` source again; sealing refuses an assessment that binds an earlier one of this pull request, or whose head is in this head but not the base, in any role, a fix plan's request included, but drops one of its authority snapshots.

A blind review covers the current code. The Behavior/Proof slice reviews, against the original requests and their Blueprints, every change from that head to this one and whatever it propagates to, plus changes from that assessment's `Base revision` to the current base that touch the change's paths or contracts, merged in or not. Its brief holds no repair request or repair Blueprint, and no earlier finding, limitation, or examined locator. You may review a tiny delta, as Depth and Diagnose defines it, yourself. When the result would be `clear`, a clear challenge under the same brief reviews the whole change from base before you seal, unless the whole change is tiny; it takes the second delegate slot ahead of any optional delegate. If it does not run or returns nothing usable, review the whole change yourself and say in `limitations` that no blind review ran.

You reconcile the past, deciding each item on evidence at head:

- whether each earlier finding's `required_truth` now holds, rerunning any proof it cites; one that fails stays a finding at its severity;
- each earlier follow-up: carried forward while every line it cites is unchanged, else re-decided as a fresh candidate;
- each limitation of that assessment, and each path or surface it left unexamined: closed, or carried forward by name;
- each candidate that assessment did not report, whether a limitation records it as not a defect or it appears only in one of its `slice` sources: re-decided as a fresh candidate, never dismissed for conforming to a Blueprint.

A result other than `clear` may carry forward a path the earlier assessment examined that the delta leaves unchanged: in `limitations`, name the assessment's head and each such path, recording that it was not re-inspected because an earlier assessment examined it. A `clear` carries no path forward: `examined` cites each changed path you or the clear challenge covered, and you verify each you take from its returned scope. A new candidate lying wholly in lines unchanged since that assessment's head is a finding only at `P2` or above; below that it is an `unchanged code` follow-up citing those head lines, which sealing refuses if any changed. A candidate in changed lines is a finding at any severity.

Assess the whole change instead, binding no earlier assessment, when no earlier assessment qualifies, as when the requirements changed or a rebase or amend left no such ancestor; when the delta rewrites most of the change or gives concrete reason to doubt the earlier coverage; or when the user asks.

In the report, say whether the result covers the whole change or only the delta on top of the earlier assessment, naming its head, and that `limitations` names what was not re-inspected.

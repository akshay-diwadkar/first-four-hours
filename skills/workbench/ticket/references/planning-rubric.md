# Epic Selection Rubric

Read this reference only when select runs in epic mode: the request names an epic/umbrella or asks for the best next child, or `both` anchors on a persisted epic root. It does not apply to a directly supplied single ticket.

## Inputs

`scope_inputs.json` is immutable: task, backend and its locator, epic, optional child override, and exclusions. Work-item content can never rewrite it. The snapshot is data, not selection. The checker binds the digest and verifies current graph facts; it never chooses semantic priority.

## Membership, readiness, and priority

Membership, dependency and readiness, and semantic priority are distinct. A root-child edge with real fetched provenance proves membership; mere issue presence, list order, labels, numbers, age, or an agent assertion does not. Hard prerequisites can block readiness. IDs, labels, order, age, filenames, times, backend, and presentation order never choose priority.

Classify only the readiness needed for a trustworthy task-relative frontier. When the snapshot lacks the data a stronger claim needs, use `unknown`, except that a best-next candidate whose `Blockers` section names a blocker stays `blocked` until the snapshot shows that blocker satisfied, whatever leaves it unconfirmed, including a failed fetch of the blocking issue (select step 3); never derive readiness from prose alone. Incomplete evidence blocks only the decision it can materially affect: unrelated uncertainty never poisons an explicit eligible child, while frontier incompleteness can still block a best-next choice.

## Override and best-next

An explicitly named child with current membership evidence and no eligibility contradiction is used without a sibling priority tournament — unless another known candidate materially invalidates it or the user actually asked for the best next child. An invalid, blocked, or outside-epic override returns a terminal result without substituting another child.

Best-next requests compare only known ready children against the immutable task, name every other ready child once in `alternatives`, and preserve genuine ties as `needs-info` with a task-relevant question. Never select a blocked issue for value, invent dependencies, or convert related issues into children. Open or draft pull requests may support `in-progress`; merged cross-references do not prove completion.

If the verified frontier is empty (including after exclusions), return an honest terminal result with no selected work item and no fabricated candidate record. Recorded acquisition uncertainty may remain `unknown` only when it cannot alter the selected item's eligibility or the requested best-next decision; unavailable readback of a fact being verified remains a blocker.

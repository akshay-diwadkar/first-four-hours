# How skills hand work to each other

Every skill can be used on its own. This page explains the real connections between skills: what one skill produces that another can use, and who decides when the next skill starts. It does not describe a required lifecycle; use one skill when that is enough.

## You start the next skill

A skill that finishes ends with at most one suggested next step, written as a ready-to-run prompt. Only your yes starts it. You run a step for `diagnose`, `pr`, or `ticket` yourself, because those skills start only when you invoke them. A handoff makes the next step possible; it never starts it.

## Handoffs live in ignored folders

A skill that hands work to another seals it in its own folder under `.first-four-hours/` at the repository root. The skill adds a rule for that folder to the worktree-local `.git/info/exclude`, so Git ignores it without a committed `.gitignore` entry. A skill stops instead of writing when its folder is already tracked by Git, or when that folder or `.first-four-hours/` is a link or not a directory.

| Skill | Handoff |
| :--- | :--- |
| Architect | `.first-four-hours/architectures/<slug>/architecture.md` |
| Assess | `.first-four-hours/assessments/<slug>/assessment.md` |
| Blueprint | `.first-four-hours/blueprints/<task-slug>/blueprint.md` and its `request.md` |
| Diagnose | `.first-four-hours/diagnoses/<slug>/diagnosis.md` |
| Ideate | `.first-four-hours/ideations/<slug>/ideation.md` |
| Router | `.first-four-hours/routes/<slug>/route.md` |
| Ticket | `.first-four-hours/ticket-scopes/<slug>/ticket-scope.md` |

Scribe keeps its support bundle the same way, in `.first-four-hours/document-bundles/<slug>/document-bundle.json`.

Deliverables you asked for are not handoffs and stay committable: Scribe's `document.md`, Ticket's local work-item store, the Atlas wiki, and the Learning skills' files under `.learning/<subject>/`. Construct and Reason write no artifact, and PR writes its draft outside the repository.

## Planning and execution

[Blueprint](../skills/blueprint.md) owns every planning decision; [Construct](../skills/construct.md) owns carrying them out. Construct may fix its own coding mistakes inside a valid plan, but when the plan is stale, wrong, or incomplete against the actual code it stops with `plan-contradiction` instead of redesigning. The fix is a new Blueprint run in a fresh task folder, followed by a fresh Construct run. Review findings from [Assess](../skills/assess.md) go the same way, so the planner keeps every decision.

## Inputs to planning

Three skills produce work that Blueprint can plan from, and you decide whether to start it:

- [Diagnose](../skills/diagnose.md) finds causes. Name one finding when you ask Blueprint to plan a fix. Diagnose's advisory directions are leads, not a chosen design.
- [Architect](../skills/architect.md) decides structure. Blueprint plans around that decision instead of reopening it.
- [Ticket](../skills/ticket.md) `select` narrows one ready ticket into a `plan-ready` scope.

## Inside a Blueprint run

Blueprint brings in other help within its own run, not as separate stages:

- It asks [Ideate](../skills/ideate.md) for options only when no viable solution is apparent or the evidence cannot rank the directions. You make the final selection unless you already chose or delegated it.
- A separate fresh-context subagent challenges the draft before sealing. Without one, Blueprint does not seal.

## Reason checkpoints

Architect, Assess, Diagnose, Ticket, Ideate, Scribe, Tutor, and Examiner consult [Reason](../skills/reason.md) at their own judgment points, such as before committing to an approach and before presenting a result. These consultations happen inside the owning skill and leave no file; they are not steps you run. You can also start Reason yourself.

## Routing

[Router](../skills/router.md) writes a route of concrete skills, never domains, as far as the next steps are known, and stops where a step depends on a result that does not exist yet. It runs none of them. When the route runs out, the target may still need a fresh route.

## Atlas upkeep

[Atlas](../skills/atlas.md) is optional orientation; the project files stay the truth. Whoever changes a file that an Atlas pointer cites updates the pointer in the same work. Construct repairs links to files its plan deletes and lists other pointers the change may affect, for the next plan to handle.

## Review and pull requests

[Assess](../skills/assess.md) is read-only and grants no approval or merge authority. [PR](../skills/pr.md) opens a pull request only after you confirm its exact text, and never merges. Every commit and merge stays yours.

## Learning

[Tutor](../skills/tutor.md) and [Examiner](../skills/examiner.md) each work alone; moving between them is optional. When both are used for a subject they share one study plan, `.learning/<subject>/study-plan.html`: Tutor owns the learning sequence, and Examiner owns the examination section.

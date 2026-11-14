# How skills hand work to each other

Every skill can be used on its own. This page explains the real connections between skills: what one skill produces that another can use, and who decides when the next skill starts. It does not describe a required lifecycle; use one skill when that is enough.

## You start the next skill

A skill that finishes ends with at most one suggested next step, written as a ready-to-run prompt. Only your yes starts it. You run a step for `charter`, `diagnose`, or `ticket` yourself, because those skills start only when you invoke them. A handoff makes the next step possible; it never starts it.

## Handoffs live in ignored folders

A skill that hands work to another seals it in its own folder under `.first-four-hours/` at the repository root. The skill adds a rule for that folder to the worktree-local `.git/info/exclude`, so Git ignores it without a committed `.gitignore` entry. A skill stops instead of writing when its folder is already tracked by Git, or when that folder or `.first-four-hours/` is a link or not a directory.

| Skill | Handoff |
| :--- | :--- |
| `/architect` | `.first-four-hours/architectures/<slug>/architecture.md` |
| `/assess` | `.first-four-hours/assessments/<slug>/assessment.md` |
| `/blueprint` | `.first-four-hours/blueprints/<task-slug>/blueprint.md` and its `request.md` |
| `/charter` | `.first-four-hours/charters/<slug>/charter.md` |
| `/diagnose` | `.first-four-hours/diagnoses/<slug>/diagnosis.md` |
| `/ideate` | `.first-four-hours/ideations/<slug>/ideation.md` |
| `/router` | `.first-four-hours/routes/<slug>/route.md` |
| `/temper` | `.first-four-hours/test-audits/<slug>/test-audit.md` |
| `/ticket` | `.first-four-hours/ticket-scopes/<slug>/ticket-scope.md` |

`/scribe` keeps its audit report the same way, in `.first-four-hours/scribes/<slug>/scribe-audit.md`. Its support bundle is a temporary file outside the repository.

`/charter`'s `charter.md` is not sealed: it is a living definition revised in place, and the project's authority until `/charter` publishes it as a GitHub issue. After a verified publication the issue owns the definition and the file points to it.

Deliverables you asked for are not handoffs and stay committable: `/scribe`'s documents, `/ticket`'s local work-item store, and the Learning skills' files under `.learning/<subject>/`. `/construct` and `/reason` write no artifact, and `/pr` writes its draft outside the repository.

## Project definition

[`/charter`](../skills/charter.md) settles what a whole project is for before any tickets exist. [`/ticket`](../skills/ticket.md) `persist` can split a `ready` charter into tickets: from a published charter it reuses the umbrella issue as the epic, and from a local-only charter it takes the file as its authority. `/charter` never splits the work itself, and you decide whether to start `/ticket`.

## Planning and execution

[`/blueprint`](../skills/blueprint.md) owns every planning decision; [`/construct`](../skills/construct.md) owns carrying them out. `/construct` may fix its own coding mistakes inside a valid plan, but when the plan is stale, wrong, or incomplete against the actual code it stops with `plan-contradiction` instead of redesigning. The fix is a new `/blueprint` run in a fresh task folder, followed by a fresh `/construct` run. Review findings from [`/assess`](../skills/assess.md) go the same way, so the planner keeps every decision.

## Inputs to planning

Five skills produce work that `/blueprint` can plan from, and you decide whether to start it:

- [`/diagnose`](../skills/diagnose.md) finds causes. Name one finding when you ask `/blueprint` to plan a fix, or ask `/architect` first when that fix needs a structural decision. `/diagnose`'s advisory directions are leads, not a chosen design.
- [`/architect`](../skills/architect.md) decides structure. `/blueprint` plans around that decision instead of reopening it.
- [`/ticket`](../skills/ticket.md) `select` narrows one ready ticket into a `plan-ready` scope.
- [`/assess`](../skills/assess.md) reviews a change. When its result is `findings`, `/blueprint` plans the repair from the sealed `assessment.md`: every finding, or only the ones you name.
- [`/temper`](../skills/temper.md) audits a test suite. `/blueprint` plans from the sealed `test-audit.md` the same way, every finding or only the ones you name, and `/construct` reruns `/temper`'s `verify` to show the remaining tests still catch each planned finding's mutants.

## Inside a Blueprint run

`/blueprint` brings in other help within its own run, not as separate stages:

- It asks [`/ideate`](../skills/ideate.md) for options only when no viable solution is apparent or the evidence cannot rank the directions. You make the final selection unless you already chose or delegated it.
- `/blueprint` attacks its own draft before sealing. A risky plan also gets one separate fresh-context challenger, and without one `/blueprint` does not seal that plan.

## Reason checkpoints

`/architect`, `/assess`, `/blueprint`, `/charter`, `/diagnose`, `/temper`, `/ticket`, `/ideate`, `/scribe`, `/tutor`, and `/examiner` consult [`/reason`](../skills/reason.md) at their own judgment points, such as before committing to an approach, after a failure, and before presenting a result. These consultations happen inside the owning skill and leave no file; they are not steps you run. You can also start `/reason` yourself.

## Routing

[`/router`](../skills/router.md) writes a route of concrete skills, never domains, as far as the next steps are known, and stops where a step depends on a result that does not exist yet. It runs none of them. When the route runs out, the target may still need a fresh route.

## Review and pull requests

[`/assess`](../skills/assess.md) is read-only and grants no approval or merge authority; it posts its findings to a pull request only after you confirm the exact comment. [`/pr`](../skills/pr.md) opens a pull request, or updates its description, only after you confirm its exact text, and never merges. Every commit and merge stays yours.

## Learning

[`/tutor`](../skills/tutor.md) and [`/examiner`](../skills/examiner.md) each work alone; moving between them is optional. When both are used for a subject they share one study plan, `.learning/<subject>/study-plan.html`: `/tutor` owns the learning sequence, and `/examiner` owns the examination section. `/tutor` records the gaps `/examiner`'s marking diagnoses, and `/examiner` reads the open Unresolved items in `/tutor`'s lessons when recommending topics. For an examination goal, each `/tutor` topic's name starts with its syllabus area. Each section says what it shows: `/tutor`'s progress shows understanding, and `/examiner`'s coverage shows examination performance. Where they disagree on an area, each notes it in its own section and the next step follows the coverage. When either changes its schedule and the sessions no longer fit, it says so and offers choices instead of changing the other's section.

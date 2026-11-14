# Choose a skill

Start from the problem in front of you, not from how the suite is organized. Pick the smallest skill that deals with what is most likely to cost you time later. A small, clear request may need no skill at all.

## Find your situation

| You are dealing with | Start with |
| :--- | :--- |
| Something is wrong and you do not know why | [`/diagnose`](../skills/diagnose.md) |
| A change another session, agent, or cheaper model will carry out, whose mistakes would show up late, or whose decisions must outlast the session | [`/blueprint`](../skills/blueprint.md) |
| A sealed `/blueprint` plan that is ready to carry out | [`/construct`](../skills/construct.md) |
| A structural question, such as a boundary, dependency direction, or module structure | [`/architect`](../skills/architect.md) |
| A finished change you need to trust before merging | [`/assess`](../skills/assess.md) |
| A rough idea for a whole app or project whose purpose, scope, and success are not agreed yet | [`/charter`](../skills/charter.md) |
| Work too big for one session, or a backlog to pick the next ready ticket from | [`/ticket`](../skills/ticket.md) |
| Several possible directions and no clear way to choose | [`/ideate`](../skills/ideate.md) |
| A decision that is stuck, or rests on an assumption you doubt | [`/reason`](../skills/reason.md) |
| Not knowing which skill comes next, or work that spans several skills | [`/router`](../skills/router.md) (ask in plain words) |
| A runbook, setup guide, error message, or other technical document that must match its sources, or a check of an existing one | [`/scribe`](../skills/scribe.md) |
| A subject you want to understand | [`/tutor`](../skills/tutor.md) |
| A written examination to practise for | [`/examiner`](../skills/examiner.md) |
| A fresh install to finish, or subagents to set up or refresh on the models you choose | [`/provision`](../skills/provision.md) |

The table covers common situations, not every skill; [the skill index](../skills/README.md) lists every skill, and each skill page says when to use another skill instead.

## Combine skills only when you need to

Every skill works alone. A skill's handoff makes the next step possible, but never starts it. When one skill is not enough, for example:

- `/diagnose` finds a cause, then `/blueprint` plans a fix for one finding and `/construct` carries out the plan. When that fix first needs a structural decision, `/architect` settles it before `/blueprint`.
- `/architect` settles structure, then `/blueprint` plans around it.
- `/charter` settles what a project is for, then `/ticket` splits it into tickets.
- `/ticket` narrows one ready ticket, then `/blueprint` plans it.
- `/assess` findings go to a new `/blueprint` run rather than a direct edit.
- `/tutor` and `/examiner` can share one study plan for a subject.

[How skills hand work to each other](../concepts/handoffs.md) describes each real handoff.

## How the skills are grouped

The skills are grouped into three domains, Workbench, Sensemaking, and Learning, to help you understand the suite. The grouping is not a step in choosing. See [How the suite works](../concepts/how-the-suite-works.md) and [the skill index](../skills/README.md).

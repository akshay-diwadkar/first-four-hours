# Why First Four Hours exists

**Sharpen the axe first.**

> "Give me six hours to chop down a tree, and I will spend the first four sharpening the axe."

The line is usually credited to Abraham Lincoln, though there is no reliable record that he said it.

Coding agents don't sharpen. They swing.

## The lost hours

Coding agents are supposed to save time. You ask one for a change. It writes the code, runs the tests, and tells you it is done.

Then you find a missed requirement. A decision you already settled has been reopened. The fix works in isolation but breaks a caller. You explain the context again, review another patch, and start checking what "done" actually means.

Those are the lost hours: the time spent turning work that looks finished into work you can trust. They come from retries, rework, rediscovering context the agent already had, side quests, and the supervision all of that demands.

## The sharpening

First Four Hours is a collection of skills for coding agents. They help an agent understand the task, make grounded decisions, carry those decisions through execution, and check the outcome that matters. Clear plans, useful handoffs, and meaningful verification give each stage something solid to build on.

Small tasks stay light. Work with more ambiguity or consequence gets the care it needs. The principle behind every skill is to raise the floor while preserving the ceiling: give weaker agents enough structure to produce useful work, and leave stronger agents room to use their judgment. Contributors apply that principle through [the skill design philosophy](../../SKILL_PHILOSOPHY.md).

Some skills deliberately spend more effort up front, for example on a plan, so that less effort goes into correcting the result afterward. The first four hours aren't overhead. They're why the last two are enough.

## What it does not promise

- It does not make every task faster. Careful up-front work pays off when a mistake would be costly to find later; a small, clear task may need no skill at all.
- It does not make agent work correct without review. You still own the decisions that are yours, and every commit, pull request, and merge.
- It makes no measured claim about time saved, and no claim that one model or agent beats another.

## Beyond code

The same care applies to learning. The Learning skills teach any subject, technical or not, and write practice papers for written examinations. They belong to the suite because they share its approach: find the real goal, ground the work in sources, and check understanding instead of assuming it. They are not a remedy for coding rework.

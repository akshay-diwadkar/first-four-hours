# Why First Four Hours exists

**Sharpen the axe first.**

> "Give me six hours to chop down a tree, and I will spend the first four sharpening the axe."

The line is usually credited to Abraham Lincoln, though there is no reliable record that he said it. It survives anyway, because anyone who has done real work recognizes it.

Coding agents don't sharpen. They swing.

## The lost hours

It is late on a Thursday. You ask an agent for a change, and a little later it tells you it is done. The tests are green. The summary is confident. You almost merge it.

Then you read the diff. A requirement from the ticket is missing. A decision your team settled on Monday has been quietly reopened, because nothing told the agent it was settled. The fix works on its own and breaks the one caller nobody mentioned. So you explain the context again. You review another patch. You start checking what "done" actually means, and you stop trusting the word.

Those are the lost hours: the time spent turning work that looks finished into work you can trust. They come from retries, rework, rediscovering context the agent already had, side quests, and the supervision all of that demands. They rarely show up in a demo. They show up in review, on a Friday evening, or in production.

## Why agents swing

An agent sees the request in front of it, not the meeting where the constraint was agreed. Ask it to fix a symptom and it fixes the symptom. Ask it to update the callers and it decides, one caller at a time, what each one needs, inside edits you only see at the end.

That is not carelessness. It is judgment, deferred and hidden. A decision nobody makes before the work still gets made: during the work, by whoever is typing, where you cannot see it and where a wrong turn costs the most.

## The sharpening

First Four Hours is a collection of skills for coding agents. They help an agent understand the task, make grounded decisions, carry those decisions through execution, and check the outcome that matters. Clear plans, useful handoffs, and meaningful verification give each stage something solid to build on.

Most of the sharpening is a matter of order:

- Find the cause before choosing a fix. A symptom you silence is a cause you keep.
- Settle the decisions before editing. Judgment made up front is judgment you can see, question, and hand to someone else.
- Review a change against what it was supposed to do, not against what it says about itself.
- Write the decisions down. Sessions forget; files don't.

Small tasks stay light. Work with more ambiguity or consequence gets the care it needs.

## Raise the floor, preserve the ceiling

Not every agent is equally capable, and the suite does not pretend otherwise. A weaker agent, left alone, cannot see its own blind spots: it commits to the first plausible answer and presents it with the same confidence as a right one. So every skill gives it enough structure to do useful work: the questions worth asking, the evidence to collect, the point at which to stop.

A stronger agent does not need to be told how to think, and a skill that insisted would only get in its way. So the same skills leave it room to choose its own techniques and to go deeper when the evidence earns it.

That is the principle behind every skill: raise the floor while preserving the ceiling. Contributors apply it through [the skill design philosophy](https://github.com/akshay-diwadkar/first-four-hours/blob/main/SKILL_PHILOSOPHY.md).

Some skills deliberately spend more effort up front, for example on a plan, so that less effort goes into correcting the result afterward. The first four hours aren't overhead. They're why the last two are enough.

## What it does not promise

- It does not make every task faster. Careful up-front work pays off when a mistake would be costly to find later; a small, clear task may need no skill at all.
- It does not make agent work correct without review. You still own the decisions that are yours, and every commit, pull request, and merge.
- It makes no measured claim about time saved, and no claim that one model or agent beats another.

## Beyond code

The same care applies to learning. The Learning skills teach any subject, technical or not, and write practice papers for written examinations. They belong to the suite because they share its approach: find the real goal, ground the work in sources, and check understanding instead of assuming it. They are not a remedy for coding rework.

# Ideate

Ideate researches the possibilities for a goal, compares them, and recommends a direction, while you keep the final choice. It works for any goal; a repository is optional. It belongs to the Sensemaking domain.

## When to use it

- No workable solution is apparent yet, or several directions look viable and you need evidence to choose.
- You want possibilities beyond what the current project already does, judged for feasibility against your constraints.

## When to use something else

- Ordinary context gathering and a quick list of ideas do not need Ideate, unless you ask for structured ideation.
- To plan the chosen direction, use [Blueprint](blueprint.md). Ideate never plans or implements.
- To find the cause of a problem, use [Diagnose](diagnose.md).

## How to start it

Start it yourself with `/ideate`, or the agent may start it when your request matches. Blueprint may also call it while planning. For example (illustrative):

```text
/ideate : Find workable ways to cut our CI time in half without dropping test coverage.
```

## What happens

Ideate frames the goal and decision criteria, names the obvious answers first, then generates candidates from several angles that look past them, all before judging any. It tests, extends, or eliminates them with the cheapest evidence that could change the conclusion, compares the survivors with each other and with the current approach, and recombines their strongest parts. It searches the web for prior art and current practice as well as any repository, unless you tell it not to, and records when you opted out or web research could not be done. It keeps mechanisms the evidence supports apart from untested hypotheses. It consults [Reason](reason.md) at its judgment points.

## What you get

A sealed `ideation.md` in the ignored folder `.first-four-hours/ideations/<slug>/`. It opens with **What to do**, written so you can act on it without knowing the format:

- `Outcome`: `recommended direction`, with the viable choices; `run an experiment first`, with the experiment that would decide between them; or `research limit reached`, with what the research could not establish;
- `Final choice`: `yours to make`, `made by you`, or `delegated` within a scope you set. A recommendation is never your approval.

The goal, decision criteria, and research coverage, including the web searches run, follow it, then the evidence, the options explored, and what would change the answer.

## When it stops

Ideate never manufactures a winner. When the evidence cannot justify a recommendation, it names the experiment that would decide, or reports the research limit.

## Why it's built this way

**The failure it prevents.** A weaker agent does not know where to look. It stops at the first idea, or at what the repository already does, and misses workable directions that nobody has built here yet. Ideate searches the possibilities from several angles, either composing pieces into steps toward a goal or comparing alternatives, and tests them against your constraints.

**What it refuses, and why.** It never manufactures a winner. When the evidence cannot justify a choice, it names the experiment that would decide or reports the limit of the research. It keeps mechanisms the evidence supports apart from untested ideas, and it does not dismiss an idea only because no one has built it in this project. Its recommendation is never your approval: you make the final selection, and a choice you already made stands without being asked again.

**Floor and ceiling.** A weaker agent generates candidates before judging them, then tests each with the cheapest evidence that could change the conclusion. A stronger agent ranges as widely as the goal deserves, while the cost stays in proportion to the decision.

## Related skills

Inside a Blueprint run, Ideate returns its result to the planner, who asks for your selection while it is still open. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Ideate's contract](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/sensemaking/ideate/SKILL.md)

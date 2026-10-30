# Plan a change before your agent starts editing

An agent that starts editing before the decisions are made settles them halfway through, and redoes work when one turns out wrong. Blueprint settles every decision first and seals a plan. Construct then carries the plan out without reopening it, in the same session or a later one, possibly with a cheaper model.

## Use this when

- Another agent, a later session, or a cheaper model will implement it.
- A mistake would show up late or silently, or the decisions need to outlast this conversation.
- You know the outcome you want.

Size and stakes alone do not decide it. [Blueprint](../skills/blueprint.md) explains when your agent's plan mode is enough and what Blueprint gives you instead.

## Use something else when

- The cause of a problem is unknown: [Fix the bug without patching the symptom](fix-a-bug.md).
- The right structure is the open question: [Settle the structure before agents add parallel machinery](settle-structure.md).
- The change is finished and needs review: [Trust a change before you merge it](review-before-merge.md).
- The same agent will make the change while you watch, the path is obvious, and mistakes show up within minutes: your agent's plan mode is enough ([Blueprint](../skills/blueprint.md)).
- The edit is small and clear: it needs no plan.

## Steps

1. Start Blueprint with the outcome, the constraints, and what must not change.
2. Answer only the questions it asks. If it shows you directions from [Ideate](../skills/ideate.md), the choice is yours, and its recommendation is not your approval.
3. Read the sealed plan's Goal summary. The seal proves the plan's shape and its binding to the files it read. Nothing is implemented yet.
4. Start Construct on the sealed plan in a Git worktree.
5. Read Construct's report and settle the conditions it lists as `Owner gate:`. Then commit and open a pull request yourself, or with [PR](../skills/pr.md).

## A worked scenario

*Illustrative: Larder is a made-up project, and this is not a recorded run. Excerpts are shortened.*

Someone is scraping Larder's public search endpoint. You want rate limiting without breaking the partner integrations that call it all day.

```text
/blueprint : Plan rate limiting for Larder's public search endpoint; existing API clients must keep working unchanged.
```

Blueprint asks one question: should partner API keys be exempt? That is a product choice, and the answer changes the plan, so it is yours. Blueprint does not ask where the limiter should go or how to test it; it reads the middleware chain and decides. While grounding, it finds that Larder already has a trusted helper for the client address, and plans to reuse it instead of reading a header any client could forge.

Before sealing, the challenger reads the draft the way a faithful executor with no design authority would follow it, and notices that `/search/suggest` shares the search handler. A faithful executor would have limited it too, without anyone deciding to. The planner makes that explicit, then seals the plan in `.first-four-hours/blueprints/search-rate-limit/`. [Anatomy of a sealed blueprint](../concepts/anatomy-of-a-blueprint.md) walks through this plan section by section.

```text
/construct : Implement the sealed blueprint in .first-four-hours/blueprints/search-rate-limit/blueprint.md.
```

Construct checks that the cited files have not changed since planning, then applies the steps in order. It writes the test from the cases the plan describes, each with its input, expected result, and the wrong implementation it rejects, sees it fail on today's code and pass after the change, runs the plan's verification, and compares the final diff with the plan. Its report ends with one pending item, the owner gate: the operations lead must confirm the limit suits production traffic. Nothing is committed until you decide.

## You are done when

Construct's report shows every instruction applied, the plan's verification passed, and the diff matching the plan, and you have settled its owner gates. The agent saying it is done is not the signal.

## If it goes wrong

- Blueprint will not seal: it is waiting on a question only you can answer, it is reporting a research limit for the direction the plan needs, or no separate subagent could run its challenge. Answer the question, decide what to do about the limit it reports, or run it where a subagent is available ([Blueprint](../skills/blueprint.md)).
- Construct stops with `plan-contradiction`: run a new `/blueprint` with the original request and Construct's evidence, then a fresh `/construct`. Never patch the plan ([Construct](../skills/construct.md)).
- Construct reports `verification-incomplete`: run it again when the environment is healthy. An incomplete check is never a pass ([Construct](../skills/construct.md)).
- Construct stops any other way: follow the table on [Construct](../skills/construct.md).

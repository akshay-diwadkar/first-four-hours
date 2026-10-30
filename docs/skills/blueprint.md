# Blueprint

Blueprint plans a repository change before anyone edits code. It settles every decision, grounds each one in the real project, and seals a plan that a fresh, weaker agent can carry out without making engineering choices of its own. It belongs to the Workbench domain.

## When to use it

- Someone other than the agent planning it will carry the change out: another session, a cheaper model, a headless or overnight run, a parallel agent, or a person.
- The context will not survive the work, such as a long change or one you expect to resume later.
- A mistake would show up late or silently: a migration, a compatibility promise, a public interface, an auth or security boundary, or a change that ripples across many consumers.
- The happy path is easy but the edges are not: corrupt state, cancelled processes, stale caches, partial failure.
- You want to review the decisions separately from the code, or plan mode already drifted from the plan you approved.
- You want a cheaper model to do the implementation. Comparable quality at lower cost is an aim of this design, not a measured guarantee.

Size and stakes alone do not decide it. Blueprint or plan mode, below, explains when your agent's built-in plan mode is enough.

## When to use something else

- To carry out a sealed plan, use [Construct](construct.md). Blueprint never implements.
- If the right structure is the open question, decide it first with [Architect](architect.md).
- If the cause of a problem is unknown, find it first with [Diagnose](diagnose.md).
- A small, clear edit may need no plan at all.

## Blueprint or plan mode

Many coding agents have a built-in plan mode: the agent proposes a plan, you approve it, and the same agent carries it out. Blueprint is not a more careful plan mode. Plan mode gets your consent before the work starts. Blueprint hands the work over, so that someone else, later, in another context, can carry it out without making engineering decisions.

**An itinerary and a schematic.** A plan-mode plan is an itinerary. The same agent carries it out in the same session and improvises around obstacles as it goes, and that is by design. A blueprint is a schematic. Every decision is settled before editing, a fresh-context challenger attacks it against the code, and it is sealed with the proof of completion fixed in advance: verification commands with their expected results, and a named check, or a named owner, behind each completion condition. Construct does not improvise. When the code disagrees with the plan, it stops with `plan-contradiction`.

**Where judgment lives.** In plan mode, judgment happens during execution, hidden in the edits. "Update the callers" is enough of a plan, because the agent finds the callers and decides each one as it goes. In Blueprint, judgment happens before execution, and an adversary checks it rather than you only approving it: the challenger hunts for the input, exit path, or consumer the plan missed.

**What the cost buys.** Plan mode does not avoid the cost of judgment. It defers it and hides it inside the work, where a wrong turn costs the most. Blueprint pays that cost up front and makes it visible, even when the change would have gone fine. It can be cheaper overall when execution is delegated, repeated, or resumed, because the judgment is paid once and the execution can use a cheaper model; like the cheaper-model aim above, that is not a measured result. Stakes alone do not decide it: a low-stakes change handed to a cheaper model still benefits from a schematic, and a high-stakes change you steer live, diff by diff, may be well served by an itinerary.

**Blueprint's limits.**

- A seal is mechanical. It proves the plan's shape and its binding to the files it read; whether the plan is ready is still a judgment, and Blueprint reports the two separately.
- Decisions are fixed once the plan is sealed. That hurts work where building is how you learn, such as UI tuning, spikes, or exploratory refactors: each surprise becomes a stop and a new plan instead of a quick detour.
- The planner only probes the code as it is now and never runs the planned change, so it cannot learn what only building reveals.
- Unsettled structure belongs in [Architect](architect.md) first, and an unsettled choice of solution in [Ideate](ideate.md) first. Blueprint asks Ideate itself when it finds no viable direction, but a plan cannot settle a choice you have not framed yet.
- For a small, clear edit, the formality is pure overhead.

**When plan mode is enough.** Stay in plan mode when these hold and none of the reasons under When to use it applies:

- The same agent will carry out the plan in the same session, with you watching.
- The path is obvious, and the risk is in the typing, not the decisions.
- Mistakes surface within minutes.
- The change is local and easy to reverse.
- Building is how you learn.

**Questions to ask before you start.** The choice comes before the work, so ask questions that predict rather than judge in hindsight:

1. "If the executor hits a fork halfway, who decides?" If the agent can decide while you watch, plan mode is enough. If nobody should have to, use Blueprint.
2. "If this is wrong, when will I find out?" Within minutes points to plan mode. In review, in production, or never points to Blueprint.
3. "Will whoever builds this remember why?" The same agent in the same session will. Anyone else, or any later session, needs the decisions written down.

There is also a middle path: start in plan mode, and switch to Blueprint when the plan grows "I'll check whether…" clauses, touches consumers you had not counted, or reaches a choice that is yours rather than an engineering detail.

## How to start it

Start it yourself with `/blueprint`, or the agent may start it when your request matches. Say the outcome, the constraints, and what must not change. For example (illustrative):

```text
/blueprint : Plan adding retry with backoff to the payment client; the public API must not change.
```

## What happens

1. Blueprint asks only questions whose answers change the correct solution, such as the outcome, compatibility, tradeoffs, or scope. It decides files, seams, and tests itself. When the work is a child of a parent or epic issue, it copies the parent's constraints for its children word for word into its request and gives the challenger the parent's text, so the plan is checked against them.
2. It reads the repository and probes its current state. It never builds or runs the planned change, not even in a scratch copy. It consults [Reason](reason.md) before committing to an approach and after a failure, such as a failed probe or blocked seal, or a change of direction.
3. When no viable solution is apparent, or the evidence cannot rank materially different directions, it asks [Ideate](ideate.md) for options inside the same run. You make the final choice unless you already chose or delegated it.
4. Before sealing, a separate fresh-context subagent challenges the draft. Just before launching it, Blueprint consults Reason in its own context, without another subagent, against the draft's most load-bearing premise and its verification, to catch defects before the challenger does. The challenger assumes an executor competent at local coding but without design authority built the plan literally and review rejected the result, then writes that review; code transcribed into the plan is one of its findings. A plan that creates, changes, or deletes code that runs or the configuration it reads, edits something under a time or size budget, spreads to other skills or packages, has irreversible or outward-facing effects, or changes the seal runtime gets the full attack from a challenger at least as capable as the planner. Every other plan gets a shorter brief and the cheapest capable model. Blueprint repairs every supported finding. Before this challenge, for every plan, Blueprint decides each input, state, configuration, or environment that could still break a rule the change must never break, and how the plan refuses or tests it; the full attack lists them again from source, independently of the plan, and checks the plan against each. Every plan also needs proof that fails when a guard the code relies on for such a rule is removed, unless another guard already stops every input that could reach it, and any test stand-in a plan's proof relies on must answer as the real thing it replaces would.
5. Like the challenger, it checks every piece of wording the plan delivers, such as skill guidance, and each completion condition against what the request's clauses require, not the plan's own restatement, including wording changed after the challenge. It consults Reason once more, then seals the plan and reports its path. Its report lists each Reason checkpoint as consulted, missed, or pending.

## What you get

A sealed `blueprint.md` next to a frozen copy of your request, `request.md`, in the ignored folder `.first-four-hours/blueprints/<task-slug>/`. The plan states the goal, the relevant current facts with their cited source files, ordered instructions with their target files, verification commands with expected results, and completion conditions. Each condition states one outcome as a concrete example and names the check that shows it. A condition that only you or another named owner can settle is marked `Owner gate:`. Read the plan's Goal summary before you go on. The seal proves only the plan's shape and its binding to the inspected files; nothing has been implemented or verified yet.

## When it stops

- It does not seal while a question only you can answer is open.
- It does not seal with a known gap in what you asked for or in a rule the change must never break unless you accepted that gap, which your request then records.
- If Ideate can only report a research limit for the direction the plan needs, Blueprint reports that limit to you instead of sealing.
- If no separate subagent can run the challenge, it stops without sealing.

A sealed plan never changes. A changed request needs a new plan in a fresh task folder.

## Choosing models

Blueprint is also meant to raise the planning floor: when only an executor-level model is available, it should help that model plan better than it would unaided. Like comparable quality at lower cost, this is an aim, not a measured guarantee.

When plan quality matters most, use your strongest affordable model for planning. The executor can be cheaper because the plan already settles every decision. Blueprint picks the challenger's model from the plan's risk signals, as step 4 of What happens describes.

The repository's tests prove the planning and execution mechanics with deterministic fakes and no live models; they say nothing about model quality or cost. To compare for yourself, run the same request through different planner and executor pairings by hand, each from the same base commit with a fresh task folder, and compare the outcomes and token use. That comparison is optional and outside repository validation.

## Why it's built this way

**The failure it prevents.** An agent that starts editing before the decisions are made settles them halfway through, and every wrong one is paid for in rework. Blueprint settles every decision first, grounded in the real project, so that a fresh, weaker executor can carry out the plan without engineering choices of its own. Strong planning followed by cheaper execution, at quality comparable to a strong model doing everything, is the aim of the design, not a measured guarantee.

**What it refuses, and why.** It never builds or runs the planned change, not even in a scratch copy, and it never writes the implementation or its tests into the plan. Code the planner never ran would be untested code the executor copies. Decision-complete is not code-complete: prose by default, pseudocode only where prose cannot settle the control flow, and exact text only for textual data whose bytes are the decision, such as wording, configuration, or test data. The seal refuses exact text on a code or test file unless it is an anchored edit of at most two lines. It never asks you to choose a file, a seam, or a test, because those are its job. It does not seal until a separate fresh-context challenger has read the draft the way a faithful executor with no design authority would follow it.

**Floor and ceiling.** A weaker planner is pushed to ground every claim in the code, to account for each input, exit path, and consumer its change affects, and to write verification that would catch a wrong result, which takes it past what it would plan unaided. A stronger planner chooses any mechanism the evidence supports. "Minimum sufficient" means removing unneeded work, never cutting a decision the executor needs. [Anatomy of a sealed blueprint](../concepts/anatomy-of-a-blueprint.md) shows what this produces.

## Related skills

Blueprint can plan from a [Diagnose](diagnose.md) finding, an [Architect](architect.md) decision, or a [Ticket](ticket.md) scope. Construct carries out the result. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Blueprint's contract](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/blueprint/SKILL.md)

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

**Marching orders and construction drawings.** A plan-mode plan is a platoon's marching orders: take the bridge by dawn, by the river road. When a fallen tree blocks the road, the platoon goes around it without sending for new orders. It can, because the soldiers who heard the briefing are the ones on the road, and they know what the orders are for. Plan mode works the same way. The agent that wrote the plan carries it out in the same session and works around obstacles as it goes, and that is by design.

A blueprint is a house's construction drawings. When the crew finds the lot two metres shorter than the drawings show where the porch goes, they do not shrink the porch themselves. The porch's size may matter for reasons the crew cannot see, such as drainage, the permit, or what the owner asked for, so they stop work and the architect redraws. In return, any crew can build from the drawings, hired months later, without ever meeting the architect, because every decision is on paper. Blueprint plans the same way. Every decision is settled before editing, Blueprint attacks it against the code (a risky plan also gets a fresh-context challenger), and it is sealed with the proof of completion fixed in advance: verification commands with their expected results, and a named check, or a named owner, behind each completion condition. Construct is the crew. When the code disagrees with the plan, it does not adjust the plan; it stops with `plan-contradiction`, and a new `/blueprint` redraws it.

**Questions to ask before you start.** The choice comes before the work, so ask questions that predict rather than judge in hindsight:

1. "If the executor hits a fork halfway, who decides?" If the agent can decide while you watch, plan mode is enough. If nobody should be deciding in the middle of an edit, use Blueprint to settle the fork before editing starts.
2. "If a decision here goes wrong, how soon would it show?" If within minutes, while you watch, plan mode catches it in time. If it would only show in review, in production, or never, that is too late to catch it in the work: use Blueprint, which attacks the decisions before anyone edits.
3. "Will whoever builds this remember why?" The same agent in the same session will. Anyone else, or any later session, needs the decisions written down.

**The same change, planned both ways.** *Illustrative and shortened: FreshCart is a made-up online grocery service, and this is the rate-limit plan that [Anatomy of a sealed blueprint](../concepts/anatomy-of-a-blueprint.md) walks through, not a recorded run.* Someone is scraping FreshCart's public search endpoint, and a cheaper model will build the fix overnight with nobody watching. A plan-mode plan for it could read:

```markdown
1. Add rate-limiting middleware for the search endpoint.
2. Return 429 when a client goes over the limit.
3. Exempt partner API keys.
4. Add tests.
```

For an agent you are watching, that is a good plan. But each line hides a fork the agent would settle in the middle of an edit. The sealed blueprint settles each one before anyone edits:

| Plan-mode line | The fork inside it | The blueprint's decision |
| :--- | :--- | :--- |
| Add rate-limiting middleware | Where in the chain, and which client does each limit count? | Right after `authenticate`, keyed on the API key, or else on the address from the trusted `client_address` helper. Never the forwarded header, which any client can forge. |
| for the search endpoint | `/search/suggest` shares the search handler. Is it limited too? | Yes, stated in the Goal and the completion conditions after the challenger noticed it. |
| Return 429 | What else does the response carry, and does the handler still run? | 429 with Retry-After set to the whole seconds until the next token, and the handler is not called. |
| Exempt partner API keys | How does the code know a partner key? | Any key in `settings.PARTNER_KEYS` skips the limit. |
| Add tests | Which tests would catch a wrong limiter? | Four cases, each naming the wrong implementation it rejects: a limiter that never fires, one bucket shared by every client, a limit keyed on the forgeable header, and an ignored exemption. The new test must fail on today's code before the change. |

With you watching, the agent settling these forks as it goes is fine, because you would see the forwarded header in the diff. Overnight, each fork is a guess nobody reviews until morning. One wrong guess opens the limit to anyone who forges a header, and another limits `/search/suggest` without anyone deciding to.

**Where judgment lives.** In plan mode, judgment happens during execution, hidden in the edits. "Update the callers" is enough of a plan, because the agent finds the callers and decides each one as it goes. In Blueprint, judgment happens before execution, and it is attacked rather than only approved by you: Blueprint's own pre-mortem walk, plus a fresh-context challenger for a risky plan, hunts for the input, exit path, or consumer the plan missed.

**What the cost buys.** Plan mode does not avoid the cost of judgment. It defers it and hides it inside the work, where a wrong turn costs the most. Blueprint pays that cost up front and makes it visible, even when the change would have gone fine. It can be cheaper overall when execution is delegated, repeated, or resumed, because the judgment is paid once and the execution can use a cheaper model; like the cheaper-model aim above, that is not a measured result. Stakes alone do not decide it: a low-stakes change handed to a cheaper model still benefits from construction drawings, and a high-stakes change you steer live, diff by diff, may be well served by marching orders.

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

There is also a middle path: start in plan mode, and switch to Blueprint when the plan grows "I'll check whether…" clauses, touches consumers you had not counted, or reaches a choice that is yours rather than an engineering detail.

## How to start it

Start it yourself with `/blueprint`, or the agent may start it when your request matches. Say the outcome, the constraints, and what must not change. For example (illustrative):

```text
/blueprint : Plan the migration that splits our 40-million-row orders table into monthly partitions without downtime. Checkout keeps writing throughout, last quarter's revenue report must match to the cent, and a cheaper model will build this overnight with nobody watching.
```

## What happens

1. Blueprint asks only questions whose answers change the correct solution, such as the outcome, compatibility, tradeoffs, or scope. It decides files, seams, and tests itself. When the work is a child of a parent or epic issue, it copies the parent's constraints for its children word for word into its request and checks the plan against the parent's text, which it also gives the challenger when the plan has one.
2. It reads the repository and probes its current state. It never builds or runs the planned change, not even in a scratch copy. It consults [Reason](reason.md) before committing to an approach, after a failure, such as a failed probe or blocked seal, or a change of direction, and once before sealing.
3. When no viable solution is apparent, or the evidence cannot rank materially different directions, it asks [Ideate](ideate.md) for options inside the same run. You make the final choice unless you already chose or delegated it.
4. Before sealing, Blueprint walks the draft itself, in its own context: it re-derives the plan's key premise from source before reading the plan's own claim, and rehearses Construct's verification. For a plan without a fresh challenger, the walk also runs the full attack. It assumes an executor competent at local coding but without design authority built the plan literally and review rejected the result, then writes that review; code transcribed into the plan is one of its findings. It backs each instruction's failure case with a fresh look at the code. A plan that creates, changes, or deletes a validator, a shared runtime, configuration or fixtures read by anything other than the confined package's own tests, or code beyond one package or directory whose own tests exercise it directly, changes a time or size budget or could use up the room left under one, spreads to other skills or packages, has irreversible or outward-facing effects, or changes the seal runtime gets exactly one fresh-context challenger, which runs the full attack in place of the walk's: its `ffh-challenger` subagent when [Provision](provision.md) set one up, otherwise one at least as capable as the planner. A change that only updates a skill's version number counts as none of these. Neither does code confined to one package or directory and exercised directly by its own tests, nor configuration or fixtures only those tests read. Its other signals still count. Every other plan gets no challenger. Blueprint repairs every supported finding and never rechallenges. A risk signal found later earns that one challenge if none ran; otherwise Blueprint runs the full attack itself. Before sealing, for every plan, Blueprint decides each input, state, configuration, or environment that could still break a rule the change must never break, and how the plan refuses or tests it; the full attack lists them again from source, independently of the plan, and checks the plan against each. Every plan also needs proof that fails when a guard the code relies on for such a rule is removed, unless another guard already stops every input that could reach it, and any test stand-in a plan's proof relies on must answer as the real thing it replaces would.
5. It checks every piece of wording the plan delivers, such as skill guidance, and each completion condition against what the request's clauses require, not the plan's own restatement, including wording changed after any challenge. It consults Reason once more, then seals the plan and reports its path. Its report lists each Reason checkpoint as consulted, missed, or pending.

## What you get

A sealed `blueprint.md` next to a frozen copy of your request, `request.md`, in the ignored folder `.first-four-hours/blueprints/<task-slug>/`. The plan states the goal, the relevant current facts with their cited source files, ordered instructions with their target files, verification commands with expected results, and completion conditions. Each condition states one outcome as a concrete example and names the check that shows it. A condition that only you or another named owner can settle is marked `Owner gate:`. Read the plan's Goal summary before you go on. The seal proves only the plan's shape and its binding to the inspected files; nothing has been implemented or verified yet. The report ends with a prompt for [Construct](construct.md); run it in a fresh session or subagent, since the plan carries every decision. As a subagent, the agent uses its `ffh-constructor` subagent when [Provision](provision.md) set one up, otherwise a generic one as before, and rechecks the run's outcome in your repository before reporting it.

## When it stops

- It does not seal while a question only you can answer is open.
- It does not seal with a known gap in what you asked for or in a rule the change must never break unless you accepted that gap, which your request then records.
- If Ideate can only report a research limit for the direction the plan needs, Blueprint reports that limit to you instead of sealing.
- If a risky plan's challenge cannot run because no separate subagent can launch, it stops without sealing.
- If repairs after the challenge would replace the plan's basis or architecture, or the one challenge returns no review, it stops without sealing and names the failing premise, with a question for you only when that premise is yours to settle.

A sealed plan never changes. A changed request needs a new plan in a fresh task folder. That new plan can ask which files the earlier plan relied on are unchanged since it was sealed, and reuse what it read from those files instead of reading them again.

## Choosing models

Blueprint is also meant to raise the planning floor: when only an executor-level model is available, it should help that model plan better than it would unaided. Like comparable quality at lower cost, this is an aim, not a measured guarantee.

When plan quality matters most, use your strongest affordable model for planning. The executor can be cheaper because the plan already settles every decision: give that model to the `ffh-constructor` subagent in [Provision](provision.md). Blueprint runs the challenger only for risky plans, on the model you gave its `ffh-challenger` subagent in [Provision](provision.md), otherwise on one at least as capable as the planner, as step 4 of What happens describes.

The repository's tests prove the planning and execution mechanics with deterministic fakes and no live models; they say nothing about model quality or cost. To compare for yourself, run the same request through different planner and executor pairings by hand, each from the same base commit with a fresh task folder, and compare the outcomes and token use. That comparison is optional and outside repository validation.

## Why it's built this way

**The failure it prevents.** "Update the callers" sounds like a plan. It is really a dozen decisions, made one at a time inside edits nobody reads until review. Plan mode writes marching orders, and the same agent works around obstacles as it goes; Blueprint draws construction drawings meant to let someone else, later, build without improvising. [Blueprint or plan mode](#blueprint-or-plan-mode) says when each is right. An agent that starts editing before the decisions are made settles them halfway through, and every wrong one is paid for in rework. Blueprint settles every decision first, grounded in the real project, so that a fresh, weaker executor can carry out the plan without engineering choices of its own. Strong planning followed by cheaper execution, at quality comparable to a strong model doing everything, is the aim of the design, not a measured guarantee.

**What it refuses, and why.** It never builds or runs the planned change, not even in a scratch copy, and it never writes the implementation or its tests into the plan. Code the planner never ran would be untested code the executor copies. Decision-complete is not code-complete: prose by default, pseudocode only where prose cannot settle the control flow, and exact text only for textual data whose bytes are the decision, such as wording, configuration, or test data. The seal refuses exact text on a code or test file unless it is an anchored edit of at most two lines. It also refuses a completion condition that names no proof the plan authors, and a command that names a file before the step that creates it. It never asks you to choose a file, a seam, or a test, because those are its job. It does not seal until the draft has been read the way a faithful executor with no design authority would follow it: by Blueprint itself and, for a risky plan, also by a separate fresh-context challenger.

**Floor and ceiling.** A weaker planner is pushed to ground every claim in the code, to account for each input, exit path, and consumer its change affects, and to write verification that would catch a wrong result, which takes it past what it would plan unaided. A stronger planner chooses any mechanism the evidence supports. "Minimum sufficient" means removing unneeded work, never cutting a decision the executor needs. [Anatomy of a sealed blueprint](../concepts/anatomy-of-a-blueprint.md) shows what this produces.

## Related skills

Blueprint can plan from a [Diagnose](diagnose.md) finding, an [Architect](architect.md) decision, a [Ticket](ticket.md) scope, or the findings of a sealed [Assess](assess.md) review, all of them or the ones you name. Construct carries out the result. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Blueprint's contract](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/blueprint/SKILL.md)

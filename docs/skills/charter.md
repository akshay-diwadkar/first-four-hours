# Charter

Charter turns a rough ambition for an app, project, or large idea into one agreed charter: what the project is for, who it serves, what success observably means, what is out of scope, what is settled, and what is still open. Later work is judged against it. It belongs to the Workbench domain.

## When to use it

- You have an ambition for a whole project and want it settled before anyone splits it into tickets or plans changes.
- A project already exists, and you want to state where it is going, with the code as evidence rather than as the answer.

## When to use something else

- For one change to existing work, use [Blueprint](blueprint.md); for a defect, [Diagnose](diagnose.md); for a structural question, [Architect](architect.md).
- With no direction yet, use [Ideate](ideate.md) to compare directions first; Charter can start from the one you choose.
- To split the agreed scope into tickets, use [Ticket](ticket.md). Charter never creates tickets and never starts implementation.

## How to start it

Only you can start Charter: type `/charter`. The agent never starts it on its own. For example (illustrative):

```text
/charter : I want an app that helps small shops track stock without spreadsheets.
```

## What happens

1. Charter proposes a purpose for the project and agrees it with you before anything else: the problem, the users, the outcome, what success observably means, and what is out of scope. For an existing project the purpose says where the project is going, not what the code does today.
2. It proposes the areas the project must settle; you cut and reorder them.
3. It works through one area per round, three to five questions at a time. Each question comes with an interpretation, what each answer would change, and a recommendation; questions only you can answer, such as values or risk appetite, come with their tradeoffs.
4. After every round it records your answers with where each came from, surfaces contradictions instead of overwriting them, and keeps the open questions current, each with who can settle it. A recommendation or your silence is never recorded as agreement.
5. When a question needs research, it can hand the comparison to Ideate; when you need to see something, it can build a throwaway prototype.

## What you get

One file, `.first-four-hours/charters/<slug>/charter.md`, with five sections: Purpose, Agreed, Unsettled, Revisions, and Authority. Authority records whether the charter is `settling` or `ready`; `ready` means nothing open blocks splitting the agreed scope into tickets.

Git ignores the file, so it exists only in the working copy that wrote it: another clone, worktree, collaborator, or cloud session never sees it. When the work will reach any of those, publish it. When you ask, Charter publishes the charter as one GitHub umbrella issue, and only after you confirm the exact title and text. After a verified publication the issue owns the definition and the local file points to it. Charter never creates child issues.

## When it stops

Charter stops in `settling` when the purpose has no observable success yet, or when an open question still blocks splitting the work. The file keeps what was agreed, so a later session resumes it instead of starting over. A failed or unconfirmed publication leaves the local file as the authority.

## Why it's built this way

**The failure it prevents.** A project that starts from a rough idea gets split into tickets and built before anyone has agreed what it is for. Later, no one can say whether a piece of work serves the project, because the destination lives in someone's head or an old conversation. Charter turns the ambition into one agreed, resumable definition that a fresh session can judge work against without reconstructing the conversation.

**What it refuses, and why.** It never records a recommendation, or your silence, as agreement: every agreed item traces to your words, a sourced fact, or your explicit confirmation. It never treats the current code as the destination; for an existing project, the code is evidence for a direction you confirm. It never creates tickets or starts implementation, because publishing a definition and splitting it into work are separate decisions. Only you can start it, because only you can say what the project is for.

**Floor and ceiling.** A weaker agent agrees the purpose before asking anything else, then works one area at a time, and brings an interpretation, the consequence of each answer, and a recommendation to every question, instead of handing you a blank questionnaire. A stronger agent sets the depth by how much each uncertainty matters, and reaches for research, an Ideate comparison, or a throwaway prototype when one would improve a decision. `ready` means the scope can be split into tickets, not that every question is answered.

## Related skills

[Ticket](ticket.md) splits a `ready` charter into tickets: it reuses the published issue as the epic, or takes the local file as its authority. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Charter's contract](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/charter/SKILL.md)

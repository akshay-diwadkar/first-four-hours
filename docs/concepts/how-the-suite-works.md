# How the suite works

## A skill is more than a prompt

A prompt snippet is text you paste into a conversation and hope the agent follows. A skill is a package the agent loads when a task calls for it. Its `SKILL.md` states the outcome and the rules. Its references hold detail the agent reads only when that part of the work comes up. Many skills also ship scripts that check mechanical facts, such as whether a handoff has the required shape and still matches the files it was based on. The scripts check; the agent still does the thinking.

A skill is not a mandatory workflow either. Each skill can be used on its own. A skill that consumes another skill's output says so: for example, `construct` carries out a sealed plan that `blueprint` produced. Some skills start automatically when the agent recognizes a matching task, and others start only when you invoke them by name. The [repository README](../../README.md) lists each skill's invocation mode.

## Use the smallest skill that helps

Start from the task or the problem in front of you, not from how the suite is organized. Ask what is most likely to cost you time later, and reach for the skill that addresses it. A clear, small request may need no skill at all.

For example:

- a defect whose cause you don't know: `diagnose`;
- a change that has to be right the first time: `blueprint` to plan it, then `construct` to carry out the plan;
- a finished change you need to trust before merging: `assess`;
- a decision that is stuck or rests on a doubtful assumption: `reason`.

When the next step is unclear, or the work spans several skills, `router` lays out the route as far as it can be known and stops where the next step depends on a result that does not exist yet.

## Composition is optional

Skills hand work to each other through files, not through your conversation history. A skill that hands work on writes it to its own folder under `.first-four-hours/` at the repository root, which Git ignores, so a later agent or session can pick it up. Deliverables you asked for stay in your project as ordinary files: for example, a document from `scribe`, or the Learning skills' lesson records and practice papers under `.learning/`.

Moving to the next skill is your decision. A handoff makes the next step possible; it never starts it automatically.

## How the suite is organized

Every skill belongs to one of three domains. The domains help you understand the suite; they are not a step in choosing a skill. Choose by task first.

| Domain | What its skills are for |
| :--- | :--- |
| Workbench | Working on a project and its changes: understanding, planning, changing, and verifying a repository. |
| Sensemaking | Getting ready to decide: reasoning, exploring options, writing technical documents, and coordinating which skill comes next. |
| Learning | Building a person's own knowledge and ability in any subject, technical or not. |

Domains are not a pipeline, and they do not decide routing: `router` works with the individual skills. A skill's folder, `skills/<domain>/<skill>/`, records its domain. The [repository README](../../README.md) lists current membership, and repository validation checks that list against those folders.

## Where the truth lives

This documentation explains; it does not define behavior. When a page here disagrees with one of these sources, the source wins and the page needs fixing:

- a skill's `SKILL.md` and its `references/` are the contract its agent follows;
- [the skill design philosophy](../../SKILL_PHILOSOPHY.md) is the doctrine every skill is designed against;
- [the versioning and validation policy](../../REPO_VERSIONING.md) owns versions, tests, and validation;
- in your own project, the current files are the truth, and the skills tell the agent to read them rather than rely on memory.

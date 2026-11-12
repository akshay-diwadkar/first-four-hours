# Assess

Assess reviews one exact proposed change, such as a branch or pull request, against what it was supposed to do. It checks correctness, code quality, and maintainability, and checks security where the change touches trust or permission boundaries, inputs, sensitive data, or risky operations. It belongs to the Workbench domain.

## When to use it

- A change is finished and you need to know whether it does what its issue, specification, or Blueprint asked, without breaking existing behavior.
- You want a re-review after rework, or an acceptance-criteria check before merge.

## When to use something else

- To fix what Assess finds, plan the fix with [Blueprint](blueprint.md) and apply it with [Construct](construct.md). Assess never edits code.
- To investigate a broader defect or risk whose cause is unknown, use [Diagnose](diagnose.md).
- To write the pull request description, use [PR](pr.md).

## How to start it

Start it yourself with `/assess`, or the agent may start it when your request matches. For example (illustrative):

```text
/assess : Assess this branch against issue #42 and the current main branch before merge.
```

## What happens

Assess fixes the exact target, base, and head, reads the authoritative requirements, and works out what the change must do before it reads pull request prose or earlier reviews. Those can suggest concerns but never clear one. It reports every independently material defect it finds, not only the first. It accounts for every clause the change removes and the whole lifecycle of any new state. A re-review after rework covers what changed since the earlier assessment and whether its findings are fixed, and names what it did not re-inspect; ask for a full review when you want the whole change assessed again. A rebase or amend that rewrites the reviewed commit gets a full review. A gap you accepted, as recorded in the plan's frozen request or other authoritative requirements, is not a finding while the change stays within it; a gap the plan accepted without your recorded decision can still be one. If the same agent wrote or planned the change, Assess hands the whole review to a fresh-context subagent. If that subagent returns no checked assessment, Assess stops and asks you to run it in a fresh session. Only when no subagent can start does it review in place and disclose the whole change as self-reviewed. A change that reaches beyond one package or directory and its own tests, not counting version bumps, `docs/` pages, and changelog entries, also gets a second reviewer for behavior and proof: `ffh-reviewer` when [Provision](provision.md) set it up, else a generic subagent. It consults [Reason](reason.md) at its judgment points, skipping only the final check on a tiny change it finds clear.

It can also review a pull request you can read but have not checked out, such as one from a fork or in a repository you have not cloned. Give its URL or `owner/repo#N`. Assess fetches only that pull request's base and head commits, using `gh` and Git, into its own folder under your system's temporary folder, and seals the assessment there; your checkout is never changed. On Linux and macOS that folder is yours alone, readable only by you, and Assess stops as `blocked` if another account holds it. It reviews that code without running it, and asks you before running any of it, such as its tests.

## What you get

A sealed `assessment.md` in its own ignored folder `.first-four-hours/assessments/<slug>/`, which a later assessment never replaces, with one result:

- `clear`: no material defect was found after sufficient examination. When Assess reviews only the rework since an earlier assessment, this covers that rework on top of the assessment, and the report names the head it reviewed;
- `findings`: evidenced material defects, each with its location, the steps that show it going wrong, its consequence, and severity;
- `blocked`: missing or contradictory authority or evidence prevents a trustworthy result.

No result is approval, certification, or permission to merge.

When the result is `findings` and the change is a pull request, Assess offers to post them there as one comment, so its author can see each defect, the steps that show it, and the truth to restore. It first shows you the exact comment, and posts it only after you say yes; declining posts nothing, and the assessment stays the same either way. The comment names the head commit it reviewed and says it is not an approval or a merge decision. If the pull request has moved to a newer head, Assess refuses to post until that head is assessed.

## When it stops

Assess returns `blocked` when it cannot establish the authority or evidence it needs, for example when it cannot confirm that an external source is current.

When it cannot read a pull request you named, it returns `blocked` without an `assessment.md`, naming the pull request, the failing command, and its error. Because a fetched pull request's folder is temporary, a later check or re-review may find it gone; Assess then reviews the whole change again.

When an evidence-backed risk beyond the change could alter the merge decision, Assess stops before sealing and asks you to run `/diagnose` on that risk. You then run Assess again with the resulting `diagnosis.md`; if that diagnosis is missing or contradictory, Assess returns `blocked`.

## Why it's built this way

**The failure it prevents.** Green checks and a confident description are the most persuasive things in a pull request, and the least informative. Reviews that skim the diff, or trust green checks and the pull request's own description, let through changes that do not do what was asked or that quietly break a caller. Assess judges the change against what it was supposed to do (the request, the requirements, the repository's rules, and the behavior on the base branch) with a senior engineer's judgment, and it keeps going after the first defect.

**What it refuses, and why.** It never fixes what it finds, approves, or merges, and it changes nothing on GitHub except a findings comment you confirmed. A reviewer that repairs code is no longer reviewing it, and a fix made straight from a review comment reopens decisions the planner owned. Pull request prose, earlier reviews, and passing tests can raise a concern but never clear one. When the same agent wrote the change, Assess hands the review to a fresh-context subagent, or says plainly that only a self-review examined it.

**Floor and ceiling.** A weaker agent must work out what the change has to do before it reads anyone's claims about it, check every candidate finding against evidence, and disclose what it did not examine. A stronger agent decides how deep to go, judges severity from consequence, and looks at security only where the change touches it. `clear` after a sufficient look is a valid result. The scripts check identity, freshness, and evidence; they never grade the review.

## Related skills

Findings usually lead to a new Blueprint and a fresh Construct run. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Assess's contract](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/assess/SKILL.md)

# PR

`/pr` writes a pull request description for the current branch that tells a reviewer what the diff cannot show, checks it, and opens the pull request, or replaces the description of the branch's open one, only after you confirm the exact text. It belongs to the Workbench domain.

## When to use it

A branch is finished and needs a pull request, or its open pull request's description no longer matches the branch.

## When to use something else

- To review the change itself, use [`/assess`](assess.md).
- `/pr` never merges, approves, or edits the branch's code.

## How to start it

Type `/pr`, or ask in plain words for a pull request or a refreshed description; the agent may also start `/pr` when your request matches. For example (illustrative):

```text
/pr : Open a pull request for this branch against main; it implements issue #42.
```

## What happens

1. `/pr` reads the whole diff against the base and finds the authority for the change: the linked issue or a sealed `/blueprint` plan. It links or quotes that authority instead of restating it. With neither, it says so and takes the intent from you.
2. It runs and records each verification it will claim, so the description cites real commands and exit codes.
3. It drafts the description outside the repository and checks it mechanically for grounding, recorded runs, and diagram shape. Prose quality stays the agent's judgment.
4. It shows you the title and the complete checked text and asks whether to open the pull request, and whether to push the branch first when that is needed. When the branch already has an open pull request, `/pr` instead asks whether to replace that description: it keeps what still holds from the current one, shows you what it drops, and changes the title only if you give a new one.

## What you get

The pull request URL, after your explicit yes, whether `/pr` opened it or updated it. Silence or an earlier approval does not count, and after any edit to the text it checks, shows, and asks again.

## When it stops

If a check fails, `/pr` repairs the draft or records the missing run and checks again. The check refuses a base that is not a local or fetched remote branch, such as a commit SHA or a tag, before asking for your yes. It does not contact GitHub, so a branch deleted there since your last fetch, or a local branch you never pushed, still passes. Without your yes, nothing is pushed, opened, or updated. `/pr` looks the pull request up only in the repository your branch was pushed to, and does not update a closed or merged pull request, one opened from another repository, one whose head is not the commit you pushed, or one whose base differs from the base the description was checked against.

## Why it's built this way

**The failure it prevents.** A reviewer opens the pull request with ten minutes to spare and none of the author's context. Reviewers dislike reviewing pull requests. Many skip the description entirely, and those who read it often still cannot work out from the diff what the change does. `/pr` exists to explain a change in a way that is understandable and that matters to the reviewer: what it does, and what impact it has if it is merged, so the reviewer can piece the change together from the description instead of reverse-engineering the diff.

**What it refuses, and why.** It never invents the intent: it links or quotes the issue or sealed `/blueprint` plan instead of restating it as a second source of truth. It never claims a check it did not run; every verification it cites is recorded with its command and exit code. It never opens or updates a pull request without your explicit yes to the exact text, and it never merges, approves, or edits the code.

**Floor and ceiling.** A weaker agent must read the whole diff, find the authority for the change, record its checks, and pass a mechanical grounding check before showing you anything. A stronger agent decides what the reviewer most needs to know and how to say it; the quality of the prose stays its judgment.

## Related skills

[`/assess`](assess.md) can review the branch before or after the pull request exists. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[`/pr`'s contract](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/pr/SKILL.md)

# PR

PR writes a pull request description for the current branch that tells a reviewer what the diff cannot show, checks it, and opens the pull request only after you confirm the exact text. It belongs to the Workbench domain.

## When to use it

A branch is finished and needs a pull request.

## When to use something else

- To review the change itself, use [Assess](assess.md).
- PR never merges, approves, or edits the branch's code.

## How to start it

Only you can start PR: type `/pr`. The agent never starts it on its own. For example (illustrative):

```text
/pr : Open a pull request for this branch against main; it implements issue #42.
```

## What happens

1. PR reads the whole diff against the base and finds the authority for the change: the linked issue or a sealed Blueprint. It links or quotes that authority instead of restating it. With neither, it says so and takes the intent from you.
2. It runs and records each verification it will claim, so the description cites real commands and exit codes.
3. It drafts the description outside the repository and checks it mechanically for grounding, recorded runs, and diagram shape. Prose quality stays the agent's judgment.
4. It shows you the title and the complete checked text and asks whether to open the pull request, and whether to push the branch first when that is needed.

## What you get

The pull request URL, after your explicit yes. Silence or an earlier approval does not count, and after any edit to the text it checks, shows, and asks again.

## When it stops

If a check fails, PR repairs the draft or records the missing run and checks again. Without your yes, nothing is pushed or opened.

## Related skills

[Assess](assess.md) can review the branch before or after the pull request exists. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[PR's contract](../../skills/workbench/pr/SKILL.md)

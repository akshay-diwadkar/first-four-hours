# Trust a change before you merge it

Review churn comes from reviews that skim the diff, or from fixes made straight from review comments that quietly reopen decisions. Assess checks the exact change against what it was supposed to do and reports every material defect it finds. Fixes go through a new plan instead of a direct edit.

## Use this when

- A change is finished and you need to know it does what its issue, specification, or Blueprint asked, without breaking existing behavior.
- You want a re-review after rework.

## Use something else when

- You need the pull request description: [PR](../skills/pr.md).
- A broader risk has an unknown cause: [Fix the bug without patching the symptom](fix-a-bug.md).
- The change is not written yet: [Plan a change before your agent starts editing](plan-a-change.md).

## Steps

1. Start Assess on the branch, naming the authority (issue, specification, or sealed Blueprint) and the base.
2. Read the result: `clear`, `findings`, or `blocked`. None of them is approval to merge.
3. For `findings`, plan the fixes with a new Blueprint from `assessment.md`, and carry them out with a fresh Construct.
4. Run Assess again on the reworked branch.
5. Open the pull request with PR. It shows you the exact text and opens the pull request only after your yes. Merging stays yours.

## Example

For example (illustrative):

```text
/assess : Assess this branch against issue #<number> and the current main branch before merge.
```

```text
/blueprint : Plan fixes for the findings in .first-four-hours/assessments/<slug>/assessment.md.
```

```text
/pr : Open a pull request for this branch against main; it implements issue #<number>.
```

`#<number>` and `<slug>` are placeholders.

## You are done when

Assess returns `clear` for the final revision of the branch, which means no material defect was found after sufficient examination, and you have decided to merge.

## If it goes wrong

- `blocked`: supply the missing or contradictory authority or evidence it names, then run Assess again ([Assess](../skills/assess.md)).
- Assess stops and asks you to run `/diagnose` on a risk beyond the change: run it, then run Assess again with the resulting `diagnosis.md` ([Assess](../skills/assess.md), [Diagnose](../skills/diagnose.md)).
- A PR check fails: PR repairs the draft and checks again. Nothing is pushed or opened without your yes ([PR](../skills/pr.md)).

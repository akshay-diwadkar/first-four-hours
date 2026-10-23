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

## A worked scenario

*Illustrative: Larder is a made-up project, and this is not a recorded run. Excerpts are shortened.*

A branch adds shareable shopping lists for Larder, from issue #40. The tests pass, and the branch's notes say the feature is complete.

```text
/assess : Assess this branch against issue #40 and the current main branch before merge.
```

Assess reads issue #40 first and works out what the change must do before it reads anyone's claims about it. It returns `findings`:

```markdown
## Result

`findings`

## Findings

### Finding 1

- Severity: P1
- Basis: reasoned
- Defect: the share endpoint loads a list by its number without checking that the caller owns it or holds its share link.
- Consequence: any signed-in customer can read any other customer's list by changing the number in the address.
- Required truth: issue #40 allows a list to be opened only by its owner and by people with its link.

### Finding 2

- Severity: P1
- Basis: reasoned
- Defect: the migration adds the new sharing column with no default, so every existing list reads as empty, and the list page treats that as an error.
- Consequence: customers with saved lists would see an error page after deploy.
- Required truth: existing lists keep working and stay private.
```

Assess kept going after the first finding. The second never shows up in tests, because the test database starts with no lists.

```text
/blueprint : Plan fixes for the findings in .first-four-hours/assessments/shared-lists/assessment.md.
```

A new Blueprint and a fresh Construct fix both findings, and a second Assess returns `clear`: no material defect found after a sufficient look. That is still not permission to merge.

```text
/pr : Open a pull request for this branch against main; it implements issue #40.
```

PR writes for the reviewer who skims and for the one who reads closely but only has the diff. It leads with what changes if this merges, links issue #40 instead of restating it, and claims only checks it actually ran and recorded:

```markdown
## What changes if this merges

Customers can share a shopping list by link. Only the owner and people holding the link can open it; anyone else gets "not found". Existing lists stay private. Closes #40.

## Where to look first

- The share endpoint: the owner-or-link check is the security boundary.
- The migration: the new column defaults to not shared, so existing lists keep working.

## Verification

- Ran: `python -m pytest tests/lists -q`: all tests passed.
```

PR shows you the title and the full text, and opens the pull request only after your yes. Merging stays yours.

## You are done when

Assess returns `clear` for the final revision of the branch, which means no material defect was found after sufficient examination, and you have decided to merge.

## If it goes wrong

- `blocked`: supply the missing or contradictory authority or evidence it names, then run Assess again ([Assess](../skills/assess.md)).
- Assess stops and asks you to run `/diagnose` on a risk beyond the change: run it, then run Assess again with the resulting `diagnosis.md` ([Assess](../skills/assess.md), [Diagnose](../skills/diagnose.md)).
- A PR check fails: PR repairs the draft and checks again. Nothing is pushed or opened without your yes ([PR](../skills/pr.md)).

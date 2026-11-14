# Trust a change before you merge it

The tests are green. The description says complete. The reviewer has twenty minutes before the weekend. Bad merges often happen that way: not through carelessness, but through trust in the wrong signals.

Review churn comes from reviews that skim the diff, or from fixes made straight from review comments that quietly reopen decisions. `/assess` checks the exact change against what it was supposed to do and reports every material defect it finds. Fixes go through a new plan instead of a direct edit.

## Use this when

- A change is finished and you need to know it does what its issue, specification, or `/blueprint` asked, without breaking existing behavior.
- You want a re-review after rework.
- You are about to trust the agent's summary of a change instead of the change.

## Use something else when

- You need the pull request description: [`/pr`](../skills/pr.md).
- A broader risk has an unknown cause: [Fix the bug without patching the symptom](fix-a-bug.md).
- The change is not written yet: [Plan a change before your agent starts editing](plan-a-change.md).

## Steps

1. Start `/assess` on the branch, naming the authority (issue, specification, or sealed `/blueprint` plan) and the base.
2. Read the result: `clear`, `findings`, or `blocked`. None of them is approval to merge.
3. For `findings`, plan the fixes with a new `/blueprint` from `assessment.md`, and carry them out with a fresh `/construct`.
4. Run `/assess` again on the reworked branch. When it reviews the rework and the earlier findings, its report names the head the earlier assessment reviewed; ask for a full review to cover the whole change again.
5. Open the pull request with `/pr`. It shows you the exact text and opens the pull request only after your yes. Merging stays yours.

## A worked scenario

*Illustrative: FreshCart is a made-up online grocery service, and this is not a recorded run. Excerpts are shortened.*

It is Friday afternoon. Checkout engineer Mateo Rojas's branch adds shareable shopping lists for FreshCart, from issue #40. The tests pass, the branch's notes say the feature is complete, and reviewer Yuki Tanaka has it. Approving it would take five minutes, and nobody would ask why.

```text
/assess : Assess this branch against issue #40 and the current main branch before merge.
```

`/assess` reads issue #40 first and works out what the change must do before it reads anyone's claims about it. It returns `findings`:

```markdown
## Result

`findings`

## Findings

### Finding 1

- Severity: P1
- Basis: reasoned
- Defect: the share endpoint loads a list by its number without checking that the caller owns it or holds its share link.
- Scenario:
  - Signed-in customer Amara opens list 41, one of Amara's own shared lists.
  - Amara changes 41 to 42 in the address; list 42 belongs to Lars and was never shared with Amara.
  - The endpoint returns Lars's list. Issue #40 says Amara should be refused.
- Consequence: every customer's private lists are readable by any other signed-in customer.
- Required truth: issue #40 allows a list to be opened only by its owner and by people with its link.

### Finding 2

- Severity: P1
- Basis: reasoned
- Defect: the migration adds the new sharing column with no default.
- Scenario:
  - Before deploy, a customer has a saved list.
  - The migration adds the sharing column, so the list's value in it is empty.
  - The list page treats the empty value as an error, and the customer gets an error page instead of the list.
- Consequence: every customer with a saved list loses access to it after deploy.
- Required truth: existing lists keep working and stay private.
```

`/assess` kept going after the first finding. The second never shows up in tests, because the test database starts with no lists. A five-minute approval would have let any customer read anyone's list, and sent everyone with a saved list to an error page.

```text
/blueprint : Plan fixes for the findings in .first-four-hours/assessments/shared-lists/assessment.md.
```

A new `/blueprint` and a fresh `/construct` fix both findings, and a second `/assess` returns `clear` for the rework on top of the first assessment: no material defect found after a sufficient look. Its report names the head the first assessment reviewed. That is still not permission to merge.

```text
/pr : Open a pull request for this branch against main; it implements issue #40.
```

`/pr` writes for the reviewer who skims and for the one who reads closely but only has the diff. It leads with what changes if this merges, links issue #40 instead of restating it, and claims only checks it actually ran and recorded:

```markdown
## What changes if this merges

Customers can share a shopping list by link. Only the owner and people holding the link can open it; anyone else gets "not found". Existing lists stay private. Closes #40.

## Where to look first

- The share endpoint: the owner-or-link check is the security boundary.
- The migration: the new column defaults to not shared, so existing lists keep working.

## Verification

- Ran: `python -m pytest tests/lists -q`: all tests passed.
```

`/pr` shows you the title and the full text, and opens the pull request only after your yes. Merging stays yours.

## You are done when

`/assess` returns `clear` for the final revision of the branch, which means no material defect was found after sufficient examination (when it reviews only the rework, in that rework on top of the earlier assessment), and you have decided to merge.

## If it goes wrong

- `blocked`: supply the missing or contradictory authority or evidence it names, then run `/assess` again ([`/assess`](../skills/assess.md)).
- `/assess` stops and asks you to run `/diagnose` on a risk beyond the change: run it, then run `/assess` again with the resulting `diagnosis.md` ([`/assess`](../skills/assess.md), [`/diagnose`](../skills/diagnose.md)).
- A `/pr` check fails: `/pr` repairs the draft and checks again. Nothing is pushed or opened without your yes ([`/pr`](../skills/pr.md)).

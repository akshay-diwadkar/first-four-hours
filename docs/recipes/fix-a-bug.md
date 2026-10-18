# Fix the bug without patching the symptom

When the cause is unknown, an agent tends to patch the place where the symptom shows, and the bug comes back somewhere else. Diagnose finds the cause from evidence first, without editing anything. The fix is then planned for one finding.

## Use this when

- Something is wrong and you do not know why: a defect, a bottleneck, or runtime behavior you cannot explain by reading the code.
- You want evidence of what is worth improving instead of generic advice.

## Use something else when

- The cause is known and the fix is clear: [Plan a change before your agent starts editing](plan-a-change.md).
- The problem is where a responsibility lives: [Settle the structure before agents add parallel machinery](settle-structure.md).
- You are reviewing a finished change: [Trust a change before you merge it](review-before-merge.md).

## Steps

1. Start Diagnose yourself and name the symptom. Only you can start it.
2. Read the sealed `diagnosis.md`. Each finding says how well its cause is established. Advisory directions are leads, not a chosen fix.
3. Pick one finding and ask Blueprint to plan its fix, naming the finding. If no viable fix is apparent, or the evidence cannot rank the possible fixes, Blueprint asks [Ideate](../skills/ideate.md) inside its run, and you choose unless you already chose or delegated the choice.
4. Carry out the sealed plan with Construct, as in [Plan a change before your agent starts editing](plan-a-change.md).

## Example

For example (illustrative):

```text
/diagnose : Find out why some customers receive two order-confirmation emails.
```

```text
/blueprint : Plan a fix for finding <finding-id> in .first-four-hours/diagnoses/<slug>/diagnosis.md.
```

`<finding-id>` and `<slug>` are placeholders for the values in your own `diagnosis.md`.

## You are done when

Construct's report shows every instruction applied, the plan's verification passed, and the diff matching the plan; you have settled its owner gates; and the symptom no longer appears when you check it the way you first saw it.

## If it goes wrong

- Diagnose reports missing evidence instead of a finding: supply that evidence or the access it asked for, then run Diagnose again ([Diagnose](../skills/diagnose.md)).
- The symptom returns after the fix: run Diagnose again with the new evidence rather than patching on top ([Diagnose](../skills/diagnose.md)).
- Construct stops: follow [Construct](../skills/construct.md).

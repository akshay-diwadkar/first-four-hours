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

## A worked scenario

*Illustrative: Larder is a made-up project, and this is not a recorded run. Excerpts are shortened.*

Larder's support inbox keeps getting the same complaint: some customers receive two order-confirmation emails. The quick patch would be a duplicate filter in the email sender. You start Diagnose instead.

```text
/diagnose : Find out why some Larder customers receive two order-confirmation emails.
```

Diagnose follows the email back from the sender to its caller: the payment webhook handler. The handler sends the confirmation before it records the provider's event ID. Against a local test app, Diagnose replays one captured webhook twice and gets two emails; it replays it again with that event ID already marked as seen and gets none. Changing the suspected cause moved the effect, so the cause is `demonstrated`, not just reproduced. It touches no production system and changes no code.

```markdown
## Finding webhook-retry-resends-confirmation

- Title: A retried payment webhook sends a second confirmation
- Cause status: demonstrated

### Summary

The webhook handler sends the order confirmation before it stores the provider's event ID, so a retried delivery sends it again.

### Impact

The provider retries webhooks that answer slowly, so duplicates rise with checkout load.

### Cause / Ownership Boundary

The webhook handler owns the duplicate: it acts on an event before marking it seen. The email sender only does what it is told.
```

In its report, Diagnose offers two advisory directions: store the event ID before acting, or filter duplicates in the sender. It notes that the second would hide the cause rather than remove it. Neither is a decision; you pick the finding to fix.

```text
/blueprint : Plan a fix for finding webhook-retry-resends-confirmation in .first-four-hours/diagnoses/duplicate-confirmation-emails/diagnosis.md.
```

Blueprint plans the fix where the finding puts the cause: the handler stores the event ID in the same transaction as the order update, before anything is sent. Its regression test replays the same webhook twice and expects one email. Construct sees that test fail before the change and pass after it. A filter in the sender would have stopped this symptom and let the next one through, such as a duplicate refund notice.

## You are done when

Construct's report shows every instruction applied, the plan's verification passed, and the diff matching the plan; you have settled its owner gates; and the symptom no longer appears when you check it the way you first saw it.

## If it goes wrong

- Diagnose reports missing evidence instead of a finding: supply that evidence or the access it asked for, then run Diagnose again ([Diagnose](../skills/diagnose.md)).
- The symptom returns after the fix: run Diagnose again with the new evidence rather than patching on top ([Diagnose](../skills/diagnose.md)).
- Construct stops: follow [Construct](../skills/construct.md).

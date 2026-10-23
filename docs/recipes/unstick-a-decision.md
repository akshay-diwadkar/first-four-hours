# Get a stuck decision moving again

An agent that cannot decide keeps gathering context, or commits to an approach that rests on an assumption no one checked, and the side quest costs more than the decision. Reason is a short, bounded check: it restores a stuck decision, challenges one load-bearing claim, or asks you the one question only you can answer.

## Use this when

- A decision is stuck because the goal, evidence, cause, or options are unresolved.
- You want a proposal or claim challenged before you rely on it.

## Use something else when

- The options need researching and comparing: [Ideate](../skills/ideate.md).
- The cause of a problem is unknown: [Fix the bug without patching the symptom](fix-a-bug.md).
- The work is mechanical, with nothing left to judge, such as carrying out a sealed plan: it needs no Reason ([Reason](../skills/reason.md)).

## Steps

1. Start Reason with the stuck decision or the claim.
2. It picks the smallest branch that fits: `decide`, `challenge`, or `ask`.
3. Read its one- or two-line result: material objection, missing evidence, needed user input, or no material concern.
4. Answer its question if it asked one. The agent, or you, then chooses the next move. Reason does not choose a replacement or start another skill.

## A worked scenario

*Illustrative: Larder is a made-up project, and this is not a recorded run.*

Larder wants order numbers that cannot be guessed, so the plan is to switch from counting numbers to random IDs. The proposal says the switch is safe, because the API already returns order IDs as strings.

```text
/reason : Challenge the claim that switching Larder's order IDs from counting numbers to random IDs is safe for existing customers.
```

Reason picks `challenge` and attacks that one claim. Its answer is short:

```text
Target: the proposal to switch order IDs to random IDs.
Disposition: material-objection
Load-bearing claim: "order IDs are already strings, so switching is safe."
Challenge: the API returns strings, but receipt emails build order links from the number, so links already in customers' inboxes would stop working.
```

Reason does not propose the fix. Whoever asked decides: keep the old links working with a redirect, or accept that they break. If Reason had found nothing, `no-material-objection` would have been a valid answer, and still not an approval.

When a decision is stuck rather than doubtful, ask about what is blocking it:

```text
/reason : We keep going back and forth between caching search results in the app or at the edge; what is blocking this decision?
```

## You are done when

There is a defensible next move, because the concern was resolved or the missing fact or choice was supplied. "No material concern" is a valid result, but it is not approval.

## If it goes wrong

- Several viable directions remain and nothing ranks them: use [Ideate](../skills/ideate.md).
- The missing evidence needs investigating: use [Diagnose](../skills/diagnose.md).
- The same question keeps coming back: it is likely one only you can answer, so answer it directly ([Reason](../skills/reason.md)).

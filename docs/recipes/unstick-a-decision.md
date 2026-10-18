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

## Example

For example (illustrative):

```text
/reason : Challenge the claim that we can drop the old config format without breaking existing installs.
```

```text
/reason : We keep going back and forth between caching in the client or in the server; what is blocking this decision?
```

## You are done when

There is a defensible next move, because the concern was resolved or the missing fact or choice was supplied. "No material concern" is a valid result, but it is not approval.

## If it goes wrong

- Several viable directions remain and nothing ranks them: use [Ideate](../skills/ideate.md).
- The missing evidence needs investigating: use [Diagnose](../skills/diagnose.md).
- The same question keeps coming back: it is likely one only you can answer, so answer it directly ([Reason](../skills/reason.md)).

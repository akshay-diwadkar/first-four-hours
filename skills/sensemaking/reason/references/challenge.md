# Challenge details

## Choose the context

Run this pass in fresh context, per [Fresh challenge](delegation-protocol.md), when it challenges a non-trivial proposal or result, as [Results](results.md) defines it, that you produced or planned in your current context, and a wrong one would be hard to reverse or would cross a safety, security, permission, or authority boundary, including a completion or readiness claim that clears such an action. Owner context suffices otherwise, when this pass already runs in fresh context, and where the owner skill defines its own fresh challenger, reviewer, or adversarial specialist for this work: that skill's rule decides whether one runs, and Reason adds none. When this pass needs fresh context but no subagent can launch, or host or user policy forbids launching one, run it in owner context, keep its disposition, and state in the reply that the expected fresh challenge did not run.

## Select the claim

Do not reopen goal selection, do routine domain work, or promote style-only criticism.

Find the claim whose failure changes the proposed action, acceptance, or claimed completion: imagine the proposal or result has already failed, name the most plausible cause, and select the claim that cause would break. Prefer proposal, authoritative evidence, material assumptions, consequence, and stop condition over the proposing agent's transcript. Never request or persist chain-of-thought. At a checkpoint on a non-trivial decision, the selected claim is the strongest opposing argument, and the pass still tests blind spots and verifies every other load-bearing assumption before `no-material-objection`.

Use the smallest relevant lens:

- authoritative evidence contradicts the claim;
- an unresolved assumption is treated as fact;
- a materially simpler or more robust authorized approach reaches the same required outcome;
- a plausible counterexample breaks required behavior;
- another cause implies a materially different action;
- selected or surviving cases are read as representing excluded or unobserved ones;
- an affected consumer, boundary, stakeholder, permission, or recovery path is omitted;
- proposed proof can pass while required behavior remains wrong;
- compatibility, migration, permission, or authority is assumed;
- scope no longer matches the authoritative request, including any settled narrowing, or the result is checked against a restated goal instead;
- evidence is stale, completion proves activity rather than outcome, or observed output does not show the claimed outcome.

A challenge is material only when it connects to goal achievement, correctness, consequence, risk, authority, or completion. Prefer disconfirmation over supportive restatement. Raise a better approach only when it is material and supported.

## Resolve or stop

Prefer observation to rereading your own reasoning: before concluding, state what an economical read, search, run, or test must show to check the load-bearing claim, then take it within read-only authority or name it for the owner; output already in hand counts when checked against that statement. A completion claim any available read, search, run, or test could settle cannot receive `no-material-objection` until it is checked, and a disposition resting on no observation says so. When the selected claim rests on rival explanations, selected evidence, an uncertain premise, or an unclear link to the required outcome, apply the one matching [evidence check](decide.md#evidence-checks) whose answer could change the disposition. If the objection remains unresolved, name the smallest credible read, test, comparison, source check, or user-owned decision that distinguishes the outcomes; when none is economical, keep the uncertainty as `insufficient-evidence`.

Stop at one disposition:

- `material-objection`: a supported defect or materially better authorized approach can change the owning decision;
- `insufficient-evidence`: a material possibility remains unresolved by available authority or evidence;
- `no-material-objection`: this bounded pass found no decision-changing defect, without proving correctness.

When one objection suffices, report only the strongest; challenge again only after the target or evidence changes.

## Result

A user-facing result keeps only `Target`, its disposition, `Load-bearing claim`, and only the needed challenge, evidence, consequence, or discriminator. On explicit user invocation, end with one optional next step fitting this outcome: a fenced, self-contained prompt naming any repository, issue, PR, or artifact it needs, or say none is needed. Only a "yes" starts it, via any skill it names, but the user runs a `charter`, `diagnose`, or `ticket` step as its `/<skill>` command.

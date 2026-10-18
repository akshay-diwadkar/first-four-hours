# Decide details

Restore decision readiness, not the whole task. Bound observable working state and start with the most upstream blocker whose resolution could make downstream uncertainty irrelevant.

Separate evidence, inference, assumption, speculation, and unknown. Give uncertainty an evidence path, question, owner, or honest insufficient-evidence result.

An assumption can also restrict the framing. When the framing blocks a defensible move, separate the required outcome from the proposed mechanism and look for an unsupported restriction that materially narrows the approaches, such as a proposed mechanism or existing implementation choice treated as a requirement. Relax or reverse only that restriction, and only to expose a materially different authorized approach; explicit requirements, settled decisions, scope, permissions, and user-owned choices stay binding. Treat the approach as a hypothesis, not a replacement: return it to authoritative evidence and name the observation or objection that would change the owner's decision. Novelty alone justifies nothing, and finding no removable restriction is a valid result.

Classify blockers:

- evidence-owned: observe the cheapest decision-changing evidence;
- agent-owned: decide within current authority;
- user-owned: switch internally to ask;
- irreducible: no economical discriminator exists; follow the [evidence checks](#evidence-checks) rule for it.

For competing causes or actions, seek the cheapest discriminator, using the matching [evidence check](#evidence-checks) when one applies. If all plausible causes imply one action, stop. If options are materially equivalent, prefer the simplest sufficiently reversible authorized convention.

Retry a failed approach only with new evidence; otherwise change approach. Before a costly, high-consequence, or hard-to-reverse commitment, test the cheapest useful falsifier; when independent adversarial challenge is that falsifier, switch internally to challenge.

Exit as soon as one defensible owned move exists.

## Evidence checks

Decide and challenge use only the check whose answer could change the owning action; none is a required sequence. Ground each rival, selection mechanism, premise variation, and condition in the actual outcome, inspected facts, or a genuine unresolved premise; never invent ranges, probabilities, requirements, policy, or authority. Gather evidence only within read-only authority; otherwise name the observation the owner needs. Preserve missing evidence and uncertainty; when no economical discriminator exists, retain the uncertainty or use an already-authorized, sufficiently reversible move.

- **Rival explanations:** when credible explanations fit current evidence but imply different actions, name an observation they predict differently and seek the cheapest one that tells them apart. Evidence that fits both equally well resolves nothing.
- **Selected evidence:** when an observed pattern or absence bears on the decision, ask how cases entered the sample and whether survival, failure, exclusion, filtering, or incomplete capture could produce the same pattern; seek the cheapest evidence that tells those mechanisms apart. An unobserved case is not a negative result, and a missing record informs only as far as the capture process supports. Never invent missing outcomes or infer a cause from the surviving sample alone.
- **Premise sensitivity:** when an action rests on an uncertain premise, check whether supported plausible alternatives change the action or its ability to reach the required outcome. Pursue only uncertainty that changes the move.
- **Outcome connection:** when the proposal's link to the required outcome is unclear, work back from the outcome to the nearest decision-changing necessary condition and check whether the proposal and evidence establish it. Report a missing connection, contradiction, or evidence gap; design no replacement or full backward plan. A met necessary condition does not prove the outcome.

## Result

A user-facing result keeps only `Goal`, `Blocker`, `Established`, `Unresolved`, and `Next move`; the owner takes the next move. On explicit user invocation, end with that move as one optional next step: a fenced, self-contained prompt naming any repository, issue, PR, or artifact it needs. Only a "yes" starts it, via any skill it names, but the user runs a `diagnose`, `pr`, or `ticket` step as its `/<skill>` command.

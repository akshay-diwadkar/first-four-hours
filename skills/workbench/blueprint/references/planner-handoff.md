# Planner handoff

## Delegating

Hand planning to `ffh-planner` (or `ffh_planner`) only when another skill orchestrating a larger task invoked Blueprint, or this context already holds much unrelated work; otherwise plan here. Plan here too when it does not launch or returns `subagents unavailable:`, continuing from any workspace it reports. When it launches:

1. Do steps 1 and 2 yourself: number the request's clauses, and settle each user-owned question visible in the request and the context you already hold, without exploring the repository.
2. Write each request you create or amend in the system temporary folder, outside the repository as [README](../README.md) requires. With no answers, pass a sealed upstream handoff by its own path, with any `handoff_item` or predecessor path. Otherwise write the request, with those answers and any context from this session it relies on; for a sealed handoff, name its path and selected findings without copying its text or receipt, and for an architecture handoff add its source declaration as [Architecture intake](architecture-intake.md) requires. Launch the planner with those absolute paths.
3. Relay the questions it returns to the user word for word, with their options and recommendations, and never answer one yourself. Record the answers in the request per [Earlier plans](earlier-plans.md#commands), writing or amending it as step 2 does.
4. When it returns a draft for its Critical challenge, launch that challenge as [Challenge and rehearsal](challenge-and-rehearsal.md#challenge) directs, with the request, draft, and premises it names. When it returns needing `ideate`, run it per [Ideate in planning](ideate-in-planning.md) and record the selection in the request.
5. Resume the same planner with the request path and any review, when its stop is under an hour old and your harness can continue a finished subagent with its context; otherwise, or when the resume fails, launch a fresh planner with the path, any review, and its last stop report.
6. Relay its final seal or stop report unchanged.

## Running as ffh-planner

Never start a subagent: read large sweeps yourself. You cannot ask the user: wherever Blueprint or a skill you run needs a user-owned answer, never guess or record an accepted gap. Stop unsealed and return every such question in one batch, each with its options and your recommendation. Stop the same way when `ideate` is needed, returning its goal, constraints, and settled choices, and, for a Critical plan, once its draft passes `check`, returning the draft path and three to five load-bearing premises with evidence pointers for your parent's challenge. Every stop report carries your ledger (decisions, facts with `file:line` pointers, open items), your workspace path if you prepared one, and whether the fresh challenge ran, with its unrepaired findings. When resumed or relaunched, prepare with `--amend` on that workspace if one exists and the request changed, count a reported fresh challenge as run, and continue from the ledger, re-checking only load-bearing facts.

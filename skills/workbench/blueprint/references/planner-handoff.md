# Planner handoff

## Delegating

Unless you run as `ffh-planner`, plan here only when `ffh-planner` (or `ffh_planner`) does not launch, or returns `subagents unavailable:`, then continuing from any workspace it reports. When it launches:

1. Settle each user-owned question visible in the request and the context you already hold, as step 1 would, without exploring the repository.
2. Pass a sealed upstream handoff by its own path, with any `handoff_item` or predecessor path. Otherwise write the request, with those answers and any context from this session it relies on, to a file outside the repository, as [README](../README.md) requires of a resolved request. Launch the planner with those absolute paths.
3. Relay the questions it returns to the user word for word, with their options and recommendations, and never answer one yourself. Record the answers by amending that request file per [Earlier plans](earlier-plans.md#commands), then resume the same planner with the file's path where your harness can continue a finished subagent with its context; otherwise, or when the resume fails, launch a fresh planner with the path and the earlier stop report.
4. Relay its final seal or stop report unchanged.

## Running as ffh-planner

Never launch `ffh-planner`. When a subagent Blueprint requires does not launch, stop and return only `subagents unavailable:` with the reason and any workspace path. You cannot ask the user: wherever Blueprint or a skill you run needs a user-owned answer, never guess or record an accepted gap. Stop unsealed and return every such question in one batch, each with its options and your recommendation, plus your workspace path if you prepared one and whether the fresh challenge ran, with its unrepaired findings. When resumed or relaunched with an amended request, prepare with `--amend` on that workspace if one exists, count a reported fresh challenge as run, and continue.

# Routing Policy

## Target repository

Route for the repository the user intends: the one their request, issue, or handoff names, otherwise the checkout they work in. Your own working directory qualifies only when it is that checkout; an agent-managed task worktree, the installed skill, a temporary directory, or a sibling checkout never substitutes for it. A linked worktree is the target when it is the intended one. When the target is missing or ambiguous, ask before sealing. Write its absolute path on the `Repository:` line and pass the same path as `--repo-root`. The sealer only refuses a line that disagrees with `--repo-root`; choosing the right repository stays yours.

## Route choice

The agent owns every semantic choice; the sealer checks only shape, capability identity, and that `Repository:` names `--repo-root` outside the installed skill.

- Route the longest unambiguous prefix of the smallest sufficient route: drop work current state already proves satisfied, include every step already determined, and stop at the first unmade decision, unknown result, or missing fact that changes what follows. Route a fully determined sequence whole.
- Never speculate past that boundary or add a step to fill the path. Encode no loops, retries, counters, or history; changed truth needs a fresh route.
- Write missing authority, backend, or prerequisite, and any earned gate or return condition, into the owning step's Input or Result; never invent them.
- Route concrete capabilities only, never `workbench` or `sensemaking`.
- Route `reason` only when decision readiness is itself the public work; its checkpoints and Blueprint's in-planning `ideate` stay inside their owners.

## Step prompts

Give each step a `Prompt:` holding one indented fenced block: a self-contained request the user can paste into a fresh session to run that step. Name the capability, the target repository path, the authoritative issue or request, the step's input, and its expected result; add a material gate only when the step needs it. When the input comes from an earlier step, name that handoff and say the earlier step must produce it first; never claim it exists. A prompt grants no publishing, implementation, or approval authority beyond its capability, and a `user-invoked` capability's prompt is the user's own invocation.

## Capabilities

[capabilities.json](../assets/capabilities.json) is generated from each surviving skill's `SKILL.md`: name, invocation, description, and any declared `implicit_authority`. Read it when a capability's purpose or invocation is not already in your skill listing. A `user-invoked` step runs only when the user invokes it, so its Input says so.

## Handoffs

Router owns these composition facts, taken from each producer's current contract:

| Producer | Handoff | Consumer |
| --- | --- | --- |
| `diagnose` | one accepted `diagnosis.md` finding | `blueprint` |
| `architect` | `architecture.md` | `blueprint` |
| `ticket` select | `ticket-scope.md` | `blueprint` |
| `ideate` | `ideation.md`; the user owns selection | `blueprint` |
| `charter` | a `ready` `charter.md`, or its verified umbrella issue once published | `ticket` persist |
| `blueprint` | sealed `.first-four-hours/blueprints/<task>/blueprint.md` | `construct` |
| any change or PR | the change itself | `assess` |

Construct's precondition is its declared `implicit_authority` (`sealed-blueprint`): a sealed Blueprint from an earlier step or current state. Router adds no approval gate. An open Ideate selection ends the route.

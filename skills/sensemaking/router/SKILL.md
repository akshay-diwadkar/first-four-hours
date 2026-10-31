---
name: router
description: Author the smallest sufficient route of suite capabilities into ignored `route.md`. Use when the next capability is unclear, work spans several capabilities, or current state may already satisfy part of the request; skip it when one capability obviously applies.
user-invocable: false
metadata:
  version: "1.0.1"
---

# Router

## Purpose

Author one bounded route of public capabilities from the current target and authoritative state, seal it as `.first-four-hours/routes/<slug>/route.md`, and return control. Never execute a routed capability, plan, edit source, publish, commit, push, or create a PR; write only that route and its local Git exclude rule.

## Author

Read [Routing Policy](references/routing-policy.md); it selects the target repository and shapes step prompts. Draft the route outside that repository:

````markdown
# Route: <target>

Repository: <absolute path of the target repository>

<only the current state needed to read the steps>

## Steps

1. `<capability>`
   - Why: <why it is needed now>
   - Input: <authoritative input or current-state dependency>
   - Result: <expected observable result>
   - Prompt:
     ```text
     <copyable request that runs this step>
     ```
````

When current state already satisfies the target, replace the numbered steps with one `None: <established postcondition>` line.

## Seal

```bash
python <skill-root>/scripts/cli.py --repo-root <Repository path> \
  --input draft=<draft.md> --input slug=<route-slug> --format json run
```

Repair each reported defect in the draft and rerun; on a repository mismatch, pass the intended repository rather than editing the line to where you run. Complete when the result names the sealed `route.md` under that Repository; return that path and end with step 1's sealed Prompt as the one optional next step, or none for a `None:` route. Only the user's later "yes" starts it, via its capability and gates, and the user runs a `user-invoked` step's Prompt themselves. Exhausting the route returns control; it does not by itself complete the target.

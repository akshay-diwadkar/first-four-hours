# Project orientation

- [Atlas](../../skills/workbench/atlas/SKILL.md): start navigation, initial mapping, structural validation, pointer upkeep, or root guidance installation.
- [Information architecture](../../skills/workbench/atlas/references/information-architecture.md): resolve Map, Landmark, Satellite, parentage, and link responsibilities before changing wiki structure.
- [Authoring and rebalancing](../../skills/workbench/atlas/references/authoring-and-rebalancing.md): decide page boundaries and completion (a representative-task walkthrough, then `run` and `setup-guidance`) for a new or reorganized wiki, including which guidance diagnostics the agent may repair.
- [Freshness and maintenance](../../skills/workbench/atlas/references/freshness-and-maintenance.md): load for a deliberate drift audit, beyond updating pointers affected by the current change.
- [Guidance installer's `guidance_lines` and `_owned_block`](../../skills/workbench/atlas/scripts/repository_guidance.py): trace how the managed root block's text comes from `MAP.md` (or the pointer above the size cap), and how the block is located, spaced, removed, and checked for drift across LF and CRLF checkouts.

Navigation stays optional: missing Atlas state never blocks work. Authoring or rebalancing is complete only after a representative-task walkthrough and then successful `run` and `setup-guidance`; an edit to `MAP.md` also needs `setup-guidance`, which `run` enforces as `map.guidance_stale`. Freshness is a separate deliberate audit, so a usable map does not imply a current baseline. Editing Atlas guidance also couples to budgets, pinned clauses, and versions; see [contribution and validation](../maintenance/contribution.md).

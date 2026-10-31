# Project orientation

- [Atlas](../../skills/workbench/atlas/SKILL.md): start navigation, initial mapping, structural validation, pointer upkeep, or root guidance installation.
- [Information architecture](../../skills/workbench/atlas/references/information-architecture.md): resolve Map, Landmark, Satellite, parentage, and link responsibilities before changing wiki structure.
- [Authoring and rebalancing](../../skills/workbench/atlas/references/authoring-and-rebalancing.md): decide page boundaries and completion (a representative-task walkthrough, then `setup-guidance` and `run`) for a new or reorganized wiki, including which guidance diagnostics the agent may repair.
- [Freshness and maintenance](../../skills/workbench/atlas/references/freshness-and-maintenance.md): load for a deliberate drift audit, beyond updating pointers affected by the current change.
- [Guidance installer's `map_lines` and `_owned_block`](../../skills/workbench/atlas/scripts/repository_guidance.py): trace how the Map block is derived from the top-level Landmarks, and how it is located, spaced, removed, and checked for drift across LF and CRLF checkouts.

Navigation stays optional: missing Atlas state never blocks work. Authoring or rebalancing is complete only after a representative-task walkthrough and then successful `setup-guidance` and `run`; an edit to a top-level Landmark's title or opening paragraph also needs `setup-guidance`, which `run` enforces as `map.map_stale`. Freshness is a separate deliberate audit, so a usable map does not imply a current baseline. Editing Atlas guidance also couples to budgets, pinned clauses, and versions; see [contribution and validation](../maintenance/contribution.md).

# Canon file

`canon.md` is the whole canon, and `check` rejects one missing any part below. Headings match exactly, each required heading appears once, sections may come in any order, and other sections may be added. `check` ignores everything inside fenced code blocks.

A **rule** is a top-level `- ` bullet, with any indented continuation lines, that states the rule and then gives `Reason:` and why it holds, so a later change can weigh what it gives up.

## Required sections

- `## Character`, with `### Thesis` (prose stating the direction), `### Personality` (one bullet per adjective), and `### Voice` (rules for copy and tone).
- `## Media`, with `### Website`, `### App`, `### Document`, and `### Slide deck`: rules translating the character into each medium. For a medium the product does not use, say so as its rule.
- `## System`, with `### Type`, `### Colour`, `### Spacing`, `### Components`, `### Motion`, and `### Imagery`: the concrete system as rules; imagery rules state style only.
- `## Viewing contexts`: one rule per supported aspect ratio, viewport, device, print, or projection context, saying how composition holds there.
- `## States`, with `### Empty`, `### Error`, `### Loading`, `### Dense data`, `### Long tables`, `### Charts`, and `### Footnotes`: rules for how the character carries into each.
- `## Banned`: rules naming what this product never uses, separate from the generic slop check.
- `## Samples`: one bullet per approved sample render, holding one Markdown link whose target is a relative path to a file inside the canon's folder. The written canon is the authority; samples illustrate it.
- `## Governs`: one bullet per repository-relative path or glob in backticks, using `/` between segments, where `*` matches within one segment and `**` matches any number of segments, as in `` `site/**` ``. Outside a repository the list is recorded but unused.
- `## Change log`: one bullet per change the user approved, oldest first, as `- YYYY-MM-DD: what changed Reason: why`.

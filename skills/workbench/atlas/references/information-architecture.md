# Information architecture

## Project-file authority

Underlying project files are truth. Wiki pages preserve durable orientation only. Filesystem paths are the single source of truth for wiki role, identity, and structural parentage:

```text
MAP.md                              Map
.map/<cluster>/LANDMARK.md          Landmark
.map/<cluster>/<concept>.md         Satellite
.map/<cluster>/<sub>/LANDMARK.md    nested Landmark
.map/<cluster>/<sub>/<concept>.md   nested Satellite
```

Do not add front matter, authored role/page/section IDs, a registry, or another hierarchy representation. Paths alone identify roles and pages.

## Map

`MAP.md` is the unique project-folder-scale router and stays small enough to read in full. After its title, it contains only project-file-authority/non-exhaustive-scope guidance plus every top-level Landmark link with one concise cue. A cue says when and why to follow the link and, where a plausible misread exists, what the target is not for (for example, generated, historical, or never consulted at runtime). Make neighboring cues distinguishable by the task or symptom that should choose each, not just a shared topic; no alias list or fixed wording is needed. Never claim exhaustive coverage. Do not add other prose, sections, indexes, Satellite/project-file links, cached file facts, file lists, or symbols.

## Landmark

Every `.map/**/LANDMARK.md` is a navigation-only cluster index. Include a compact cluster summary plus every immediate child Landmark and Satellite with a concise cue, written as for the Map. Add an occasional wiki cross-link only when it materially improves navigation.

Do not link directly to project files or cache file-specific implementation facts. When cluster-level project-file orientation pays rent, put it in a cohesive Satellite such as `overview.md` and route to that page.

## Satellite

Every other `.map/**/*.md` is a Satellite: focused pointers to productive project-file entrypoints, each with a brief what/why cue, plus only durable cross-file conclusions that are costly to rediscover, such as one lifecycle, boundary, flow, or convention. When files must change together and that coupling is costly to rediscover, name them; when the repository already records the coupling, point to that record instead of copying it. Prune source narration and keep cues accurate: a wrong cue misleads more than a missing one.

Link to productive project-file starting points and explain why each matters. Write a Markdown href relative to the Satellite page; it must resolve to a literal path of a regular file inside the project folder, whose project-relative form is the file identity; `run` rejects directory links. Do not use absolute paths, external URIs, or traversal that escapes the project folder. Prefer stable file links; add symbol hints in prose when helpful. Avoid permanent line anchors, generated trees, file/symbol/caller inventories, copied one-file facts, and catch-all subsystem manuals.

## Parentage and links

- `MAP.md` indexes every top-level Landmark.
- Each Landmark indexes every immediate child Landmark and Satellite.
- A Satellite's parent is the Landmark in its containing directory.
- A nested Landmark's parent is its nearest ancestor Landmark; a top-level Landmark's parent is `MAP.md`.
- Cross-links never change parentage or imply project-file dependency.
- Give shared meaning one home page; other pages cross-link to it rather than restating it.
- Derive parentage; do not author backlinks.

Nested Landmarks are valid when another navigation level prevents unrelated Satellite reads. There is no arbitrary maximum depth. A layer that does not improve progressive disclosure is sediment.

## Authority boundary

The agent owns project-file exploration, conceptual boundaries, authored meaning, task navigation, cross-link choices, and semantic promotion/collapse decisions. The read-only validator verifies path roles, structural indexes, reachability, exact-case project-contained links, and safe project-file bindings. It reports raw size, depth, child, and link counts for review but must not select task context, author meaning, infer ownership, score hierarchy quality, or decide promotion and collapse.

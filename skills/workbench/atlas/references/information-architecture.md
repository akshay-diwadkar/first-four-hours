# Information architecture

## Project-file authority

Underlying project files are truth. Wiki pages preserve durable orientation only. Filesystem paths are the single source of truth for wiki role, identity, and structural parentage:

```text
root AGENTS.md and CLAUDE.md block  Map
.map/<cluster>/LANDMARK.md          Landmark
.map/<cluster>/<concept>.md         Satellite
.map/<cluster>/<sub>/LANDMARK.md    nested Landmark
.map/<cluster>/<sub>/<concept>.md   nested Satellite
```

Do not add front matter, authored role/page/section IDs, a registry, or another hierarchy representation. Paths alone identify roles and pages.

## Map

The Map, the unique project-folder-scale router, is the managed `<!-- ATLAS -->` block in root `AGENTS.md` and `CLAUDE.md`. `setup-guidance` derives it, so never hand-edit it: a fixed project-file-authority/non-exhaustive-scope line, then one link per top-level Landmark in cluster-path order, whose text is the Landmark's `# Title` and whose cue is its opening paragraph. Write that paragraph as plain text, with links, HTML, and URLs only inside code spans. A cue says when and why to follow the link and, where a plausible misread exists, what the target is not for (for example, generated, historical, or never consulted at runtime). Make neighboring cues distinguishable by the task or symptom that should choose each, not just a shared topic; no alias list or fixed wording is needed. Never claim exhaustive coverage. `run` reports a missing, unreadable, or stale block; spacing around it and line-ending style do not count.

## Landmark

Every `.map/**/LANDMARK.md` is a navigation-only cluster index. Open with its `# Title` and a compact cluster summary paragraph, which for a top-level Landmark is its Map cue, then every immediate child Landmark and Satellite with a concise cue, written as for the Map. Add an occasional wiki cross-link only when it materially improves navigation.

Do not link directly to project files or cache file-specific implementation facts. When cluster-level project-file orientation pays rent, put it in a cohesive Satellite such as `overview.md` and route to that page.

## Satellite

Every other `.map/**/*.md` is a Satellite: the smallest sufficient read path into one coherent question, not a file list. Mark its start target, the project file a fresh agent opens first, and name the symbol or section where reading starts when that is not obvious. Cue every other link by the task, symptom, or decision that should choose it, as for the Map. Where knowing when enough has been read is otherwise a guess, state a stop point scoped to a kind of task, such as "enough for a cue edit; a validator change also needs the runner". A stop point is a hint: current project files still decide what the task needs. When the start target already routes to its own references, cue those links by task rather than re-describing that routing.

Add only durable cross-file conclusions that are costly to rediscover, such as one lifecycle, boundary, flow, or convention. When files must change together and that coupling is costly to rediscover, name them; when the repository already records the coupling, point to that record instead of copying it. When a generated, synchronized, vendored, or legacy copy could be mistaken for the source, name the authoritative file and how the copy is produced. Say what the page does not own when a plausible misread exists. Location hints are always welcome, but state a symbol's role or behavior only when the linked file shows it on first read, so the reader confirms it there. Prune source narration and keep cues and stop points accurate: a wrong cue misleads more than a missing one, and a stale stop point ends reading early. A page that leaves its first read or stop point to guess is incomplete.

Link to productive project-file starting points and explain why each matters. Write a Markdown href relative to the Satellite page; it must resolve to a literal path of a regular file inside the project folder, whose project-relative form is the file identity; `run` rejects directory links. Do not use absolute paths, external URIs, or traversal that escapes the project folder. Prefer stable file links. Give a target over 20,000 bytes an entry point: a GitHub-style `#heading` for Markdown, a backticked start symbol in a code link's text or cue, or a cue saying why the whole file is needed; `run` checks the heading and the symbol as a whole word. Avoid line anchors, generated trees, file/symbol/caller inventories, copied one-file facts, and catch-all subsystem manuals.

## Parentage and links

- The Map indexes every top-level Landmark.
- Each Landmark indexes every immediate child Landmark and Satellite.
- A Satellite's parent is the Landmark in its containing directory.
- A nested Landmark's parent is its nearest ancestor Landmark; a top-level Landmark's parent is the Map.
- Cross-links never change parentage or imply project-file dependency.
- Give shared meaning one home page; other pages cross-link to it rather than restating it.
- Derive parentage; do not author backlinks.

Nested Landmarks are valid when another navigation level prevents unrelated Satellite reads. There is no arbitrary maximum depth. A layer that does not improve progressive disclosure is sediment.

## Authority boundary

The agent owns project-file exploration, conceptual boundaries, authored meaning, task navigation, cross-link choices, and semantic promotion/collapse decisions. The read-only validator verifies path roles, structural indexes, reachability, exact-case project-contained links, and safe project-file bindings. It reports raw size, depth, child, and link counts for review but must not select task context, author meaning, infer ownership, score hierarchy quality, or decide promotion and collapse.

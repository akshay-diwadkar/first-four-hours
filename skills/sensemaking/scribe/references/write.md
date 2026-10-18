# Write

1. Identify the audience, the reader's job, risk, profile, and authoritative local sources. Complete when every technical claim has a source or an unresolved-gap label.
2. Decide what the reader's job needs. Include information only when its absence would make that job unsafe, ambiguous, or unusable, such as a prerequisite, expected result, verification, stop or recovery, impact, timing, required action, escalation, searchable reference detail, or navigation. These are examples, not a checklist or required headings; choose the structure the job needs. A concise error message stays concise; a risky procedure earns its verification, stop, and recovery. For each material procedure, the reader must be able to find its prerequisite, action, expected outcome, and any needed stop or recovery.
3. Write `document-bundle.json` from `templates/document-bundle.json` at the path `prepare` returned, choosing `profile` per [Document Bundle](document-bundle.md). Bind each source hash, the glossary, and only the material facts that [Source Grounding](source-grounding.md) names.
4. Draft `document.md`. Put conditions before actions and warnings before hazards; preserve bound literals exactly.
5. Read each material instruction as a faithful reader: could two readers follow it exactly and still take materially different actions or reach materially different outcomes? Resolve that ambiguity from the supplied sources when they settle the intent; otherwise label the exact missing information as an unresolved gap. Never run a hazardous command to create proof, and never rewrite valid prose only to change its style.
6. Run `write`. Repair `document.md` or the bundle for every diagnostic and rerun until it returns `status: complete`.

Do not report completion while a source gap or diagnostic remains.

# Document Bundle Contract

Keep the template's `contract_version`. `write` and `audit` validate the bundle with `schemas/document-bundle.schema.json` and never modify it.

The bundle is the deterministic bridge between sources and the document. It lives only at `.first-four-hours/document-bundles/<slug>/document-bundle.json`, which `prepare` creates and Git ignores. It is support state, never evidence or a deliverable; delete it when no further write or audit needs it.

- `profile` and `glossary` drive language validation. Use `strict` for hazardous procedures, commands, warnings, notices, and recovery; otherwise use `standard`. The bundle holds the only glossary copy.
- `sources` bind repository-relative source bytes with SHA-256. A source inside `.first-four-hours/document-bundles/` is rejected.
- `required_facts` bind exact canonical claims to source identifiers.
- `integrity_literals` preserve exact commands, paths, and values.
- Every `source_ids` entry in `required_facts` and `integrity_literals` must name a declared source; an undeclared one blocks `write` and `audit`.
- `procedures` define marker order.
- `warnings` bind warning text to the hazardous action that must follow it.
- `recovery_steps`, `prerequisites`, and `branches` check that declared operational obligations appear. Declare only what the reader's job needs.
- Optional `section` values restrict a check to an exact Markdown heading.

Use lowercase hexadecimal hashes without the `sha256:` prefix for source records.

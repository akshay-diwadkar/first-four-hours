# Document Bundle Contract

Keep the template's `contract_version`. `write` and `audit` validate the bundle with `schemas/document-bundle.schema.json` and never modify it.

The bundle is the deterministic bridge between sources and documents. Name it `document-bundle.json` and keep it in a temporary directory outside the repository; both commands refuse it inside the repository. It is support state, never evidence or a deliverable; delete it and the evidence captured beside it when no further write or audit needs them.

- `glossary` drives language validation for every document. The bundle holds the only glossary copy.
- `sources` bind source bytes with SHA-256 for every document: a repository file by its repository-relative path, or evidence captured beside the bundle by its absolute path. A source inside `.first-four-hours/scribes/` is rejected.
- `documents` lists each document. Its `path` is absolute or repository-relative, never inside `.first-four-hours/scribes/`. Its `profile` drives its language validation: use `strict` for hazardous procedures, commands, warnings, notices, and recovery; otherwise use `standard`. Only `.md`, `.markdown`, and `.txt` documents get language validation and `section` values; another file, such as source code holding error messages, gets only the checks below. Its other fields check that document only:
  - `required_facts` bind exact canonical claims to source identifiers.
  - `integrity_literals` preserve exact commands, paths, and values.
  - Every `source_ids` entry in `required_facts` and `integrity_literals` must name a declared source; an undeclared one blocks `write` and `audit`.
  - `procedures` define marker order.
  - `warnings` bind warning text to the hazardous action that must follow it.
  - `recovery_steps`, `prerequisites`, and `branches` check that declared operational obligations appear: each recovery `step` after its `trigger`, and a prerequisite with a `procedure` before that procedure's first marker. Declare only what the reader's job needs.
  - An order check (procedures, warnings, recovery steps, and prerequisites with a `procedure`) needs each of its markers to occur once in its scope; scope it to the section that holds the steps, so an overview cannot decide it.
  - Optional `section` values restrict a check to an exact Markdown heading and its subsections; that heading must occur once.
  - Every check except `integrity_literals` ignores backticks, emphasis markers, and line wrapping; literals match exactly.
  - A gap marker inside fenced or inline code is an example, not a gap.
  - `reader_findings` hold audit-only reader judgment, each with `location`, `issue`, and `consequence`; `write` ignores them.

Use lowercase hexadecimal hashes without the `sha256:` prefix for source records.

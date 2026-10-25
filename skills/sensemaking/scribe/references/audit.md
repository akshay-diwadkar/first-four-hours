# Audit

Audit reports what it finds and never fixes it. It does not edit any document, even when remediation is authorized; remediation is a separate `write` with document-revision authority.

1. Write a bundle that lists every document to audit and binds the sources the audit checks per [Source Grounding](source-grounding.md), choosing each `profile` per [Document Bundle](document-bundle.md), or reuse the documents' existing bundle.
2. Read each document as its intended reader. Ask the reader-job question of [Write](write.md) step 2 and the two-reader question of its step 5. Record each material omission or ambiguity in that document's `reader_findings`, with its location and its consequence for that reader. Do not resolve it, add gap labels to the document, or edit the document or sources.
3. Run `audit`. It reads the documents, bundle, and bound sources, changes none of them, and writes `.first-four-hours/scribes/<slug>/scribe-audit.md`, replacing an earlier report for that slug. The report gives each document its own section: the audited `document_sha256`, every check finding with its exact `code`, and your reader findings, labeled as judgment apart from the checks. A later change to a document makes its section stale; a reader finding added later needs a rerun.
4. Report from `scribe-audit.md`, not a separately authored report: its path, whether `result.material_findings` is true, and each document's findings.

A `blocked` audit is an integrity failure, not a finding: an input is missing or unsafe, or a bound source is undeclared or changed since the bundle recorded its hash. It writes no report and leaves an earlier one unchanged. Report that the audit could not establish findings. Never edit a document or a source, or refresh only a hash, to unblock it. To continue, rebind the bundle from the current sources per [Source Grounding](source-grounding.md), re-extracting every bound fact, then rerun; a document change needs a separate `write`.

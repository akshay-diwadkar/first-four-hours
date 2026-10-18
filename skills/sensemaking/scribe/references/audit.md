# Audit

Audit reports what it finds and never fixes it. It does not edit the document, even when remediation is authorized; remediation is a separate `write` with document-revision authority.

1. Run `prepare`, then write a bundle that binds the sources the audit checks per [Source Grounding](source-grounding.md), choosing `profile` per [Document Bundle](document-bundle.md), or reuse the document's existing bundle.
2. Run `audit`. It reads the document, bundle, and bound sources and changes none of them.
3. Report from the `audit` result itself, not a separately authored report: whether `result.material_findings` is true, every entry of `result.findings` with its exact `code`, and `result.document_sha256`, which names the audited bytes. A later document change makes those findings stale.
4. When `audit` returns `status: complete`, read the document as its intended reader. Ask the reader-job question of [Write](write.md) step 2 and the two-reader question of its step 5. In the same report, add each material omission or ambiguity with its location and its consequence for that reader, labeled as your judgment and kept apart from the `audit` findings. Do not resolve it, add gap labels to the document, or edit the document or inputs.

A `blocked` audit is an integrity failure, not a finding: an input is missing, unsafe, or unignored, or a bound source is undeclared or changed since the bundle recorded its hash. Report that the audit could not establish findings. Never edit the document or a source, or refresh only a hash, to unblock it. To continue, rebind the bundle from the current sources per [Source Grounding](source-grounding.md), re-extracting every bound fact, then rerun; a document change needs a separate `write`.

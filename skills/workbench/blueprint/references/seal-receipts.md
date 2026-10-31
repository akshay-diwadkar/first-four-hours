# Seal receipts

Read this on a `receipt.*` diagnostic, on a `proof.*` diagnostic about the Blueprint proof or its receipts rather than an instruction's Proof run, or when consuming a sealed proof. Planners never author these lines.

Sealing appends two generated HTML-comment receipts as the final two lines, after the authored plan: the first holds `blueprint-proof:` followed by the proof JSON (`{"version":"<version>","binding":{...},"locations":[...],"sources":[...]}`), and the last holds `blueprint-validation: <version>; plan-sha256: ...; proof-sha256: ...`, where `<version>` is the sealing Blueprint's version.

The proof is the settled downstream contract; Construct consumes it without guessing:

- `binding` — `repository_id` (non-empty string), `git_head` (null or 40/64-char lowercase hex; provenance only, never compared for freshness), `request_sha256` (64-hex), and `source_item` (diagnosis handoffs only);
- `locations` — for `state: "existing"` or `state: "deleted"`, exactly `path`, `symbol` (when authored), `state`, and `sha256` of the exact worktree bytes; for `state: "new"`, exactly `path` and `state`;
- `sources` — exactly `path` and `sha256` per declared decision-critical source.

`blueprint-validation` binds the canonical authored-body hash and the proof hash. The receipt prefixes are generated-only and globally reserved, independent of marker well-formedness: any authored, displaced, duplicated, malformed, or fenced fake receipt-prefixed line fails closed, and the pair cannot be moved off the final two lines.

Workspace identity binds `repository_id` and the frozen request bytes only, so unrelated HEAD movement never redirects a Blueprint to a suffixed workspace; the planning contract's Source and worktree binding owns freshness.

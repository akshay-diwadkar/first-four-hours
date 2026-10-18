# Architecture Decision Template

Use this heading order. `Alternatives and Tradeoffs` and `View / Contract` are optional; omit them unless they materially affected or communicate the decision. When bounded no-target discovery finds no qualified structural consequence, use the same shape with selected architecture `no-design-change`; do not create a discovery artifact. The sealer rejects text between the title and the first section, non-record Evidence Ledger text, missing required sections, duplicates, reordered sections, unknown headings, empty sections, placeholders, undefined citations, invalid local evidence, and stale local hashes. It does not judge whether the architecture is best.

Evidence records and section citations use readable locators such as `payments/service.py:1-7` or `user-request`:

```text
- source: request | locator: user-request | claim: Requested design pressure.
- source: code | locator: relative/path.py:10-24 | anchor: symbol_name | sha256: 64_lowercase_hex_characters | claim: Observed behavior.
```

Allowed sources: `request`, `code`, `test`, `configuration`, `schema`, `runtime`, and `external`. Local sources use repository-relative `path:start-end`; optional `sha256` binds the inclusive UTF-8/LF line range and is backfilled when omitted. `anchor` must occur inside the cited range. External evidence uses HTTP(S).

```markdown
# Architecture Decision: REPLACE_TITLE

## Context

REPLACE_CURRENT_STRUCTURAL_PROBLEM_OR_OPPORTUNITY_OWNER_BOUNDARY_SCOPE_AND_EXCLUSIONS `user-request` `REPLACE_PATH:REPLACE_LINES`

## Decision

- Selected architecture: REPLACE_SETTLED_DESIGN_AND_THE_DISCRIMINATOR_THAT_MADE_IT_WIN `REPLACE_PATH:REPLACE_LINES`
- Owner / boundary: REPLACE_OWNER_AND_BOUNDARY `REPLACE_PATH:REPLACE_LINES`
- Invariants / constraints: REPLACE_MATERIAL_INVARIANTS_OR_EVIDENCED_NONE `REPLACE_PATH:REPLACE_LINES`
- Consequences: REPLACE_ACCEPTED_CONSEQUENCES `REPLACE_PATH:REPLACE_LINES`
- User-owned policy: REPLACE_ONLY_IF_MATERIAL_USER_POLICY_AFFECTED_THE_DECISION `user-request`

## Evidence and Uncertainty

REPLACE_CURRENT_EVIDENCE_ASSUMPTIONS_AND_UNKNOWNS_NEEDED_TO_TRUST_THE_DECISION `REPLACE_PATH:REPLACE_LINES`

## Alternatives and Tradeoffs

REPLACE_ONLY_MATERIALLY_DISTINCT_ALTERNATIVES_TRADEOFFS_AND_DISCRIMINATORS_THAT_AFFECTED_THE_DECISION `REPLACE_PATH:REPLACE_LINES`

## View / Contract

REPLACE_OPTIONAL_VIEW_OR_CALLER_CONTRACT_ONLY_WHEN_IT_PREVENTS_A_REAL_MISUNDERSTANDING `REPLACE_PATH:REPLACE_LINES`

## Evidence Ledger

- source: request | locator: user-request | claim: REPLACE_REQUEST_CLAIM
- source: code | locator: REPLACE_PATH:REPLACE_LINES | anchor: REPLACE_ANCHOR | sha256: REPLACE_OPTIONAL_HASH | claim: REPLACE_REPOSITORY_CLAIM
```

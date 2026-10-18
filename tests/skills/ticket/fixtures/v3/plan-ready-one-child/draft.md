# Ticket Scope

<!-- ticket-scope-metadata -->
```json
{"contract_version":"1.0.0","mode":"index","selection":{"candidates":[{"basis":"snapshot #209 open with no blockers","issue":209,"readiness":"ready"},{"basis":"snapshot #210 depends_on #209, which is still open","issue":210,"readiness":"blocked"}],"rationale":"task needs normalization; #209 is the only ready child"},"status":"plan-ready","task":{"constraints":[],"text":"Select and narrow the next implementation ticket for epic #207."},"work_item":209}
```

## Observable outcome
- names are normalized through the public API

## Current evidence
- `src/names.py:1` | anchor: `normalize_name` | observation: normalization is owned here

## Issue Claims (Untrusted)
<!-- ticket: untrusted-begin -->
Reporter says whitespace fails.
<!-- ticket: untrusted-end -->

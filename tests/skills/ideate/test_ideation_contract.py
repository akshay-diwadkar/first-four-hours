from __future__ import annotations

import hashlib
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[3] / "skills" / "sensemaking" / "ideate"
sys.path.insert(0, str(SKILL / "scripts"))

from ideation_contract import (  # noqa: E402
    validate_ideation,
)

# ---------------------------------------------------------------------------
# Minimal valid bodies for reuse
# ---------------------------------------------------------------------------


def _valid_open_questions() -> str:
    return (
        "## Open questions / next discriminator\n"
        "- What would change the answer: an index rebuild wins if the cache hit rate falls below 70%\n"
    )


def _valid_body(
    state: str = "decision-ready",
    local_rows: str = "",
    contextual_rows: str = "",
    ext_rows: str = "| Found X | https://example.com | § 2 | 2026-07 | high |\n",
    exploration: str | None = None,
    conclusion: str | None = None,
) -> str:
    if exploration is None:
        exploration = (
            "## Exploration\n\n"
            "### Divergence\n"
            "Search shape: alternative\n"
            "- Simplify/eliminate: drop the slow join\n"
            "- Invert/relax an authorized constraint: not applicable — the latency target is the user's\n"
            "- Domain transfer: Strategy A, CDN-style response caching\n"
            "- Combine mechanisms: Strategy A with an L2 cache tier\n"
            "- Actor/timing/control: precompute results at write time\n"
            "- Failure recovery: serve stale results on a miss\n"
            "- Preserve baseline: keep the 500ms pipeline\n\n"
            "### Dropped\n"
            "- Precompute at write time: write volume makes it costlier than caching\n\n"
            "### Strategy A — Local Caching\n"
            "- Mechanism: In-memory LRU cache\n"
            "- Support basis: evidence-backed: the example.com caching benchmark\n"
            "- Cheapest decisive experiment: test with 10k items; metric: hit rate; pass/fail: >80%; duration: 1h; cost/effort: low\n"
        )
    if conclusion is None:
        conclusion = "## Conclusion\n\nProceed with Strategy A as primary direction based on the example.com benchmark.\n"
    local_section = ""
    if local_rows:
        local_section = (
            "### Local evidence\n\n"
            "| Claim | Source path | Locator | Verification |\n"
            "| --- | --- | --- | --- |\n" + local_rows + "\n"
        )
    contextual_section = ""
    if contextual_rows:
        contextual_section = (
            "### Contextual evidence\n\n"
            "| Claim | Source description | Locator | Verification |\n"
            "| --- | --- | --- | --- |\n" + contextual_rows + "\n"
        )
    ext_section = ""
    if ext_rows:
        ext_section = (
            "### External evidence\n\n"
            "| Finding | Source | Locator | Date/freshness | Relevance |\n"
            "| --- | --- | --- | --- | --- |\n" + ext_rows + "\n"
        )

    return (
        "# Ideation: Optimize Query Latency\n\n"
        "## Handoff\n"
        f"- State: {state}\n"
        "- Selection: open\n"
        "- Goal: reduce p99 query latency under 100ms\n"
        "- Decision criteria: latency reduction, implementation complexity\n"
        "- Scope / non-goals: query processing pipeline; no hardware expansion\n"
        "- Research: condition met — searched cache and index options; no production load traces\n\n"
        "## Evidence\n\n"
        f"{local_section}"
        f"{ext_section}"
        f"{contextual_section}"
        f"{exploration}\n\n"
        f"{conclusion}\n\n"
        f"{_valid_open_questions()}"
    )


def test_readable_evidence_tables_keep_row_checks(tmp_path: Path) -> None:
    benchmark = tmp_path / "bench.txt"
    benchmark.write_text("hit rate 82%\n", encoding="utf-8")
    digest = hashlib.sha256(benchmark.read_bytes()).hexdigest()
    body = _valid_body(
        local_rows=f"| Cache benchmark shows an 82% hit rate | bench.txt | whole file | hash-verified {digest} |\n",
        contextual_rows="| Team caps cache memory at 2 GB | user planning message | first request | user-stated |\n",
        conclusion=(
            "## Conclusion\n\n"
            "Combine Strategy A with an L2 cache tier: the local cache benchmark and the "
            "example.com study both support it within the team's 2 GB memory cap.\n"
        ),
    )

    # Several sources are cited in readable words, with no evidence codes to assign or decode.
    assert validate_ideation(body, repo_root=tmp_path) == []

    # The historical ID column is refused, never translated.
    legacy = body.replace(
        "| Claim | Source path | Locator | Verification |",
        "| ID | Claim | Source path | Locator | Verification |",
    )
    assert "ideation.invalid_local_table_header" in {e.code for e in validate_ideation(legacy, repo_root=tmp_path)}

    # A table outside the three evidence kinds, or an evidence table outside Evidence,
    # would skip their checks, so each is refused.
    stray = body.replace(
        "## Exploration",
        "### Notes\n\n| Claim | Source |\n| --- | --- |\n| x | y |\n\n## Exploration",
        1,
    )
    assert [e.code for e in validate_ideation(stray, repo_root=tmp_path)] == ["ideation.unrecognized_evidence_table"]
    misplaced = body.replace(
        "## Conclusion",
        "### Local evidence\n\n| Claim | Source path | Locator | Verification |\n| --- | --- | --- | --- |\n"
        "| Prior handoff | .first-four-hours/ideations/x/ideation.md | whole file | read |\n\n## Conclusion",
        1,
    )
    assert [e.code for e in validate_ideation(misplaced, repo_root=tmp_path)] == [
        "ideation.misplaced_evidence_declaration"
    ]

    # Local rows are still read and checked: stale and missing files fail at their row.
    benchmark.write_text("hit rate 40%\n", encoding="utf-8")
    assert [e.code for e in validate_ideation(body, repo_root=tmp_path)] == ["ideation.hash_verified_digest_mismatch"]
    benchmark.unlink()
    assert [e.code for e in validate_ideation(body, repo_root=tmp_path)] == ["ideation.local_path_not_found"]


def test_prohibited_direct_construct_routing():
    opt_action = "## Optional downstream action\nDirectly invoke construct to implement changes."
    body = _valid_body() + "\n\n" + opt_action
    errors = validate_ideation(body)
    assert any(e.code == "ideation.prohibited_direct_implementation" for e in errors)

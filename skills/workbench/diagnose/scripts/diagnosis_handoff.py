#!/usr/bin/env python3
"""Canonical diagnosis handoff contract owned by Diagnose.

One provider-free owner for the sealed artifact's contract version, receipt,
headings, field labels, and reserved-delimiter detection. Diagnose validation
and rendering use this module; Blueprint and Construct parse only the final
receipt line and `## Finding <id>` headings, which this contract keeps stable.
"""

from __future__ import annotations

import hashlib
import re

from _skill_protocol_runtime import compatible_version_pattern

CONTRACT_VERSION = "1.0.3"
RECEIPT_MARKER = "diagnosis"

ARTIFACT_TITLE = "Diagnosis"
CONTEXT_HEADING = "Diagnosis Context"
FINDINGS_HEADING = "Findings"
FINDING_HEADING_LABEL = "Finding"
ZERO_FINDINGS_SENTENCE = "No accepted findings."
RULED_OUT_HEADING = "Ruled Out"
OPEN_PROBES_HEADING = "Open Probes"
FIELD_LABELS = {
    "target": "Target",
    "snapshot": "Snapshot",
    "evidence_root": "Evidence root",
    "material_surfaces": "Material surfaces",
    "limitations": "Limitations",
    "finding_count": "Finding count",
}
FINDING_FIELD_LABELS = {
    "title": "Title",
    "cause_status": "Cause status",
    "summary": "Summary",
    "impact": "Impact",
    "cause_or_boundary": "Cause / Ownership Boundary",
    "evidence": "Evidence",
}
RULED_OUT_LABELS = {"hypothesis": "Hypothesis"}
OPEN_PROBE_LABELS = {
    "question": "Question",
    "probe": "Probe",
    "expected_outcomes": "Expected outcomes",
}
RECEIPT_PREFIX = f"<!-- {RECEIPT_MARKER}:"

RESERVED_HEADING_LINE_RE = re.compile(r"^#{1,6}\s", re.MULTILINE)

RECEIPT_RE = re.compile(
    rf"^<!-- {RECEIPT_MARKER}: {compatible_version_pattern(CONTRACT_VERSION)}; sha256: (?P<sha256>[0-9a-f]{{64}}) -->$"
)


def body_digest(body: str) -> str:
    """Return the receipt digest covering every byte before the receipt line."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def receipt_line(digest: str) -> str:
    """Return the exact receipt line sealing one rendered artifact."""
    return f"{RECEIPT_PREFIX} {CONTRACT_VERSION}; sha256: {digest} -->"


def finding_heading(finding_id: str) -> str:
    """Return the deterministic section heading for one finding."""
    return f"## {FINDING_HEADING_LABEL} {finding_id}"


def contains_reserved_delimiter(text: str) -> bool:
    """Detect Markdown heading lines or receipt markers inside authored prose."""
    return bool(RESERVED_HEADING_LINE_RE.search(text) or RECEIPT_PREFIX in text)

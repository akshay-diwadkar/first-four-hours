"""Render the immutable diagnosis-to-publication artifact."""

from __future__ import annotations

import json
from typing import Any

from diagnosis_handoff import (
    ARTIFACT_TITLE,
    CONTEXT_HEADING,
    FIELD_LABELS,
    FINDING_FIELD_LABELS,
    FINDINGS_HEADING,
    OPEN_PROBE_LABELS,
    OPEN_PROBES_HEADING,
    RECEIPT_RE,
    RULED_OUT_HEADING,
    RULED_OUT_LABELS,
    ZERO_FINDINGS_SENTENCE,
    body_digest,
    finding_heading,
    receipt_line,
)


def _scalar(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _evidence_lines(evidence: list[dict[str, Any]], indent: str = "") -> list[str]:
    return [
        f"{indent}- {_scalar({key: value for key, value in item.items() if key != 'observation'})}: {item['observation']}"
        for item in evidence
    ]


def render(bundle: dict[str, Any]) -> str:
    """Render one deterministic, receipt-sealed diagnosis artifact."""
    context = bundle["diagnosis_context"]
    findings = bundle["findings"]
    lines = [f"# {ARTIFACT_TITLE}"]
    if not findings:
        lines.extend(["", f"## {FINDINGS_HEADING}", "", ZERO_FINDINGS_SENTENCE])
    for finding in findings:
        lines.extend(
            [
                "",
                finding_heading(finding["id"]),
                "",
                f"- {FINDING_FIELD_LABELS['title']}: {_scalar(finding['title'])}",
                f"- {FINDING_FIELD_LABELS['cause_status']}: {_scalar(finding['cause_status'])}",
                "",
                f"### {FINDING_FIELD_LABELS['summary']}",
                "",
                finding["summary"],
                "",
                f"### {FINDING_FIELD_LABELS['impact']}",
                "",
                finding["impact"],
                "",
                f"### {FINDING_FIELD_LABELS['cause_or_boundary']}",
                "",
                finding["cause_or_boundary"],
                "",
                f"### {FINDING_FIELD_LABELS['evidence']}",
                "",
            ]
        )
        lines.extend(_evidence_lines(finding["evidence"]))
    if context["ruled_out"]:
        lines.extend(["", f"## {RULED_OUT_HEADING}", ""])
        for entry in context["ruled_out"]:
            lines.append(f"- {RULED_OUT_LABELS['hypothesis']}: {_scalar(entry['hypothesis'])}")
            lines.extend(_evidence_lines(entry["evidence"], "  "))
    if context["open_probes"]:
        lines.extend(["", f"## {OPEN_PROBES_HEADING}", ""])
        for entry in context["open_probes"]:
            lines.extend(
                [
                    f"- {OPEN_PROBE_LABELS['question']}: {_scalar(entry['question'])}",
                    f"  - {OPEN_PROBE_LABELS['probe']}: {_scalar(entry['probe'])}",
                    f"  - {OPEN_PROBE_LABELS['expected_outcomes']}: {_scalar(entry['expected_outcomes'])}",
                ]
            )
    lines.extend(
        [
            "",
            f"## {CONTEXT_HEADING}",
            "",
            f"- {FIELD_LABELS['target']}: {_scalar(context['target'])}",
            f"- {FIELD_LABELS['limitations']}: {_scalar(context['limitations'])}",
            f"- {FIELD_LABELS['finding_count']}: {len(findings)}",
            f"- {FIELD_LABELS['evidence_root']}: {_scalar(context['evidence_root'])}",
            f"- {FIELD_LABELS['snapshot']}: {_scalar(context['snapshot'])}",
            f"- {FIELD_LABELS['material_surfaces']}: {_scalar(context['material_surfaces'])}",
        ]
    )
    body = "\n".join(lines) + "\n"
    return body + receipt_line(body_digest(body)) + "\n"


def verify_receipt(text: str) -> str:
    """Return the receipt-free body after verifying exact content integrity."""
    body_text, separator, final = text.removesuffix("\n").rpartition("\n")
    match = RECEIPT_RE.fullmatch(final)
    if not separator or match is None:
        raise ValueError("handoff receipt is missing or malformed")
    if body_digest(body_text + "\n") != match.group("sha256"):
        raise ValueError("handoff receipt does not match content")
    return body_text + "\n"

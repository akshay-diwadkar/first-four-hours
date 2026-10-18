"""Standard-library-only repair-ready diagnostic contract.

This file is synchronized into executable skill packages. Keep it free of
repository-local imports and third-party dependencies.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

CATEGORIES = (
    "malformed_input",
    "stale_evidence",
    "missing_evidence",
    "contract_contradiction",
    "unsafe_state",
    "unavailable_prerequisite",
)
SEVERITIES = ("info", "warning", "error", "critical")
REQUIRED_FIELDS = (
    "code",
    "category",
    "severity",
    "skill",
    "phase",
    "artifact",
    "record",
    "field",
    "path",
    "message",
    "why_it_matters",
    "required_action",
    "valid_repairs",
    "supporting_evidence",
    "next_command",
)

_CATEGORY_WHY = {
    "malformed_input": "The validator cannot safely interpret the supplied artifact.",
    "stale_evidence": "The recorded evidence no longer proves the current repository state.",
    "missing_evidence": "The required claim has no local evidence that the validator can verify.",
    "contract_contradiction": "Two contract claims cannot both describe a valid workflow state.",
    "unsafe_state": "Continuing from this state could change data or files outside the authorized scope.",
    "unavailable_prerequisite": "The validator cannot complete until the named local prerequisite is available.",
}
_CATEGORY_ACTION = {
    "malformed_input": "Correct the named value in the reported artifact and run the same validation command again.",
    "stale_evidence": "Refresh the named evidence from the current artifact and run the same validation command again.",
    "missing_evidence": "Add the named evidence at the reported location and run the same validation command again.",
    "contract_contradiction": "Reconcile the conflicting values at the reported location and run the same validation command again.",
    "unsafe_state": "Restore an authorized safe state at the reported location and run the same validation command again.",
    "unavailable_prerequisite": "Provide the named prerequisite and run the same validation command again.",
}
_RECORD_RE = re.compile(
    r"\b(?:SC|F|D|CH|P|B|O|C|R|T|X|E|A)-[A-Za-z0-9-]+\b"
    r"|\b(?:baseline\.)?(?:quality_checks|verification|changes|candidates|issues|coverage|deep_analysis)"
    r"\[[0-9]+\]"
)
_FIELD_RE = re.compile(r"\b(?:[A-Za-z_][A-Za-z0-9_-]*\.)+([A-Za-z_][A-Za-z0-9_-]*)\b")
_PATH_RE = re.compile(
    r"(?:^|[\s`'\"])(?P<path>(?:[A-Za-z]:[\\/])?[A-Za-z0-9_.-]+(?:[\\/][A-Za-z0-9_.-]+)+)"
)


def _normalized_path(value: str | Path | None, artifact: str) -> str:
    raw = (str(value or artifact or ".").strip() or ".").rstrip(".,:;")
    return raw.replace("\\", "/")


def command(argv: Sequence[str] | None, cwd: str | Path | None) -> dict[str, Any] | None:
    if not argv:
        return None
    return {
        "argv": [str(item) for item in argv],
        "cwd": _normalized_path(cwd or Path.cwd(), "."),
    }


def _category(code: str, message: str) -> str:
    text = f"{code} {message}".casefold()
    if any(token in text for token in ("stale", "hash mismatch", "sha256.mismatch", "repository_changed")):
        return "stale_evidence"
    if any(token in text for token in ("missing", "required", "no evidence", "empty evidence")):
        return "missing_evidence"
    if any(token in text for token in ("unsafe", "escape", "unauthorized", "dirty_preservation", "outside")):
        return "unsafe_state"
    if any(
        token in text
        for token in ("prerequisite", "not found", "not installed", "unavailable", "cannot import", "missing required import")
    ):
        return "unavailable_prerequisite"
    if any(token in text for token in ("mismatch", "contradict", "unsupported", "conflict", "accounting", "must match")):
        return "contract_contradiction"
    return "malformed_input"


def _record(message: str) -> str | None:
    match = _RECORD_RE.search(message)
    return match.group(0) if match else None


def _field(message: str) -> str | None:
    match = _FIELD_RE.search(message)
    return match.group(1) if match else None


def _path(message: str, fallback: str) -> str:
    match = _PATH_RE.search(message)
    return _normalized_path(match.group("path") if match else fallback, fallback)


def _unique(values: Iterable[str], *, sort: bool = False) -> tuple[str, ...]:
    result = tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))
    return tuple(sorted(result)) if sort else result


@dataclasses.dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    category: str = "malformed_input"
    severity: str = "error"
    skill: str = "unknown"
    phase: str = "validate"
    artifact: str = "input"
    record: str | None = None
    field: str | None = None
    path: str = "."
    why_it_matters: str = ""
    required_action: str = ""
    valid_repairs: tuple[str, ...] = ()
    supporting_evidence: tuple[str, ...] = ()
    next_command: dict[str, Any] | None = None
    extensions: Mapping[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"unsupported diagnostic category: {self.category}")
        if self.severity not in SEVERITIES:
            raise ValueError(f"unsupported diagnostic severity: {self.severity}")
        if not self.code.strip() or not self.message.strip():
            raise ValueError("diagnostic code and message must be non-empty")
        repairs = _unique(self.valid_repairs or (self.required_action or _CATEGORY_ACTION[self.category],))
        evidence = _unique(self.supporting_evidence or (self.message,), sort=True)
        object.__setattr__(self, "path", _normalized_path(self.path, self.artifact))
        object.__setattr__(self, "why_it_matters", self.why_it_matters or _CATEGORY_WHY[self.category])
        object.__setattr__(self, "required_action", self.required_action or repairs[0])
        object.__setattr__(self, "valid_repairs", repairs)
        object.__setattr__(self, "supporting_evidence", evidence)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "code": self.code,
            "category": self.category,
            "severity": self.severity,
            "skill": self.skill,
            "phase": self.phase,
            "artifact": self.artifact,
            "record": self.record,
            "field": self.field,
            "path": self.path,
            "message": self.message,
            "why_it_matters": self.why_it_matters,
            "required_action": self.required_action,
            "valid_repairs": list(self.valid_repairs),
            "supporting_evidence": list(self.supporting_evidence),
            "next_command": self.next_command,
        }
        payload.update(self.extensions)
        return payload


def is_canonical(value: object) -> bool:
    if not isinstance(value, Mapping) or not all(field in value for field in REQUIRED_FIELDS):
        return False
    return (
        value.get("category") in CATEGORIES
        and value.get("severity") in SEVERITIES
        and isinstance(value.get("valid_repairs"), list)
        and bool(value.get("valid_repairs"))
        and isinstance(value.get("supporting_evidence"), list)
        and bool(value.get("supporting_evidence"))
    )


def normalize_diagnostic(
    value: Mapping[str, Any],
    *,
    skill: str,
    phase: str,
    artifact: str,
    path: str | Path,
    next_command: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    code = str(value.get("code") or value.get("rule_id") or value.get("type") or "adapter.validation")
    message = str(value.get("message") or value.get("issue") or "Skill validation failed.")
    category = str(value.get("category") or _category(code, message))
    if category not in CATEGORIES:
        category = _category(code, message)
    severity = str(value.get("severity") or "error")
    if severity not in SEVERITIES:
        severity = "error"
    repair = str(
        value.get("required_action")
        or value.get("hint")
        or value.get("fix")
        or _CATEGORY_ACTION[category]
    )
    repairs_value = value.get("valid_repairs")
    repairs = (
        tuple(str(item) for item in repairs_value)
        if isinstance(repairs_value, list) and repairs_value
        else (repair,)
    )
    evidence_value = value.get("supporting_evidence")
    evidence = (
        tuple(str(item) for item in evidence_value)
        if isinstance(evidence_value, list) and evidence_value
        else (message,)
    )
    target_path = _path(message, str(value.get("path") or path))
    canonical = Diagnostic(
        code=code,
        message=message,
        category=category,
        severity=severity,
        skill=str(value.get("skill") or skill),
        phase=str(value.get("phase") or phase),
        artifact=str(value.get("artifact") or artifact),
        record=value.get("record") if isinstance(value.get("record"), str) else _record(message),
        field=value.get("field") if isinstance(value.get("field"), str) else _field(message),
        path=target_path,
        why_it_matters=str(value.get("why_it_matters") or _CATEGORY_WHY[category]),
        required_action=repair,
        valid_repairs=repairs,
        supporting_evidence=evidence,
        next_command=dict(value["next_command"])
        if isinstance(value.get("next_command"), Mapping)
        else dict(next_command)
        if next_command is not None
        else None,
        extensions={
            key: item
            for key, item in value.items()
            if key not in REQUIRED_FIELDS
        },
    )
    return canonical.to_dict()


def sorted_diagnostics(values: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized = [dict(value) for value in values]
    return sorted(
        normalized,
        key=lambda item: (
            str(item.get("skill", "")),
            str(item.get("phase", "")),
            str(item.get("path", "")),
            str(item.get("artifact", "")),
            str(item.get("record") or ""),
            str(item.get("field") or ""),
            str(item.get("code", "")),
            str(item.get("message", "")),
        ),
    )


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"

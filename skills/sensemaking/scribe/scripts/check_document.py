"""Validate a Markdown document against a source-bound Scribe bundle."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from pathlib import Path, PurePosixPath
from typing import Any

from _diagnostic_contract import normalize_diagnostic
from _document_contract import BUNDLE_FILENAME, WORKSPACE_DIR, require_canonical_name
from _skill_protocol_runtime import compatible_version
from bundle_workspace import WorkspaceError, in_namespace, require_external_bundle
from check_document_language import collect_diagnostics
from jsonschema import Draft7Validator

SKILL_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_SCHEMA = SKILL_ROOT / "schemas" / "document-bundle.schema.json"
BUNDLE_CONTRACT_VERSION = "1.0.0"
# Source-binding repairs point at the bundle or source, never the audited document.
SOURCE_REPAIRS = {
    "unsafe_source_path": "Bind a repository-relative source path inside the repository root.",
    "namespace_source": f"Bind a source outside {WORKSPACE_DIR}/; Scribe audit reports are never evidence.",
    "missing_source": (
        "Bind an existing source file, or report the missing fact as an unresolved gap; "
        "never create a source to satisfy the bundle or edit the document to unblock it."
    ),
    "source_hash_mismatch": (
        "Re-extract the bound facts from the current source, then record its new hash; "
        "never refresh only the hash or edit the source."
    ),
    "undeclared_source": "Declare the cited source in sources with its hash, or remove the reference.",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _error(error_type: str, location: str, severity: str, message: str) -> dict[str, str]:
    return {"type": error_type, "location": location, "severity": severity, "message": message}


def _schema_errors(data: Any) -> list[dict[str, str]]:
    try:
        schema = json.loads(BUNDLE_SCHEMA.read_text(encoding="utf-8"))
        schema["properties"]["glossary"] = json.loads(
            (BUNDLE_SCHEMA.parent / "glossary.schema.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read bundle schema: {exc}") from exc
    errors = sorted(Draft7Validator(schema).iter_errors(data), key=lambda item: list(item.absolute_path))
    result = []
    for item in errors:
        location = ".".join(str(part) for part in item.absolute_path) or "$"
        result.append(_error("invalid_bundle", location, "critical", item.message))
    return result


def load_bundle(path: Path) -> dict[str, Any]:
    require_canonical_name(path, BUNDLE_FILENAME)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        errors = _schema_errors(data)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read bundle: {exc}") from exc
    except RecursionError as exc:
        raise ValueError(
            "cannot read bundle: it is nested too deeply to validate; write a document-bundle.json "
            "that follows schemas/document-bundle.schema.json"
        ) from exc
    if errors:
        raise ValueError("; ".join(f"{item['location']}: {item['message']}" for item in errors))
    assert isinstance(data, dict)
    if not compatible_version(data.get("contract_version"), BUNDLE_CONTRACT_VERSION):
        raise ValueError(
            f"contract_version: must share major version {BUNDLE_CONTRACT_VERSION.split('.')[0]} with "
            f"{BUNDLE_CONTRACT_VERSION!r}; write the bundle from templates/document-bundle.json"
        )
    return data


def _section_bounds(text: str) -> dict[str, tuple[int, int]]:
    headings = list(re.finditer(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", text))
    sections: dict[str, tuple[int, int]] = {"document": (0, len(text))}
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        sections[match.group(1).strip().casefold()] = (match.end(), end)
    return sections


def _scope(text: str, section: str | None, sections: dict[str, tuple[int, int]]) -> tuple[str, int, str]:
    if not section:
        return text, 0, "document"
    bounds = sections.get(section.casefold())
    if bounds is None:
        return "", 0, f"section {section}"
    start, end = bounds
    return text[start:end], start, f"section {section}"


def _tokenize_command(value: str) -> list[str]:
    try:
        return shlex.split(value, posix=True)
    except ValueError:
        return re.findall(r'"[^"]*"|\'[^\']*\'|\S+', value)


def _changed_command(document: str, literal: str) -> bool:
    expected = sorted(_tokenize_command(literal))
    if len(expected) < 2:
        return False
    for line in document.splitlines():
        candidate = line.strip().strip("`")
        if candidate != literal and sorted(_tokenize_command(candidate)) == expected:
            return True
    return False


def _safe_source(repo_root: Path, relative: str) -> Path | None:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or "\\" in relative:
        return None
    candidate = (repo_root / Path(*pure.parts)).resolve()
    try:
        candidate.relative_to(repo_root)
    except ValueError:
        return None
    return candidate


def validate_sources(bundle: dict[str, Any], repo_root: Path) -> list[dict[str, str]]:
    """Return stable source-binding diagnostics for the whole bundle without modifying any input."""
    root = repo_root.resolve()
    errors: list[dict[str, str]] = []

    for source in bundle["sources"]:
        location = f"source {source['id']}"
        path = _safe_source(root, source["path"])
        if path is None:
            errors.append(_error("unsafe_source_path", location, "critical", f"Source path escapes repo root: {source['path']}"))
            continue
        if in_namespace(root, path):
            errors.append(
                _error(
                    "namespace_source",
                    location,
                    "critical",
                    f"Source is inside the {WORKSPACE_DIR}/ audit namespace, which is never evidence: {source['path']}",
                )
            )
            continue
        if not path.is_file():
            errors.append(_error("missing_source", location, "critical", f"Source file does not exist: {source['path']}"))
            continue
        actual = sha256_bytes(path.read_bytes())
        if actual != source["sha256"]:
            errors.append(_error("source_hash_mismatch", location, "critical", f"Source hash changed: {source['path']}"))

    declared = {source["id"] for source in bundle["sources"]}
    for document in bundle["documents"]:
        for record in [*document.get("required_facts", []), *document.get("integrity_literals", [])]:
            for source_id in record["source_ids"]:
                if source_id not in declared:
                    message = f"{record['id']} cites undeclared source {source_id}"
                    errors.append(_error("undeclared_source", f"source {source_id}", "critical", message))

    return sorted(errors, key=lambda item: (item["location"], item["type"], item["message"]))


def validate_document(text: str, document: dict[str, Any]) -> list[dict[str, str]]:
    """Return stable semantic diagnostics for one listed document without modifying any input."""
    sections = _section_bounds(text)
    errors: list[dict[str, str]] = []

    for fact in document.get("required_facts", []):
        scoped, _, location = _scope(text, fact.get("section"), sections)
        if fact["claim"] not in scoped:
            errors.append(_error("missing_required_fact", location, "error", f"Missing fact {fact['id']}: {fact['claim']}"))

    for item in document.get("integrity_literals", []):
        scoped, _, location = _scope(text, item.get("section"), sections)
        if item["literal"] in scoped:
            continue
        error_type = f"changed_{item['kind']}"
        if item["kind"] == "command" and not _changed_command(scoped, item["literal"]):
            error_type = "missing_command"
        elif item["kind"] != "command":
            error_type = f"missing_{item['kind']}"
        errors.append(_error(error_type, location, "critical", f"Required {item['kind']} changed or is missing: {item['literal']}"))

    for procedure in document.get("procedures", []):
        scoped, _, location = _scope(text, procedure.get("section"), sections)
        positions = [scoped.find(marker) for marker in procedure["ordered_markers"]]
        missing = [marker for marker, position in zip(procedure["ordered_markers"], positions, strict=True) if position < 0]
        if missing:
            errors.append(_error("missing_procedure_step", location, "critical", f"Procedure {procedure['id']} is missing: {missing[0]}"))
        elif positions != sorted(positions):
            errors.append(_error("procedure_order", location, "critical", f"Procedure {procedure['id']} is out of order"))

    for warning in document.get("warnings", []):
        scoped, _, location = _scope(text, warning.get("section"), sections)
        warning_at = scoped.find(warning["warning"])
        action_at = scoped.find(warning["dangerous_action"])
        if action_at < 0:
            errors.append(_error("missing_dangerous_action", location, "error", f"Bound action is missing: {warning['dangerous_action']}"))
        elif warning_at < 0:
            errors.append(_error("missing_warning", location, "critical", f"Warning {warning['id']} is missing"))
        elif warning_at > action_at:
            errors.append(_error("warning_order", location, "critical", f"Warning {warning['id']} follows the dangerous action"))

    for recovery in document.get("recovery_steps", []):
        scoped, _, location = _scope(text, recovery.get("section"), sections)
        if recovery["step"] not in scoped:
            errors.append(_error("missing_recovery_step", location, "critical", f"No recovery step for {recovery['id']}: {recovery['step']}"))

    for prerequisite in document.get("prerequisites", []):
        scoped, _, location = _scope(text, prerequisite.get("section"), sections)
        if prerequisite["marker"] not in scoped:
            errors.append(_error("missing_prerequisite", location, "critical", f"Missing prerequisite {prerequisite['id']}"))

    for branch in document.get("branches", []):
        scoped, _, location = _scope(text, branch.get("section"), sections)
        if branch["condition"] not in scoped:
            errors.append(_error("missing_branch", location, "critical", f"Missing branch condition {branch['id']}: {branch['condition']}"))
        for marker in branch["required_markers"]:
            if marker not in scoped:
                errors.append(_error("incomplete_branch", location, "critical", f"Branch {branch['id']} is missing: {marker}"))

    return sorted(errors, key=lambda item: (item["location"], item["type"], item["message"]))


def resolve_documents(bundle: dict[str, Any], repo_root: Path) -> list[Path]:
    """Resolve every listed document path in bundle order without reading any document."""
    root = repo_root.resolve()
    paths = []
    for index, document in enumerate(bundle["documents"]):
        raw = document["path"]
        path = Path(raw).resolve() if Path(raw).is_absolute() else _safe_source(root, raw)
        if path is None:
            raise ValueError(
                f"documents.{index}.path escapes the repository root: {raw}; "
                "give an absolute path or a repository-relative path inside it"
            )
        if in_namespace(root, path):
            raise WorkspaceError(
                "namespace_document",
                f"documents.{index}.path is inside {WORKSPACE_DIR}/, which holds only audit reports; "
                f"keep the document where its reader uses it: {raw}",
            )
        paths.append(path)
    return paths


def inspect_bundle(repo_root: Path, bundle_path: Path) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Load an external bundle, check its sources, and check every listed document; read-only."""
    root = repo_root.resolve()
    bundle = load_bundle(require_external_bundle(root, bundle_path))
    paths = resolve_documents(bundle, root)
    sources = validate_sources(bundle, root)
    records = []
    for spec, path in zip(bundle["documents"], paths, strict=True):
        try:
            data = path.read_bytes()
            text = data.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"cannot read document {path}: {exc}") from exc
        records.append(
            {
                "path": path,
                "profile": spec["profile"],
                "document_sha256": "sha256:" + sha256_bytes(data),
                "language": collect_diagnostics(text, spec["profile"], bundle["glossary"]),
                "semantic": validate_document(text, spec),
                "reader_findings": spec.get("reader_findings", []),
            }
        )
    return sources, records


def repair_diagnostics(
    language: list[dict[str, Any]],
    semantic: list[dict[str, str]],
    *,
    phase: str,
    path: Path,
    document: Path | None = None,
) -> list[dict[str, Any]]:
    """Convert language and semantic findings into canonical repair-ready diagnostics."""
    named = {"document": str(document)} if document is not None else {}
    result = [
        normalize_diagnostic(
            {
                **item,
                "code": item["rule_id"],
                "message": item["issue"],
                "record": f"line {item['line']}",
                "field": "sentence",
                "required_action": item["fix"],
                "valid_repairs": [item["fix"]],
                "supporting_evidence": [item["sentence"]],
                **named,
            },
            skill="scribe",
            phase=phase,
            artifact="document",
            path=path,
        )
        for item in language
    ]
    result.extend(
        normalize_diagnostic(
            {
                **item,
                "code": item["type"],
                "record": item["location"],
                **(
                    {"required_action": SOURCE_REPAIRS[item["type"]], "valid_repairs": [SOURCE_REPAIRS[item["type"]]]}
                    if item["type"] in SOURCE_REPAIRS
                    else {}
                ),
                **named,
            },
            skill="scribe",
            phase=phase,
            artifact="document-bundle" if item["location"].startswith("source ") else "document",
            path=path,
        )
        for item in semantic
    )
    return result

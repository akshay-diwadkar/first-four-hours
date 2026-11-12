"""Validate a Markdown document against a source-bound Scribe bundle."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from pathlib import Path, PurePosixPath
from typing import Any

from _diagnostic_contract import normalize_diagnostic
from _document_contract import (
    BUNDLE_FILENAME,
    GAP_MARKER,
    GAP_OPENING,
    INLINE_CODE,
    WORKSPACE_DIR,
    require_canonical_name,
)
from _skill_protocol_runtime import compatible_version
from bundle_workspace import WorkspaceError, in_namespace, require_external_bundle
from check_document_language import collect_diagnostics

SKILL_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_SCHEMA = SKILL_ROOT / "schemas" / "document-bundle.schema.json"
BUNDLE_CONTRACT_VERSION = "1.1.1"
# Source-binding repairs point at the bundle or source, never the audited document.
SOURCE_REPAIRS = {
    "unsafe_source_path": (
        "Bind a repository-relative path inside the repository root, or an absolute path to captured evidence "
        "inside the bundle's directory; bind repository files only by repository-relative path."
    ),
    "namespace_source": f"Bind a source outside {WORKSPACE_DIR}/; Scribe audit reports are never evidence.",
    "missing_source": (
        "Bind an existing source file, recapture supplied evidence verbatim beside the bundle, or report the missing "
        "fact as an unresolved gap; never invent a source or edit the document to unblock it."
    ),
    "source_hash_mismatch": (
        "Re-extract the bound facts from the current source, then record its new hash; "
        "never refresh only the hash or edit the source."
    ),
    "undeclared_source": "Declare the cited source in sources with its hash, or remove the reference.",
}
# Document-check repairs: code -> (category, required action).
DOCUMENT_REPAIRS = {
    "ambiguous_section": (
        "malformed_input",
        "Give the heading a name that occurs once in the document, or remove the record's section value.",
    ),
    "unsupported_section": (
        "malformed_input",
        "Remove the section value; only .md, .markdown, and .txt documents have sections.",
    ),
    "ambiguous_marker": (
        "contract_contradiction",
        "Scope the record to the one section that holds the step, or bind marker text that occurs once in that scope.",
    ),
    "unknown_procedure": (
        "contract_contradiction",
        "Name a procedure id this document declares, or remove the prerequisite's procedure value.",
    ),
    "prerequisite_order": ("contract_contradiction", "Move the prerequisite before the first step of its procedure."),
    "recovery_order": ("contract_contradiction", "Put the recovery step after its trigger."),
    "malformed_gap": ("malformed_input", "Write the gap on one line as [GAP: <missing fact>; owner: <next owner>]."),
    "unresolved_gap": (
        "missing_evidence",
        "Bind a source that settles the missing fact and replace the marker, or take the gap to its named owner; "
        "never fill it by guessing.",
    ),
}
PROSE_SUFFIXES = frozenset({".md", ".markdown", ".txt"})
HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _error(error_type: str, location: str, severity: str, message: str) -> dict[str, str]:
    return {"type": error_type, "location": location, "severity": severity, "message": message}


_SCHEMA_KEYWORDS = frozenset(
    {
        "$schema",
        "title",
        "type",
        "properties",
        "required",
        "additionalProperties",
        "propertyNames",
        "items",
        "minItems",
        "minLength",
        "pattern",
        "enum",
        "uniqueItems",
    }
)
_PYTHON_TYPES: dict[str, type] = {"object": dict, "array": list, "string": str}


def _validate(
    schema: dict[str, Any], value: Any, path: list[str | int], errors: list[tuple[list[str | int], str]]
) -> None:
    """Append (path, message) for each violation of the JSON Schema keywords Scribe's schemas use."""
    for key in schema:
        if key not in _SCHEMA_KEYWORDS:
            raise ValueError(f"cannot read bundle schema: unsupported keyword {key!r}")
    names = schema.get("propertyNames")
    if names is not None:
        for key in names:
            if key != "pattern":
                raise ValueError(f"cannot read bundle schema: unsupported keyword {key!r}")
    expected = schema.get("type")
    if expected is not None:
        if expected not in _PYTHON_TYPES:
            raise ValueError(f"cannot read bundle schema: unsupported type {expected!r}")
        if not isinstance(value, _PYTHON_TYPES[expected]):
            errors.append((path, f"is not of type {expected!r}"))
            return
    if "enum" in schema and value not in schema["enum"]:
        errors.append((path, f"must be one of {schema['enum']!r}"))
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append((path, f"must be at least {schema['minLength']} characters long"))
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append((path, f"{value!r} does not match {schema['pattern']!r}"))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append((path, f"must have at least {schema['minItems']} items"))
        if schema.get("uniqueItems"):
            dumped = [json.dumps(item, sort_keys=True) for item in value]
            if len(set(dumped)) != len(dumped):
                errors.append((path, "has non-unique items"))
        if "items" in schema:
            for index, item in enumerate(value):
                _validate(schema["items"], item, [*path, index], errors)
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                errors.append((path, f"{name!r} is a required property"))
        extra = [key for key in value if key not in properties]
        additional = schema.get("additionalProperties")
        if additional is False:
            if extra:
                errors.append((path, "additional properties are not allowed: " + ", ".join(repr(key) for key in sorted(extra))))
        elif isinstance(additional, dict):
            for key in extra:
                _validate(additional, value[key], [*path, key], errors)
        if names is not None and "pattern" in names:
            for key in value:
                if not re.search(names["pattern"], key):
                    errors.append((path, f"property name {key!r} does not match {names['pattern']!r}"))
        for key in value:
            if key in properties:
                _validate(properties[key], value[key], [*path, key], errors)


def _schema_errors(data: Any) -> list[dict[str, str]]:
    try:
        schema = json.loads(BUNDLE_SCHEMA.read_text(encoding="utf-8"))
        schema["properties"]["glossary"] = json.loads(
            (BUNDLE_SCHEMA.parent / "glossary.schema.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read bundle schema: {exc}") from exc
    errors: list[tuple[list[str | int], str]] = []
    _validate(schema, data, [], errors)
    return [
        _error("invalid_bundle", ".".join(str(part) for part in path) or "$", "critical", message)
        for path, message in sorted(errors, key=lambda item: item[0])
    ]


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


def _lines(text: str) -> list[tuple[int, str, bool]]:
    """Return (offset, line, in_code) for each line; fence lines and the lines between them are code."""
    result = []
    offset = 0
    fenced = False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        fence = stripped.startswith("```") or stripped.startswith("~~~")
        result.append((offset, line, fenced or fence))
        if fence:
            fenced = not fenced
        offset += len(line)
    return result


def _section_bounds(text: str) -> dict[str, list[tuple[int, int]]]:
    """Map each casefolded heading to its occurrences; a section ends at the next heading of its level or higher."""
    headings = []
    for offset, line, in_code in _lines(text):
        match = None if in_code else HEADING.match(line.rstrip("\r\n"))
        if match:
            headings.append((offset, offset + len(line), len(match.group(1)), match.group(2).strip().casefold()))
    sections: dict[str, list[tuple[int, int]]] = {}
    for index, (_, body, level, name) in enumerate(headings):
        end = next((later[0] for later in headings[index + 1 :] if later[2] <= level), len(text))
        sections.setdefault(name, []).append((body, end))
    return sections


def _scope(
    text: str, record: dict[str, Any], sections: dict[str, list[tuple[int, int]]], prose: bool
) -> tuple[str, int, str, dict[str, str] | None]:
    section = record.get("section")
    if not section:
        return text, 0, "document", None
    location = f"section {section}"
    record_id = record.get("id", "record")
    if not prose:
        message = f"{record_id} sets a section, but only .md, .markdown, and .txt documents have sections"
        return "", 0, location, _error("unsupported_section", location, "critical", message)
    bounds = sections.get(section.casefold())
    if bounds is None:
        return "", 0, location, None
    if len(bounds) > 1:
        message = f"{record_id} names heading {section}, which occurs more than once"
        return "", 0, location, _error("ambiguous_section", location, "critical", message)
    start, end = bounds[0]
    return text[start:end], start, location, None


def _is_word(character: str) -> bool:
    return character.isalnum() or character == "_"


def _normalize(text: str) -> tuple[str, list[int]]:
    """Drop backticks and emphasis delimiters, collapse whitespace, and map each kept character to its raw offset."""
    characters: list[str] = []
    offsets: list[int] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character == "`":
            index += 1
            continue
        if text.startswith("**", index) or text.startswith("__", index):
            index += 2
            continue
        if character in "*_":
            before = index > 0 and _is_word(text[index - 1])
            after = index + 1 < len(text) and _is_word(text[index + 1])
            if before != after:
                index += 1
                continue
        if character.isspace():
            if not characters or characters[-1] != " ":
                characters.append(" ")
                offsets.append(index)
            index += 1
            continue
        characters.append(character)
        offsets.append(index)
        index += 1
    return "".join(characters), offsets


def _phrase(value: str) -> str:
    return _normalize(value)[0].strip()


def _occurrences(normalized: str, phrase: str) -> list[int]:
    positions = []
    start = normalized.find(phrase)
    while phrase and start >= 0:
        positions.append(start)
        start = normalized.find(phrase, start + len(phrase))
    return positions


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


def _captured_evidence(root: Path, bundle_path: Path, raw: str) -> Path | None:
    """Resolve an absolute evidence path beside the bundle, outside the repository, other than the bundle itself."""
    path = Path(raw).resolve()
    bundle = bundle_path.resolve()
    try:
        path.relative_to(bundle.parent)
    except ValueError:
        return None
    if path == bundle:
        return None
    try:
        path.relative_to(root)
    except ValueError:
        return path
    return None


def validate_sources(bundle: dict[str, Any], repo_root: Path, bundle_path: Path) -> list[dict[str, str]]:
    """Return stable source-binding diagnostics for the whole bundle without modifying any input."""
    root = repo_root.resolve()
    errors: list[dict[str, str]] = []

    for source in bundle["sources"]:
        location = f"source {source['id']}"
        absolute = Path(source["path"]).is_absolute()
        path = _captured_evidence(root, bundle_path, source["path"]) if absolute else _safe_source(root, source["path"])
        if path is None:
            message = (
                "Source path is neither repository-relative inside the repository root nor captured evidence "
                f"beside the bundle: {source['path']}"
            )
            errors.append(_error("unsafe_source_path", location, "critical", message))
            continue
        if not absolute and in_namespace(root, path):
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


def validate_document(text: str, document: dict[str, Any], *, prose: bool = True) -> list[dict[str, str]]:
    """Return stable semantic diagnostics for one listed document without modifying any input."""
    sections = _section_bounds(text) if prose else {}
    errors: list[dict[str, str]] = []

    def scope(record: dict[str, Any]) -> tuple[str, int, str, str, list[int]] | None:
        scoped, start, location, error = _scope(text, record, sections, prose)
        if error is not None:
            errors.append(error)
            return None
        normalized, offsets = _normalize(scoped)
        return scoped, start, location, normalized, offsets

    def ambiguous(location: str, record_id: str, marker: str) -> None:
        message = f"{record_id} marker occurs more than once in its scope: {marker}"
        errors.append(_error("ambiguous_marker", location, "critical", message))

    for fact in document.get("required_facts", []):
        scoped_fact = scope(fact)
        if scoped_fact is None:
            continue
        _, _, location, normalized, _ = scoped_fact
        if not _occurrences(normalized, _phrase(fact["claim"])):
            errors.append(_error("missing_required_fact", location, "error", f"Missing fact {fact['id']}: {fact['claim']}"))

    for item in document.get("integrity_literals", []):
        scoped_literal = scope(item)
        if scoped_literal is None:
            continue
        scoped, _, location, _, _ = scoped_literal
        if item["literal"] in scoped:
            continue
        error_type = f"changed_{item['kind']}"
        if item["kind"] == "command" and not _changed_command(scoped, item["literal"]):
            error_type = "missing_command"
        elif item["kind"] != "command":
            error_type = f"missing_{item['kind']}"
        errors.append(_error(error_type, location, "critical", f"Required {item['kind']} changed or is missing: {item['literal']}"))

    procedure_ids = {procedure["id"] for procedure in document.get("procedures", [])}
    procedure_starts: dict[str, int] = {}
    for procedure in document.get("procedures", []):
        scoped_procedure = scope(procedure)
        if scoped_procedure is None:
            continue
        _, start, location, normalized, offsets = scoped_procedure
        markers = procedure["ordered_markers"]
        found = [_occurrences(normalized, _phrase(marker)) for marker in markers]
        missing = [marker for marker, positions in zip(markers, found, strict=True) if not positions]
        repeated = [marker for marker, positions in zip(markers, found, strict=True) if len(positions) > 1]
        if missing:
            errors.append(_error("missing_procedure_step", location, "critical", f"Procedure {procedure['id']} is missing: {missing[0]}"))
            continue
        if repeated:
            ambiguous(location, procedure["id"], repeated[0])
            continue
        firsts = [positions[0] for positions in found]
        if any(later <= earlier for earlier, later in zip(firsts, firsts[1:])):
            errors.append(_error("procedure_order", location, "critical", f"Procedure {procedure['id']} is out of order"))
            continue
        procedure_starts[procedure["id"]] = start + offsets[firsts[0]]

    for warning in document.get("warnings", []):
        scoped_warning = scope(warning)
        if scoped_warning is None:
            continue
        _, _, location, normalized, _ = scoped_warning
        warnings_at = _occurrences(normalized, _phrase(warning["warning"]))
        actions_at = _occurrences(normalized, _phrase(warning["dangerous_action"]))
        if not actions_at:
            errors.append(_error("missing_dangerous_action", location, "error", f"Bound action is missing: {warning['dangerous_action']}"))
        elif not warnings_at:
            errors.append(_error("missing_warning", location, "critical", f"Warning {warning['id']} is missing"))
        elif len(warnings_at) > 1 or len(actions_at) > 1:
            ambiguous(location, warning["id"], warning["warning"] if len(warnings_at) > 1 else warning["dangerous_action"])
        elif warnings_at[0] > actions_at[0]:
            errors.append(_error("warning_order", location, "critical", f"Warning {warning['id']} follows the dangerous action"))

    for recovery in document.get("recovery_steps", []):
        scoped_recovery = scope(recovery)
        if scoped_recovery is None:
            continue
        _, _, location, normalized, _ = scoped_recovery
        triggers_at = _occurrences(normalized, _phrase(recovery["trigger"]))
        steps_at = _occurrences(normalized, _phrase(recovery["step"]))
        if not triggers_at:
            errors.append(
                _error("missing_recovery_trigger", location, "critical", f"No recovery trigger for {recovery['id']}: {recovery['trigger']}")
            )
        if not steps_at:
            errors.append(_error("missing_recovery_step", location, "critical", f"No recovery step for {recovery['id']}: {recovery['step']}"))
        if triggers_at and steps_at:
            if len(triggers_at) > 1 or len(steps_at) > 1:
                ambiguous(location, recovery["id"], recovery["trigger"] if len(triggers_at) > 1 else recovery["step"])
            elif steps_at[0] <= triggers_at[0]:
                message = f"Recovery step {recovery['id']} does not follow its trigger: {recovery['trigger']}"
                errors.append(_error("recovery_order", location, "critical", message))

    for prerequisite in document.get("prerequisites", []):
        scoped_prerequisite = scope(prerequisite)
        if scoped_prerequisite is None:
            continue
        _, start, location, normalized, offsets = scoped_prerequisite
        found_at = _occurrences(normalized, _phrase(prerequisite["marker"]))
        if not found_at:
            errors.append(_error("missing_prerequisite", location, "critical", f"Missing prerequisite {prerequisite['id']}"))
            continue
        procedure_id = prerequisite.get("procedure")
        if not procedure_id:
            continue
        if procedure_id not in procedure_ids:
            message = f"{prerequisite['id']} names undeclared procedure {procedure_id}"
            errors.append(_error("unknown_procedure", location, "critical", message))
            continue
        if procedure_id not in procedure_starts:
            continue
        if len(found_at) > 1:
            ambiguous(location, prerequisite["id"], prerequisite["marker"])
        elif start + offsets[found_at[0]] >= procedure_starts[procedure_id]:
            message = f"Prerequisite {prerequisite['id']} does not precede procedure {procedure_id}"
            errors.append(_error("prerequisite_order", location, "critical", message))

    for branch in document.get("branches", []):
        scoped_branch = scope(branch)
        if scoped_branch is None:
            continue
        _, _, location, normalized, _ = scoped_branch
        if not _occurrences(normalized, _phrase(branch["condition"])):
            errors.append(_error("missing_branch", location, "critical", f"Missing branch condition {branch['id']}: {branch['condition']}"))
        for marker in branch["required_markers"]:
            if not _occurrences(normalized, _phrase(marker)):
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
    sources = validate_sources(bundle, root, bundle_path)
    records = []
    for spec, path in zip(bundle["documents"], paths, strict=True):
        try:
            data = path.read_bytes()
            text = data.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"cannot read document {path}: {exc}") from exc
        prose = path.suffix.casefold() in PROSE_SUFFIXES
        gaps, malformed = _find_gaps(_gap_search_text(text, prose))
        semantic = validate_document(text, spec, prose=prose) + malformed
        records.append(
            {
                "path": path,
                "profile": spec["profile"],
                "document_sha256": "sha256:" + sha256_bytes(data),
                "language": collect_diagnostics(text, spec["profile"], bundle["glossary"]) if prose else [],
                "semantic": sorted(semantic, key=lambda item: (item["location"], item["type"], item["message"])),
                "reader_findings": spec.get("reader_findings", []),
                "gaps": gaps,
                "language_checked": prose,
            }
        )
    return sources, records


def _blank(value: str) -> str:
    return re.sub(r"[^\n]", " ", value)


def _gap_search_text(text: str, prose: bool) -> str:
    """Return text where gap markers count: a prose document hides fenced and inline code; other files search everything."""
    if not prose:
        return text
    parts = []
    for _, line, in_code in _lines(text):
        parts.append(_blank(line) if in_code else INLINE_CODE.sub(lambda match: _blank(match.group()), line))
    return "".join(parts)


def _find_gaps(text: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Return well-formed gap markers in document order and a malformed_gap error for every other opening."""
    gaps: list[dict[str, Any]] = []
    starts = set()
    for match in GAP_MARKER.finditer(text):
        starts.add(match.start())
        line = text.count("\n", 0, match.start()) + 1
        gaps.append({"line": line, "missing": match.group("missing").strip(), "owner": match.group("owner").strip()})
    malformed = []
    for match in GAP_OPENING.finditer(text):
        if match.start() not in starts:
            line = text.count("\n", 0, match.start()) + 1
            message = f"Gap marker on line {line} is not [GAP: <missing fact>; owner: <next owner>]"
            malformed.append(_error("malformed_gap", f"line {line}", "critical", message))
    return gaps, malformed


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
                **(
                    {
                        "category": DOCUMENT_REPAIRS[item["type"]][0],
                        "required_action": DOCUMENT_REPAIRS[item["type"]][1],
                        "valid_repairs": [DOCUMENT_REPAIRS[item["type"]][1]],
                    }
                    if item["type"] in DOCUMENT_REPAIRS
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

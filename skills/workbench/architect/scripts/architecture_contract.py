"""Parse and validate the sole architect handoff format."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from _diagnostic_contract import normalize_diagnostic

ARTIFACT_ROOT = ".first-four-hours"
WORKSPACE_PARTS = (ARTIFACT_ROOT, "architectures")
WORKSPACE_DIR = "/".join(WORKSPACE_PARTS)
BLUEPRINT_WORKSPACE_PARTS = (ARTIFACT_ROOT, "blueprints")

EVIDENCE_HEADING = "Evidence Ledger"
REQUIRED_SECTIONS = (
    "Context",
    "Decision",
    "Evidence and Uncertainty",
)
OPTIONAL_SECTIONS = (
    "Alternatives and Tradeoffs",
    "View / Contract",
)
EXPECTED_HEADINGS = (*REQUIRED_SECTIONS, *OPTIONAL_SECTIONS, EVIDENCE_HEADING)
LOCAL_SOURCES = {"code", "test", "configuration", "schema"}
EVIDENCE_SOURCES = {"request", *LOCAL_SOURCES, "runtime", "external"}

HEADING_RE = re.compile(r"^## (?P<name>.+?)\s*$", re.MULTILINE)
ATX_HEADING_RE = re.compile(r"^(?P<heading>#{1,6}\s+.+?)\s*$", re.MULTILINE)
SETEXT_HEADING_RE = re.compile(r"^(?P<text>[^\n]+)\n(?P<underline>[=-]{2,})\s*$", re.MULTILINE)
TITLE_RE = re.compile(r"^# Architecture Decision:\s*(?P<title>.*?)\s*$", re.MULTILINE)
EVIDENCE_RE = re.compile(r"^- (?P<fields>source:\s*.+)$", re.MULTILINE)
CITATION_RE = re.compile(r"`(user-request|https?://[^`]+|[^`]+:[1-9]\d*(?:-[1-9]\d*)?)`")
RETIRED_CITATION_RE = re.compile(r"\[E-[1-9]\d*\]")
LOCAL_LOCATOR_RE = re.compile(r"^(?P<path>.+):(?P<start>[1-9]\d*)(?:-(?P<end>[1-9]\d*))?$")
PLACEHOLDER_RE = re.compile(
    r"\b(?:TBD|TODO|FIXME|REPLACE(?:_[A-Z0-9_]+)?|INSERT HERE|AS NEEDED)\b|\{\{[^}\n]+\}\}",
    re.IGNORECASE,
)
REASONING_STATE_RE = re.compile(
    r"\b(?:reason(?:ing)?[\s_-]+transcript|temporary[\s_-]+reasoning|scratchpad|reasoning[\s_-]+state)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    line: int | None = None

    def __str__(self) -> str:
        location = f"line {self.line}: " if self.line is not None else ""
        return f"{self.code}: {location}{self.message}"

    def as_dict(
        self,
        *,
        path: str | Path = "architecture.md",
        next_command: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return normalize_diagnostic(
            asdict(self),
            skill="architect",
            phase="validate",
            artifact="architecture",
            path=path,
            next_command=next_command,
        )


@dataclass(frozen=True)
class Evidence:
    identifier: str
    source: str
    locator: str
    claim: str
    anchor: str | None
    sha256: str | None
    line: int


@dataclass(frozen=True)
class ParsedHandoff:
    sections: dict[str, str]
    evidence: dict[str, Evidence]


def normalize_markdown(text: str) -> str:
    """Normalize line endings and trailing whitespace with one final newline."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in normalized.strip().splitlines()) + "\n"


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _fields(raw: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for part in raw.split(" | "):
        key, separator, value = part.partition(":")
        if separator:
            values[key.strip().casefold()] = value.strip()
    return values


def excerpt_sha256(lines: list[str], start: int, end: int) -> str:
    """Hash an inclusive excerpt using the architecture contract canonicalization."""
    excerpt = "\n".join(lines[start - 1 : end]) + "\n"
    return hashlib.sha256(excerpt.encode()).hexdigest()


def _present(value: str) -> bool:
    return bool(value.strip()) and PLACEHOLDER_RE.search(value) is None


def _parse_sections(text: str) -> tuple[dict[str, str], list[Diagnostic]]:
    matches = list(HEADING_RE.finditer(text))
    names = [match.group("name").strip() for match in matches]
    diagnostics: list[Diagnostic] = []
    allowed = set(EXPECTED_HEADINGS)
    for expected in (EVIDENCE_HEADING, *REQUIRED_SECTIONS):
        count = names.count(expected)
        if count == 0:
            diagnostics.append(Diagnostic("section.missing", f"Missing required section '## {expected}'."))
        elif count > 1:
            diagnostics.append(Diagnostic("section.duplicate", f"Section '## {expected}' appears {count} times."))
    for optional in OPTIONAL_SECTIONS:
        count = names.count(optional)
        if count > 1:
            diagnostics.append(Diagnostic("section.duplicate", f"Section '## {optional}' appears {count} times."))
    for index, name in enumerate(names):
        if name not in allowed:
            diagnostics.append(
                Diagnostic(
                    "section.unknown",
                    f"Unknown level-two section '## {name}'.",
                    _line_number(text, matches[index].start()),
                )
            )
    expected_order = [name for name in EXPECTED_HEADINGS if name in names]
    if names != expected_order:
        diagnostics.append(
            Diagnostic(
                "section.order",
                "Level-two headings must follow this order, omitting only optional sections: "
                + ", ".join(EXPECTED_HEADINGS)
                + ".",
            )
        )
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        name = match.group("name").strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.setdefault(name, text[match.end() : end].strip())
    return sections, diagnostics


def _validate_title(text: str) -> list[Diagnostic]:
    matches = list(TITLE_RE.finditer(text))
    if len(matches) != 1 or (matches and matches[0].start() != 0):
        return [
            Diagnostic(
                "title.invalid",
                "Handoff requires exactly one leading '# Architecture Decision: TITLE' heading.",
            )
        ]
    if not _present(matches[0].group("title")):
        return [Diagnostic("title.placeholder", "Design handoff title must be non-empty and contain no placeholder.")]
    return []


def _validate_closed_markdown(text: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    allowed_headings = {f"## {name}" for name in EXPECTED_HEADINGS}
    title = TITLE_RE.search(text)
    first_section = HEADING_RE.search(text)
    if title is not None and first_section is not None and text[title.end() : first_section.start()].strip():
        diagnostics.append(
            Diagnostic(
                "body.extra_outside_sections",
                "Only blank lines may appear between the title and the first section.",
                _line_number(text, title.end()),
            )
        )
    for match in ATX_HEADING_RE.finditer(text):
        heading = match.group("heading").strip()
        if TITLE_RE.fullmatch(heading) or heading in allowed_headings:
            continue
        diagnostics.append(
            Diagnostic(
                "section.unknown",
                f"Unknown markdown heading '{heading}'.",
                _line_number(text, match.start()),
            )
        )
    for match in SETEXT_HEADING_RE.finditer(text):
        diagnostics.append(
            Diagnostic(
                "section.unknown",
                f"Unknown markdown heading '{match.group('text').strip()}'.",
                _line_number(text, match.start()),
            )
        )
    return diagnostics


def _parse_evidence(body: str, full_text: str) -> tuple[dict[str, Evidence], list[Diagnostic]]:
    evidence: dict[str, Evidence] = {}
    diagnostics: list[Diagnostic] = []
    ledger_offset = full_text.find(body)
    for match in EVIDENCE_RE.finditer(body):
        line = _line_number(full_text, max(0, ledger_offset) + match.start())
        fields = _fields(match.group("fields"))
        missing = [name for name in ("source", "locator", "claim") if not fields.get(name)]
        if missing:
            diagnostics.append(
                Diagnostic(
                    "evidence.fields.missing",
                    f"Evidence record is missing: {', '.join(missing)}.",
                    line,
                )
            )
            continue
        identifier = fields["locator"]
        if identifier in evidence:
            diagnostics.append(
                Diagnostic("evidence.duplicate", f"Evidence locator {identifier!r} is duplicated.", line)
            )
            continue
        evidence[identifier] = Evidence(
            identifier=identifier,
            source=fields["source"].casefold(),
            locator=fields["locator"],
            claim=fields["claim"],
            anchor=fields.get("anchor"),
            sha256=fields.get("sha256"),
            line=line,
        )
    if RETIRED_CITATION_RE.search(body):
        diagnostics.append(
            Diagnostic("evidence.private_notation", "Evidence Ledger must use direct locators, not [E-n] notation.")
        )
    unparsed_lines = [line for line in body.splitlines() if line.strip() and EVIDENCE_RE.fullmatch(line) is None]
    if unparsed_lines:
        diagnostics.append(
            Diagnostic(
                "evidence.ledger.extra",
                "Evidence Ledger may contain only evidence records and blank lines.",
            )
        )
    if not evidence:
        diagnostics.append(Diagnostic("evidence.missing", "Evidence Ledger requires at least one evidence record."))
    return evidence, diagnostics


def _validate_local_evidence(
    item: Evidence,
    repo_root: Path,
    *,
    require_evidence_hashes: bool,
    file_cache: dict[Path, list[str]],
) -> tuple[list[Diagnostic], str | None]:
    match = LOCAL_LOCATOR_RE.fullmatch(item.locator)
    if not match:
        return [
            Diagnostic(
                "evidence.locator.invalid",
                f"[{item.identifier}] local evidence requires relative path:start-end.",
                item.line,
            )
        ], None
    relative = Path(match.group("path"))
    if relative.is_absolute():
        return [
            Diagnostic(
                "evidence.path.absolute",
                f"[{item.identifier}] repository locator must be relative.",
                item.line,
            )
        ], None
    target = (repo_root / relative).resolve()
    try:
        target.relative_to(repo_root)
    except ValueError:
        return [
            Diagnostic(
                "evidence.path.escape",
                f"[{item.identifier}] locator escapes the repository.",
                item.line,
            )
        ], None
    if target.is_relative_to(repo_root) and tuple(part.casefold() for part in target.relative_to(repo_root).parts[:2]) in {BLUEPRINT_WORKSPACE_PARTS, WORKSPACE_PARTS}:
        return [Diagnostic('evidence.path.planning', 'Architecture evidence cannot cite excluded Blueprint planning or Architect workspace artifacts.', item.line)], None
    if not target.is_file():
        return [
            Diagnostic(
                "evidence.path.missing",
                f"[{item.identifier}] cited file does not exist: {relative.as_posix()}.",
                item.line,
            )
        ], None
    if target not in file_cache:
        file_cache[target] = target.read_text(encoding="utf-8", errors="replace").splitlines()
    lines = file_cache[target]
    start = int(match.group("start"))
    end = int(match.group("end") or start)
    if end < start or end > len(lines):
        return [
            Diagnostic(
                "evidence.lines.invalid",
                f"[{item.identifier}] line range {start}-{end} is outside the {len(lines)}-line file.",
                item.line,
            )
        ], None
    if item.anchor and item.anchor not in "\n".join(lines[start - 1 : end]):
        return [
            Diagnostic(
                "evidence.anchor.missing",
                f"[{item.identifier}] anchor '{item.anchor}' is absent from the cited range.",
                item.line,
            )
        ], None
    current_hash = excerpt_sha256(lines, start, end)
    if item.sha256 is None:
        if require_evidence_hashes:
            return [
                Diagnostic(
                    "evidence.sha256.missing",
                    f"[{item.identifier}] local evidence requires sha256 when evidence verification is enabled.",
                    item.line,
                )
            ], current_hash
        return [], current_hash
    if not re.fullmatch(r"[0-9a-f]{64}", item.sha256):
        return [
            Diagnostic(
                "evidence.sha256.invalid",
                f"[{item.identifier}] sha256 must be exactly 64 lowercase hexadecimal characters.",
                item.line,
            )
        ], current_hash
    if item.sha256 != current_hash:
        return [
            Diagnostic(
                "evidence.sha256.mismatch",
                f"[{item.identifier}] sha256 does not match current content at {item.locator}; evidence is stale.",
                item.line,
            )
        ], current_hash
    return [], current_hash


def _validate_evidence(
    evidence: dict[str, Evidence],
    repo_root: Path,
    *,
    require_evidence_hashes: bool,
    file_cache: dict[Path, list[str]],
) -> tuple[list[Diagnostic], dict[str, str]]:
    diagnostics: list[Diagnostic] = []
    hashes: dict[str, str] = {}
    for item in evidence.values():
        if item.source not in EVIDENCE_SOURCES:
            diagnostics.append(
                Diagnostic(
                    "evidence.source.invalid",
                    f"[{item.identifier}] source must be one of {sorted(EVIDENCE_SOURCES)}.",
                    item.line,
                )
            )
        elif item.source in LOCAL_SOURCES:
            local_diagnostics, current_hash = _validate_local_evidence(
                item,
                repo_root,
                require_evidence_hashes=require_evidence_hashes,
                file_cache=file_cache,
            )
            diagnostics.extend(local_diagnostics)
            if current_hash is not None:
                hashes[item.identifier] = current_hash
        elif item.source == "request" and item.locator != "user-request":
            diagnostics.append(
                Diagnostic(
                    "evidence.request.locator",
                    f"[{item.identifier}] request evidence locator must be 'user-request'.",
                    item.line,
                )
            )
        elif item.source == "external" and not re.match(r"^https?://\S+$", item.locator):
            diagnostics.append(
                Diagnostic(
                    "evidence.external.locator",
                    f"[{item.identifier}] external evidence requires an HTTP(S) URL.",
                    item.line,
                )
            )
        if item.source not in LOCAL_SOURCES and item.sha256 is not None:
            diagnostics.append(
                Diagnostic(
                    "evidence.sha256.unsupported",
                    f"[{item.identifier}] sha256 is supported only for code, test, configuration, and schema evidence.",
                    item.line,
                )
            )
        for field, value in (("locator", item.locator), ("claim", item.claim)):
            marker = REASONING_STATE_RE.search(value)
            if marker:
                diagnostics.append(
                    Diagnostic(
                        "evidence.reasoning_state",
                        f"[{item.identifier}] evidence {field} contains persisted reasoning state: '{marker.group()}'.",
                        item.line,
                    )
                )
        if not _present(item.claim):
            diagnostics.append(
                Diagnostic(
                    "evidence.claim.placeholder",
                    f"[{item.identifier}] claim must be non-empty and contain no placeholder.",
                    item.line,
                )
            )
    return diagnostics, hashes


def _parse_handoff(text: str) -> tuple[str, ParsedHandoff, list[Diagnostic]]:
    """Normalize and parse a handoff exactly once."""
    normalized = normalize_markdown(text)
    sections, diagnostics = _parse_sections(normalized)
    diagnostics.extend(_validate_title(normalized))
    diagnostics.extend(_validate_closed_markdown(normalized))
    evidence, evidence_diagnostics = _parse_evidence(sections.get(EVIDENCE_HEADING, ""), normalized)
    diagnostics.extend(evidence_diagnostics)
    if RETIRED_CITATION_RE.search(normalized):
        diagnostics.append(
            Diagnostic(
                "evidence.private_notation",
                "Architecture handoffs must cite direct evidence locators, not [E-n] notation.",
            )
        )
    return normalized, ParsedHandoff(sections=sections, evidence=evidence), diagnostics


def _validate_parsed_handoff(
    _normalized: str,
    parsed: ParsedHandoff,
    repo_root: Path,
    *,
    require_evidence_hashes: bool,
    file_cache: dict[Path, list[str]],
) -> tuple[list[Diagnostic], dict[str, str]]:
    """Run mechanical validators against one parsed handoff."""
    diagnostics: list[Diagnostic] = []
    evidence_diagnostics, hashes = _validate_evidence(
        parsed.evidence,
        repo_root.resolve(),
        require_evidence_hashes=require_evidence_hashes,
        file_cache=file_cache,
    )
    diagnostics.extend(evidence_diagnostics)

    for name in (*REQUIRED_SECTIONS, *OPTIONAL_SECTIONS):
        body = parsed.sections.get(name)
        if body is None:
            continue
        if not _present(body):
            diagnostics.append(
                Diagnostic(
                    "section.content.invalid",
                    f"Section '## {name}' must be non-empty and contain no placeholder.",
                )
            )
        citations = set(CITATION_RE.findall(body))
        if not citations:
            diagnostics.append(
                Diagnostic("section.citation.missing", f"Section '## {name}' requires evidence citation.")
            )
        for identifier in sorted(citations - set(parsed.evidence)):
            diagnostics.append(
                Diagnostic(
                    "section.citation.undefined",
                    f"Section '## {name}' cites undefined evidence [{identifier}].",
                )
            )
        marker = REASONING_STATE_RE.search(body)
        if marker:
            diagnostics.append(
                Diagnostic(
                    "section.reasoning_state",
                    f"Section '## {name}' contains persisted reasoning state: '{marker.group()}'.",
                )
            )
    return diagnostics, hashes


def validate_handoff(
    text: str,
    repo_root: Path,
    *,
    require_evidence_hashes: bool = False,
) -> tuple[ParsedHandoff, list[Diagnostic]]:
    """Parse and validate one architecture decision against the current repository."""
    normalized, parsed, diagnostics = _parse_handoff(text)
    validation_diagnostics, _hashes = _validate_parsed_handoff(
        normalized,
        parsed,
        repo_root,
        require_evidence_hashes=require_evidence_hashes,
        file_cache={},
    )
    diagnostics.extend(validation_diagnostics)
    return parsed, diagnostics


def _insert_missing_hashes(
    normalized: str,
    evidence: dict[str, Evidence],
    hashes: dict[str, str],
) -> str:
    """Insert computed hashes without reparsing the handoff."""
    missing = {
        identifier: hashes[identifier]
        for identifier, item in evidence.items()
        if item.sha256 is None and identifier in hashes
    }
    if not missing:
        return normalized

    evidence_body = re.search(
        r"^## Evidence Ledger\s*$\n(?P<body>.*?)(?=^## |\Z)",
        normalized,
        re.MULTILINE | re.DOTALL,
    )
    if evidence_body is None:
        return normalized

    def insert_hash(match: re.Match[str]) -> str:
        fields = match.group("fields")
        parsed = _fields(fields)
        digest = missing.get(parsed.get("locator", ""))
        if digest is None:
            return match.group(0)
        marker = " | claim:"
        claim_offset = fields.find(marker)
        if claim_offset < 0:
            return match.group(0)
        with_hash = fields[:claim_offset] + f" | sha256: {digest}" + fields[claim_offset:]
        return f"- {with_hash}"

    body = evidence_body.group("body")
    hashed_body = EVIDENCE_RE.sub(insert_hash, body)
    return normalized[: evidence_body.start("body")] + hashed_body + normalized[evidence_body.end("body") :]


def seal_handoff(
    text: str,
    repo_root: Path,
) -> tuple[ParsedHandoff, list[Diagnostic], str]:
    """Validate and reseal one handoff in memory without reparsing it."""
    normalized, parsed, diagnostics = _parse_handoff(text)
    file_cache: dict[Path, list[str]] = {}
    validation_diagnostics, hashes = _validate_parsed_handoff(
        normalized,
        parsed,
        repo_root,
        require_evidence_hashes=False,
        file_cache=file_cache,
    )
    diagnostics.extend(validation_diagnostics)
    if diagnostics:
        return parsed, diagnostics, normalized
    return parsed, diagnostics, _insert_missing_hashes(normalized, parsed.evidence, hashes)

#!/usr/bin/env python3
"""Parse and validate the sole ideation.md handoff format.

Deterministic, standard-library-only. No model calls, web requests, or
external dependencies.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from _diagnostic_contract import normalize_diagnostic
from ideation_workspace import WORKSPACE_DIR, WORKSPACE_PARTS

# ---------------------------------------------------------------------------
# Structural constants
# ---------------------------------------------------------------------------

IDEATE_VERSION = "2.0.0"

WHAT_TO_DO_HEADING = "## What to do"
GOAL_AND_RESEARCH_HEADING = "## Goal and research"
WHAT_WOULD_CHANGE_HEADING = "## What would change the answer"
SUGGESTED_FOLLOW_UP_HEADING = "## Suggested follow-up"

REQUIRED_HEADINGS = (
    WHAT_TO_DO_HEADING,
    GOAL_AND_RESEARCH_HEADING,
    "## Evidence",
    "## Exploration",
    WHAT_WOULD_CHANGE_HEADING,
)
OPTIONAL_HEADINGS = (
    SUGGESTED_FOLLOW_UP_HEADING,
)

OUTCOMES = {"recommended direction", "run an experiment first", "research limit reached"}
RESEARCH_STOP_REASON_PREFIXES = (
    "settled",
    "diminishing returns",
    "unavailable sources",
    "user limit",
)
WEB_OPT_OUT_STOP_REASONS = ("unavailable sources", "user limit")

TITLE_RE = re.compile(r"^# Ideation:[ \t]*(.+)$")
OUTCOME_RE = re.compile(r"^- Outcome:[ \t]*(.+)$", re.MULTILINE)
RESEARCH_RE = re.compile(r"^- Research:[ \t]*(.+)$", re.MULTILINE)
RESEARCH_RECORD_RE = re.compile(
    r"^(?:" + "|".join(re.escape(prefix) for prefix in RESEARCH_STOP_REASON_PREFIXES) + r")[ \t]+[—-][ \t]+\S",
    re.IGNORECASE,
)
FINAL_CHOICE_RE = re.compile(r"^- Final choice:[ \t]*(.+)$", re.MULTILINE)
FINAL_CHOICE_VALUE_RE = re.compile(r"^(yours to make|made by you|delegated)(?:[ \t]+[—-][ \t]+(\S.*))?$")
WHAT_TO_DO_FIELD_LINE_RE = re.compile(r"^- (?:Outcome|Final choice):.*$", re.MULTILINE)

WHAT_TO_DO_REQUIRED_FIELDS = (
    "- Outcome:",
    "- Final choice:",
)
GOAL_AND_RESEARCH_REQUIRED_FIELDS = (
    "- Goal:",
    "- Decision criteria:",
    "- Scope / non-goals:",
    "- Research:",
)

SUPPORT_BASIS_PREFIXES = (
    "evidence-backed:",
    "assumption-backed:",
    "hypothesis:",
)

SEARCH_SHAPES = ("alternative", "path", "path with a fork")
SEQUENCED_SHAPES = ("path", "path with a fork")
SEARCH_SHAPE_RE = re.compile(r"^Search shape:[ \t]*(.*)$", re.MULTILINE)
HTML_COMMENT_RE = re.compile(r"<!--.*?(?:-->|\Z)", re.DOTALL)
CAUSAL_LENSES = (
    "Obvious defaults",
    "Simplify/eliminate",
    "Invert/relax an authorized constraint",
    "Domain transfer",
    "Combine mechanisms",
    "Actor/timing/control",
    "Failure recovery",
    "Preserve baseline",
)
SEQUENCING_LENSES = (
    "Risk-first",
    "Value-first",
    "Reversible-first",
    "Dependency-forced",
    "Cheapest-learning-first",
)

PROHIBITED_RE = re.compile(
    r"```(?:diff|patch)\s*\n(?:@@|\+\+\+|---)",
    re.IGNORECASE,
)
DIGEST_RE = re.compile(r"\b[0-9a-f]{64}\b", re.IGNORECASE)

LOCAL_HEADER = "| Claim | Source path | Locator | Verification |"
EXTERNAL_HEADER = "| Finding | Source | Locator | Date/freshness | Relevance |"
CONTEXTUAL_HEADER = "| Claim | Source description | Locator | Verification |"
EVIDENCE_TABLES = {
    "### Local evidence": ("local", LOCAL_HEADER),
    "### External evidence": ("external", EXTERNAL_HEADER),
    "### Contextual evidence": ("contextual", CONTEXTUAL_HEADER),
}
TABLE_SEPARATOR_RE = re.compile(r"^\|(?:[ \t]*:?-+:?[ \t]*\|)+$")
EMPTY_CELLS = ("", "-", "—")


# ---------------------------------------------------------------------------
# Diagnostic dataclass
# ---------------------------------------------------------------------------


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
        path: str | Path = "ideation.md",
        next_command: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return normalize_diagnostic(
            asdict(self),
            skill="ideate",
            phase="validate",
            artifact="ideation",
            path=path,
            next_command=next_command,
        )


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _section_body(text: str, heading: str) -> str:
    """Extract text from heading to next same-level heading or end."""
    pattern = re.compile(
        rf"^{re.escape(heading)}\s*\n(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    return m.group(1) if m else ""


def _evidence_rows(evidence_section: str) -> tuple[dict[str, list[list[str]]], list[Diagnostic]]:
    """Return evidence rows keyed by source kind, read from the fixed evidence subsections."""
    rows: dict[str, list[list[str]]] = {"local": [], "external": [], "contextual": []}
    errors: list[Diagnostic] = []
    current: tuple[str, str] | None = None
    header_pending = False
    stray = False
    for line in evidence_section.splitlines():
        line_s = line.strip()
        if line_s.startswith("### "):
            current = EVIDENCE_TABLES.get(line_s)
            header_pending = True
            continue
        if not line_s.startswith("|"):
            continue
        if current is None:
            stray = True
            continue
        kind, header = current
        if header_pending:
            header_pending = False
            if line_s != header:
                errors.append(
                    Diagnostic(
                        f"ideation.invalid_{kind}_table_header",
                        f"{kind.capitalize()} evidence table header must exactly match {header!r}",
                    )
                )
            continue
        if TABLE_SEPARATOR_RE.fullmatch(line_s):
            continue
        cells = [cell.strip() for cell in line_s.split("|")[1:-1]]
        width = header.count("|") - 1
        if len(cells) != width:
            errors.append(
                Diagnostic(
                    f"ideation.invalid_{kind}_table_row_width",
                    f"{kind.capitalize()} evidence row width must have {width} columns, found {len(cells)}",
                )
            )
            continue
        rows[kind].append(cells)
    if stray:
        errors.append(
            Diagnostic(
                "ideation.unrecognized_evidence_table",
                "evidence table lines must sit under '### Local evidence', "
                "'### External evidence', or '### Contextual evidence'",
            )
        )
    return rows, errors


def _parse_support_basis(value: str) -> tuple[str | None, str]:
    """Return (kind, remainder) for a Support basis field value."""
    trimmed = value.strip()
    lowered = trimmed.casefold()
    for prefix in SUPPORT_BASIS_PREFIXES:
        if lowered.startswith(prefix):
            return (prefix[:-1], trimmed[len(prefix):].strip())
    return (None, trimmed)


def _validate_research_record(record: str) -> list[Diagnostic]:
    if RESEARCH_RECORD_RE.match(record.strip()):
        return []
    return [
        Diagnostic(
            "ideation.invalid_research_record",
            "research record must read '<settled | diminishing returns | unavailable sources | user limit> "
            "— <coverage searched; limitations>'",
        )
    ]


def _validate_final_choice(final_choice: str) -> list[Diagnostic]:
    match = FINAL_CHOICE_VALUE_RE.fullmatch(final_choice.strip())
    if match is None or (match.group(1) != "yours to make" and match.group(2) is None):
        return [
            Diagnostic(
                "ideation.invalid_final_choice",
                "final choice must be 'yours to make', 'made by you — <choice; source>', "
                "or 'delegated — <scope; source>'",
            )
        ]
    return []


EXPERIMENT_COMPONENT_RE = re.compile(
    r"(metric|pass/fail|duration|cost/effort|cost|effort)\s*:\s*([^;]*)",
    re.IGNORECASE,
)
REQUIRED_EXPERIMENT_COMPONENTS = ("metric", "pass/fail", "duration")
COST_EFFORT_COMPONENTS = ("cost/effort", "cost", "effort")


def _parse_experiment_components(value: str) -> dict[str, str]:
    """Parse 'metric: m; pass/fail: p; ...' into component name -> trimmed value."""
    components: dict[str, str] = {}
    for m in EXPERIMENT_COMPONENT_RE.finditer(value):
        name = m.group(1).lower()
        components[name] = m.group(2).strip()
    return components


def _validate_decisive_experiment(owner: str, value: str) -> list[Diagnostic]:
    """Require a metric, pass/fail rule, duration bound, and cost/effort bound."""
    errors: list[Diagnostic] = []
    components = _parse_experiment_components(value)
    for name in REQUIRED_EXPERIMENT_COMPONENTS:
        if not components.get(name, ""):
            errors.append(
                Diagnostic(
                    "ideation.decisive_experiment_incomplete",
                    f"{owner}: decisive experiment requires a non-empty '{name}:' value",
                )
            )
    if not any(components.get(name, "") for name in COST_EFFORT_COMPONENTS):
        errors.append(
            Diagnostic(
                "ideation.decisive_experiment_incomplete",
                f"{owner}: decisive experiment requires a non-empty 'cost:' or 'effort:' bound",
            )
        )
    return errors


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_ideation(text: str, repo_root: Path | None = None) -> list[Diagnostic]:
    """Validate an ideation.md body (receipt already stripped)."""
    errors: list[Diagnostic] = []

    # 1. Title is first non-empty body line with non-empty goal
    stripped_text = text.lstrip("\r\n")
    first_line = stripped_text.splitlines()[0].strip() if stripped_text else ""
    title_m = TITLE_RE.match(first_line)
    if not title_m or not title_m.group(1).strip():
        errors.append(Diagnostic("ideation.missing_title", "document must begin with '# Ideation: <goal>' on the first line"))

    # 2. Required headings in order and exactly once
    heading_positions: list[int] = []
    for heading in REQUIRED_HEADINGS:
        count = text.count(heading)
        if count == 0:
            errors.append(Diagnostic("ideation.missing_heading", f"required heading is absent: {heading!r}"))
            heading_positions.append(-1)
        elif count > 1:
            errors.append(Diagnostic("ideation.duplicate_heading", f"required heading appears {count} times: {heading!r}"))
            heading_positions.append(text.find(heading))
        else:
            heading_positions.append(text.find(heading))

    valid_positions = [p for p in heading_positions if p != -1]
    if valid_positions != sorted(valid_positions):
        errors.append(Diagnostic("ideation.heading_order", "required headings must appear in canonical order"))

    sec_opt_idx = text.find(SUGGESTED_FOLLOW_UP_HEADING)
    if sec_opt_idx != -1:
        if text.count(SUGGESTED_FOLLOW_UP_HEADING) > 1:
            errors.append(Diagnostic("ideation.duplicate_heading", f"optional heading {SUGGESTED_FOLLOW_UP_HEADING!r} appears multiple times"))
        sec_change_idx = text.find(WHAT_WOULD_CHANGE_HEADING)
        if sec_change_idx != -1 and sec_opt_idx < sec_change_idx:
            errors.append(Diagnostic("ideation.heading_order", "Suggested follow-up must appear after What would change the answer"))

    # 3. Required fields of What to do and Goal and research
    what_to_do_body = _section_body(text, WHAT_TO_DO_HEADING)
    goal_and_research_body = _section_body(text, GOAL_AND_RESEARCH_HEADING)
    for body, fields in (
        (what_to_do_body, WHAT_TO_DO_REQUIRED_FIELDS),
        (goal_and_research_body, GOAL_AND_RESEARCH_REQUIRED_FIELDS),
    ):
        for field in fields:
            line_re = re.compile(rf"^{re.escape(field)}[ \t]*(.*)$", re.MULTILINE)
            m = line_re.search(body)
            if not m or not m.group(1).strip():
                errors.append(Diagnostic("ideation.field_empty", f"required field is missing or empty: {field!r}"))

    research_m = RESEARCH_RE.search(goal_and_research_body)
    research_valid = False
    if research_m:
        research_errors = _validate_research_record(research_m.group(1))
        research_valid = not research_errors
        errors.extend(research_errors)

    final_choice_m = FINAL_CHOICE_RE.search(what_to_do_body)
    if final_choice_m:
        errors.extend(_validate_final_choice(final_choice_m.group(1)))

    # 4. Outcome
    outcome_m = OUTCOME_RE.search(what_to_do_body)
    if not outcome_m:
        errors.append(
            Diagnostic(
                "ideation.missing_outcome",
                "What to do requires '- Outcome: recommended direction | run an experiment first | research limit reached'",
            )
        )
        outcome = ""
    else:
        outcome = outcome_m.group(1).strip()
        if outcome not in OUTCOMES:
            errors.append(
                Diagnostic(
                    "ideation.invalid_outcome",
                    "outcome must be one of: recommended direction, run an experiment first, research limit reached",
                )
            )

    # What to do states the recommendation or next step in prose after its fields
    what_to_do_prose = WHAT_TO_DO_FIELD_LINE_RE.sub("", HTML_COMMENT_RE.sub("", what_to_do_body))
    if not what_to_do_prose.strip():
        errors.append(
            Diagnostic(
                "ideation.empty_what_to_do",
                "What to do must state the recommendation or the next step in plain language after its fields",
            )
        )

    # 5. Evidence section
    evidence_section = _section_body(text, "## Evidence")

    # 6. Evidence rows, read by their fixed subsection
    rows, table_errors = _evidence_rows(evidence_section)
    errors.extend(table_errors)

    # Evidence subsections and tables elsewhere would skip these checks, so they are refused.
    evidence_markers = set(EVIDENCE_TABLES) | {header for _kind, header in EVIDENCE_TABLES.values()}

    def _marker_count(body: str) -> int:
        return sum(1 for line in body.splitlines() if line.strip() in evidence_markers)

    if _marker_count(text) > _marker_count(evidence_section):
        errors.append(
            Diagnostic(
                "ideation.misplaced_evidence_declaration",
                "evidence subsections and tables must appear only inside the Evidence section",
            )
        )

    for _claim, local_path, locator, verification in rows["local"]:
        label = f"local evidence {local_path!r}"
        if locator in EMPTY_CELLS:
            errors.append(Diagnostic("ideation.empty_local_locator", f"{label}: locator must be non-empty"))
        if verification in EMPTY_CELLS:
            errors.append(Diagnostic("ideation.empty_local_verification", f"{label}: verification must be non-empty"))

        resolved = None
        if local_path in EMPTY_CELLS:
            errors.append(Diagnostic("ideation.local_path_not_found", f"{label}: source path must be non-empty"))
        elif repo_root is not None:
            try:
                resolved = (repo_root / local_path).resolve()
                relative = resolved.relative_to(repo_root.resolve())
                if tuple(part.casefold() for part in relative.parts[:2]) == WORKSPACE_PARTS:
                    errors.append(
                        Diagnostic(
                            "ideation.workspace_evidence",
                            f"{label}: path {local_path!r} is inside the Ideate workspace ({WORKSPACE_DIR}/) and is never evidence",
                        )
                    )
                    resolved = None
                elif not resolved.exists() or not resolved.is_file():
                    errors.append(
                        Diagnostic("ideation.local_path_not_found", f"{label}: path {local_path!r} does not exist or is not a regular file")
                    )
                    resolved = None
            except ValueError:
                resolved = None
                errors.append(Diagnostic("ideation.local_path_escape", f"{label}: path {local_path!r} escapes the workspace root"))

        if "hash-verified" in verification.lower():
            digest_m = DIGEST_RE.search(verification)
            if not digest_m:
                errors.append(
                    Diagnostic("ideation.hash_verified_without_digest", f"{label}: 'hash-verified' requires a SHA-256 digest")
                )
            elif resolved is not None:
                actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
                if digest_m.group(0).lower() != actual:
                    errors.append(
                        Diagnostic(
                            "ideation.hash_verified_digest_mismatch",
                            f"{label}: 'hash-verified' digest does not match file {local_path!r}",
                        )
                    )

    for _claim, source_description, locator, verification in rows["contextual"]:
        label = f"contextual evidence {source_description!r}"
        if locator in EMPTY_CELLS:
            errors.append(Diagnostic("ideation.empty_contextual_locator", f"{label}: locator must be non-empty"))
        if verification in EMPTY_CELLS:
            errors.append(Diagnostic("ideation.empty_contextual_verification", f"{label}: verification must be non-empty"))

    # Web research is the default: with no External row naming a source, research must
    # record why the web was not searched.
    if research_m and research_valid:
        sourced_external = [row for row in rows["external"] if row[1] not in EMPTY_CELLS]
        stop_reason = research_m.group(1).strip().casefold()
        if not sourced_external and not stop_reason.startswith(WEB_OPT_OUT_STOP_REASONS):
            errors.append(
                Diagnostic(
                    "ideation.web_research_missing",
                    "no External evidence row: search the web and record what it found (including that it "
                    "found nothing relevant), or record why not with 'user limit' (the user said not to) "
                    "or 'unavailable sources' (web research could not be done)",
                )
            )

    # 7. Exploration section
    exploration_body = _section_body(text, "## Exploration")
    if not exploration_body.strip():
        errors.append(Diagnostic("ideation.empty_exploration", "Exploration section must be non-empty"))

    # Divergence record: a search shape and one line per required lens, outside HTML comments,
    # checked for presence only
    visible_exploration = HTML_COMMENT_RE.sub("", exploration_body)
    shape_m = SEARCH_SHAPE_RE.search(visible_exploration)
    shape = shape_m.group(1).strip() if shape_m else ""
    if shape not in SEARCH_SHAPES:
        errors.append(
            Diagnostic(
                "ideation.invalid_search_shape",
                "Exploration must declare 'Search shape: alternative | path | path with a fork'",
            )
        )
    required_lenses = CAUSAL_LENSES + (SEQUENCING_LENSES if shape in SEQUENCED_SHAPES else ())
    for lens in required_lenses:
        if not re.search(rf"^- {re.escape(lens)}:[ \t]*\S", visible_exploration, re.MULTILINE):
            errors.append(
                Diagnostic(
                    "ideation.lens_unaccounted",
                    f"Exploration must account for lens '{lens}': write '- {lens}: <candidate>' "
                    f"or '- {lens}: not applicable — <one-line reason>'",
                )
            )

    # Check for decisive experiments inside Exploration or document
    for exp_m in re.finditer(
        r"^[ \t]*- (?:Cheapest decisive experiment|Next experiment):[ \t]*(.+)$",
        text,
        re.MULTILINE | re.IGNORECASE,
    ):
        errors.extend(_validate_decisive_experiment("Exploration", exp_m.group(1)))

    what_would_change_body = _section_body(text, WHAT_WOULD_CHANGE_HEADING)

    # Check support bases if declared
    for support_m in re.finditer(r"^- Support basis:[ \t]*(.+)$", exploration_body, re.MULTILINE):
        kind, remainder = _parse_support_basis(support_m.group(1))
        if kind is None:
            errors.append(
                Diagnostic(
                    "ideation.invalid_support_basis",
                    "support basis must begin with one of: "
                    + ", ".join(prefix.rstrip(":") for prefix in SUPPORT_BASIS_PREFIXES),
                )
            )
        elif not remainder:
            errors.append(
                Diagnostic(
                    "ideation.invalid_support_basis",
                    f"{kind} support basis requires non-empty text after the prefix",
                )
            )

    # 8. Outcome invariants
    if outcome == "recommended direction":
        if sum(len(found) for found in rows.values()) == 0:
            errors.append(
                Diagnostic(
                    "ideation.recommendation_without_evidence",
                    "outcome 'recommended direction' requires at least one evidence row (local, external, or contextual)",
                )
            )

    # 9. Suggested follow-up routing restriction
    sec_opt_body = _section_body(text, SUGGESTED_FOLLOW_UP_HEADING)
    if sec_opt_body and "construct" in sec_opt_body.lower():
        errors.append(
            Diagnostic(
                "ideation.prohibited_direct_implementation",
                "suggested follow-up must never route directly to 'construct'",
            )
        )

    # 10. Prohibited implementation patches
    if PROHIBITED_RE.search(text):
        errors.append(
            Diagnostic(
                "ideation.prohibited_implementation",
                "ideation.md must not contain implementation patches or diff hunks",
            )
        )

    # 11. What would change the answer
    if not HTML_COMMENT_RE.sub("", what_would_change_body).strip():
        errors.append(
            Diagnostic(
                "ideation.empty_what_would_change",
                "What would change the answer must state the strongest challenge and when another candidate "
                "or the baseline would win",
            )
        )

    return errors


def validate_ideation_path(draft_path: Path, repo_root: Path | None = None) -> list[Diagnostic]:
    """Validate an ideation.md file on disk (strip receipt if present)."""
    text = draft_path.read_text(encoding="utf-8")
    head, _, final = text.removesuffix("\n").rpartition("\n")
    if final.startswith("<!-- ideation-handoff:"):
        text = head + "\n"
    return validate_ideation(text, repo_root=repo_root)


def seal_body(text: str) -> str:
    """Normalize line endings and trailing whitespace for sealing."""
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"


def compute_digest(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()

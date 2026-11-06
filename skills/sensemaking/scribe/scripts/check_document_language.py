"""Apply deterministic MTE-1 language checks to a Markdown document."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from _document_contract import GAP_MARKER, INLINE_CODE

DEFAULT_ACTIONS = {
    "add",
    "apply",
    "back",
    "close",
    "configure",
    "connect",
    "copy",
    "create",
    "delete",
    "disable",
    "disconnect",
    "enable",
    "enter",
    "install",
    "move",
    "open",
    "press",
    "remove",
    "replace",
    "restart",
    "restore",
    "run",
    "save",
    "select",
    "set",
    "start",
    "stop",
    "turn",
    "type",
    "uninstall",
    "update",
    "verify",
}
DEFAULT_PHRASAL = {"back up", "carry out", "log in", "log out", "set up", "shut down", "turn off", "turn on"}
DEFAULT_HAZARDS = {"delete", "disconnect", "format", "purge", "remove", "reset", "shutdown", "stop", "uninstall"}
CONDITION_WORDS = ("if", "unless", "when", "after", "before", "while")
KNOWN_DEMONSTRATIVE_NOUNS = {
    "action",
    "command",
    "file",
    "literal",
    "manual",
    "operator",
    "package",
    "path",
    "process",
    "section",
    "service",
    "step",
    "system",
    "value",
}
OBJECTLESS_STOP_FOLLOWERS = set(CONDITION_WORDS) | {"and", "here", "then", "now", "immediately"}
IRREGULAR_PARTICIPLES = (
    "begun", "broken", "built", "chosen", "done", "drawn", "driven", "eaten", "fallen", "forgotten", "found",
    "frozen", "given", "gotten", "held", "hidden", "kept", "known", "lost", "made", "paid", "run", "seen", "sent",
    "set", "shown", "shut", "spent", "split", "stolen", "taken", "thrown", "told", "written",
)
NON_PARTICIPLES = ("bleed", "breed", "embed", "feed", "hundred", "indeed", "need", "seed", "shed", "speed")
PASSIVE = re.compile(
    r"\b(?:am|is|are|was|were|be|been|being)\s+(?:\w+\s+){0,2}"
    r"(?!(?:" + "|".join(NON_PARTICIPLES) + r")\b)"
    r"(?:\w{2,}ed|" + "|".join(IRREGULAR_PARTICIPLES) + r")\b"
)
TABLE_DELIMITER_CELL = re.compile(r"^:?-+:?$")
STYLE_WARNINGS_STANDARD = {"MTE-VOICE-001", "MTE-PHRASAL-001", "MTE-NOM-001"}
RULE_TEXT = {
    "MTE-SENT-001": ("Multiple actions in one sentence", "Split the actions into separate sentences"),
    "MTE-TERM-001": ("Nonpreferred term", "Use the preferred glossary term"),
    "MTE-VOICE-001": ("Passive voice", "Name the actor and use active voice"),
    "MTE-REF-001": ("Vague reference", "Replace the reference with a specific noun"),
    "MTE-PHRASAL-001": ("Phrasal verb", "Use a single precise verb"),
    "MTE-COND-001": ("Condition follows the action", "Move the condition before the action"),
    "MTE-WARN-001": ("Warning does not precede a hazardous action", "Add a warning before the action"),
    "MTE-ABBR-001": ("Undefined abbreviation", "Define the abbreviation before first use"),
    "MTE-NOM-001": ("Nominalization chain", "Replace the noun chain with a direct verb"),
    "MTE-LEN-001": ("Sentence exceeds the strict word limit", "Shorten or split the sentence"),
}


@dataclass(frozen=True)
class Sentence:
    text: str
    line: int
    scopes: tuple[int, ...]
    procedural: bool
    index: int


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", text)


def _strip_markdown_prefix(line: str) -> tuple[str, bool]:
    text = re.sub(r"^\s*>\s?", "", line)
    match = re.match(r"^\s*(?:[-+*]|\d+[.)])\s+(.*)$", text)
    return (match.group(1), True) if match else (text.strip(), False)


def _table_cells(line: str) -> list[str]:
    """Split one table row at pipes outside inline code spans and not escaped with a backslash."""
    spans = [match.span() for match in INLINE_CODE.finditer(line)]
    cells: list[str] = []
    current: list[str] = []
    for index, character in enumerate(line):
        inside = any(start <= index < end for start, end in spans)
        if character == "|" and not inside and (index == 0 or line[index - 1] != "\\"):
            cells.append("".join(current))
            current = []
        else:
            current.append(character)
    cells.append("".join(current))
    if cells and not cells[0].strip():
        cells = cells[1:]
    if cells and not cells[-1].strip():
        cells = cells[:-1]
    return [cell.strip() for cell in cells]


def _split_block(text: str, line: int, section: tuple[int, ...], procedural: bool, start_index: int) -> list[Sentence]:
    result: list[Sentence] = []
    pattern = re.compile(r".+?[.!?](?=\s+[A-Z0-9`]|\s*$)|.+$", re.DOTALL)
    for match in pattern.finditer(text):
        raw = match.group()
        value = re.sub(r"\s+", " ", raw).strip()
        if not value:
            continue
        content_start = match.start() + len(raw) - len(raw.lstrip())
        sentence_line = line + text[:content_start].count("\n")
        result.append(Sentence(value, sentence_line, section, procedural, start_index + len(result)))
    return result


def parse_markdown(text: str, actions: set[str]) -> list[Sentence]:
    """Parse Markdown prose and list items into line-bound sentences."""
    sentences: list[Sentence] = []
    paragraph: list[str] = []
    paragraph_line = 0
    stack: list[tuple[int, int]] = [(0, 0)]
    next_id = 1
    section: tuple[int, ...] = (0,)
    fenced = False
    frontmatter = False

    def flush() -> None:
        nonlocal paragraph
        if paragraph:
            joined = "\n".join(paragraph)
            first = _words(joined)
            procedural = bool(first and first[0].casefold() in actions)
            sentences.extend(_split_block(joined, paragraph_line, section, procedural, len(sentences)))
            paragraph = []

    for number, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if number == 1 and stripped == "---":
            frontmatter = True
            continue
        if frontmatter:
            if stripped == "---":
                frontmatter = False
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            flush()
            fenced = not fenced
            continue
        if fenced:
            continue
        heading = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", raw)
        if heading:
            flush()
            level = len(heading.group(1))
            while len(stack) > 1 and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, next_id))
            next_id += 1
            section = tuple(identifier for _, identifier in stack)
            continue
        if re.match(r"^\s*\|.*\|\s*$", raw):
            flush()
            cells = _table_cells(raw.strip())
            if cells and all(TABLE_DELIMITER_CELL.match(cell) for cell in cells):
                continue
            for cell in cells:
                if not cell:
                    continue
                first = _words(cell)
                procedural = bool(first and (first[0].casefold() in actions or first[0].casefold() in CONDITION_WORDS))
                sentences.extend(_split_block(cell, number, section, procedural, len(sentences)))
            continue
        if not stripped or re.match(r"^\s{4}\S", raw):
            flush()
            continue
        cleaned, is_list = _strip_markdown_prefix(raw)
        if is_list:
            flush()
            first = _words(cleaned)
            procedural = bool(first and (first[0].casefold() in actions or first[0].casefold() in CONDITION_WORDS))
            sentences.extend(_split_block(cleaned, number, section, procedural, len(sentences)))
        else:
            if not paragraph:
                paragraph_line = number
            paragraph.append(cleaned)
    flush()
    return sentences


def _severity(profile: str, rule_id: str) -> str:
    if profile == "standard" and rule_id in STYLE_WARNINGS_STANDARD:
        return "warning"
    return "error"


def _diagnostic(sentence: Sentence, profile: str, rule_id: str, detail: str = "") -> dict[str, Any]:
    issue, fix = RULE_TEXT[rule_id]
    if detail:
        issue = f"{issue}: {detail}"
    return {
        "rule_id": rule_id,
        "severity": _severity(profile, rule_id),
        "line": sentence.line,
        "sentence": sentence.text,
        "issue": issue,
        "fix": fix,
    }


def _hazardous(lower: str, hazard: str) -> bool:
    """Return whether lower names the hazard as an action; an objectless stop is not one."""
    for match in re.finditer(rf"\b{re.escape(hazard)}\b", lower):
        if hazard != "stop":
            return True
        following = _words(lower[match.end() :])
        if following and following[0] not in OBJECTLESS_STOP_FOLLOWERS:
            return True
    return False


def collect_diagnostics(text: str, profile: str, glossary: dict[str, Any]) -> list[dict[str, Any]]:
    actions = DEFAULT_ACTIONS | {str(item).casefold() for item in glossary.get("action_verbs", [])}
    phrasal = DEFAULT_PHRASAL | {str(item).casefold() for item in glossary.get("phrasal_verbs", [])}
    hazards = DEFAULT_HAZARDS | {str(item).casefold() for item in glossary.get("hazardous_actions", [])}
    text = GAP_MARKER.sub(lambda match: " " * len(match.group()), text)
    sentences = parse_markdown(text, actions)
    diagnostics: list[dict[str, Any]] = []
    defined_abbreviations = {str(key) for key in glossary.get("abbreviations", {})}
    warned: set[int] = set()

    for sentence in sentences:
        raw_lower = sentence.text.casefold()
        plain = INLINE_CODE.sub("literal", sentence.text)
        lower = plain.casefold()
        words = [word.casefold() for word in _words(plain)]
        action_positions = [index for index, word in enumerate(words) if word in actions]
        if len(action_positions) > 1:
            between = " ".join(words[action_positions[0] : action_positions[-1] + 1])
            if re.search(r"\b(?:and|then|next)\b", between) or ";" in plain or "," in plain:
                diagnostics.append(_diagnostic(sentence, profile, "MTE-SENT-001"))

        for term in glossary.get("terms", []):
            preferred = str(term["preferred"])
            for variant in term.get("forbidden", []):
                if re.search(rf"(?<![\w-]){re.escape(str(variant))}(?![\w-])", plain, re.IGNORECASE):
                    diagnostics.append(_diagnostic(sentence, profile, "MTE-TERM-001", f"use '{preferred}'"))

        if PASSIVE.search(lower):
            diagnostics.append(_diagnostic(sentence, profile, "MTE-VOICE-001"))

        vague = bool(re.search(r"\bit\b", lower))
        for match in re.finditer(r"\b(this|that|these|those)\b(?:\s+([a-z]+))?", lower):
            if not match.group(2) or match.group(2) not in KNOWN_DEMONSTRATIVE_NOUNS:
                vague = True
        if vague:
            diagnostics.append(_diagnostic(sentence, profile, "MTE-REF-001"))

        for phrase in sorted(phrasal):
            if re.search(rf"(?<![\w-]){re.escape(phrase)}(?![\w-])", lower):
                diagnostics.append(_diagnostic(sentence, profile, "MTE-PHRASAL-001", phrase))

        condition_matches = list(re.finditer(r"\b(?:" + "|".join(CONDITION_WORDS) + r")\b", lower))
        if condition_matches and condition_matches[0].start() > 0 and not lower.startswith(("warning:", "caution:")):
            diagnostics.append(_diagnostic(sentence, profile, "MTE-COND-001"))

        if raw_lower.startswith(("warning:", "caution:")):
            warned.add(sentence.scopes[-1])
        elif any(_hazardous(raw_lower, hazard) for hazard in hazards):
            if not warned.intersection(sentence.scopes):
                diagnostics.append(_diagnostic(sentence, profile, "MTE-WARN-001"))

        definitions = set(re.findall(r"\(([A-Z][A-Z0-9-]{1,7})\)", plain))
        for abbreviation in re.findall(r"\b[A-Z][A-Z0-9-]{1,7}\b", plain):
            if (
                abbreviation not in {"CAUTION", "NOTE", "WARNING"}
                and abbreviation not in defined_abbreviations
                and abbreviation not in definitions
            ):
                diagnostics.append(_diagnostic(sentence, profile, "MTE-ABBR-001", abbreviation))
        defined_abbreviations.update(definitions)

        nominalizations = r"\b\w+(?:tion|sion|ment|ance|ence|ity|ness)\b"
        if re.search(nominalizations + r"(?:\s+of)?\s+" + nominalizations, lower):
            diagnostics.append(_diagnostic(sentence, profile, "MTE-NOM-001"))

        if profile == "strict":
            limit = 20 if sentence.procedural else 25
            if len(_words(plain)) > limit:
                diagnostics.append(_diagnostic(sentence, profile, "MTE-LEN-001", f"limit is {limit} words"))

    unique = {(item["rule_id"], item["line"], item["sentence"], item["issue"]): item for item in diagnostics}
    return sorted(unique.values(), key=lambda item: (item["line"], item["rule_id"], item["issue"]))

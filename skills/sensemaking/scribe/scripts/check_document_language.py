"""Apply deterministic MTE-1 language checks to a Markdown document."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

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
    section: str
    procedural: bool
    index: int


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", text)


def _strip_markdown_prefix(line: str) -> tuple[str, bool]:
    text = re.sub(r"^\s*>\s?", "", line)
    match = re.match(r"^\s*(?:[-+*]|\d+[.)])\s+(.*)$", text)
    return (match.group(1), True) if match else (text.strip(), False)


def _split_block(text: str, line: int, section: str, procedural: bool, start_index: int) -> list[Sentence]:
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
    section = "document"
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
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", raw)
        if heading:
            flush()
            section = heading.group(1)
            continue
        if not stripped or re.match(r"^\s*\|.*\|\s*$", raw) or re.match(r"^\s{4}\S", raw):
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


def collect_diagnostics(text: str, profile: str, glossary: dict[str, Any]) -> list[dict[str, Any]]:
    actions = DEFAULT_ACTIONS | {str(item).casefold() for item in glossary.get("action_verbs", [])}
    phrasal = DEFAULT_PHRASAL | {str(item).casefold() for item in glossary.get("phrasal_verbs", [])}
    hazards = DEFAULT_HAZARDS | {str(item).casefold() for item in glossary.get("hazardous_actions", [])}
    sentences = parse_markdown(text, actions)
    diagnostics: list[dict[str, Any]] = []
    defined_abbreviations = {str(key) for key in glossary.get("abbreviations", {})}
    prior_warnings: dict[str, int] = {}

    for sentence in sentences:
        lower = sentence.text.casefold()
        words = [word.casefold() for word in _words(sentence.text)]
        action_positions = [index for index, word in enumerate(words) if word in actions]
        if len(action_positions) > 1:
            between = " ".join(words[action_positions[0] : action_positions[-1] + 1])
            if re.search(r"\b(?:and|then|next)\b", between) or ";" in sentence.text or "," in sentence.text:
                diagnostics.append(_diagnostic(sentence, profile, "MTE-SENT-001"))

        for term in glossary.get("terms", []):
            preferred = str(term["preferred"])
            for variant in term.get("forbidden", []):
                if re.search(rf"(?<![\w-]){re.escape(str(variant))}(?![\w-])", sentence.text, re.IGNORECASE):
                    diagnostics.append(_diagnostic(sentence, profile, "MTE-TERM-001", f"use '{preferred}'"))

        if re.search(r"\b(?:am|is|are|was|were|be|been|being)\s+(?:\w+\s+){0,2}\w+(?:ed|en)\b", lower):
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

        if lower.startswith(("warning:", "caution:")):
            prior_warnings[sentence.section.casefold()] = sentence.index
        elif any(re.search(rf"\b{re.escape(hazard)}\b", lower) for hazard in hazards):
            if prior_warnings.get(sentence.section.casefold(), -1) >= sentence.index:
                prior_warnings.pop(sentence.section.casefold(), None)
            if sentence.section.casefold() not in prior_warnings:
                diagnostics.append(_diagnostic(sentence, profile, "MTE-WARN-001"))

        definitions = set(re.findall(r"\(([A-Z][A-Z0-9-]{1,7})\)", sentence.text))
        for abbreviation in re.findall(r"\b[A-Z][A-Z0-9-]{1,7}\b", sentence.text):
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
            if len(_words(sentence.text)) > limit:
                diagnostics.append(_diagnostic(sentence, profile, "MTE-LEN-001", f"limit is {limit} words"))

    unique = {(item["rule_id"], item["line"], item["sentence"], item["issue"]): item for item in diagnostics}
    return sorted(unique.values(), key=lambda item: (item["line"], item["rule_id"], item["issue"]))

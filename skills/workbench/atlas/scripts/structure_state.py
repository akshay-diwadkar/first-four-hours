#!/usr/bin/env python3
"""Validate a filesystem-native Map/Landmark/Satellite wiki without writing it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import string
import urllib.parse
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Iterable

from _diagnostic_contract import normalize_diagnostic, sorted_diagnostics

WIKI_ROOT = ".map"
MAP_PARENT = "<!-- ATLAS -->"
RESERVED_GUIDANCE_TEXT = ("<!--", "## Repository Knowledge")
LEGACY_STATE_ROOT = PurePosixPath(".agent", "knowledge")
LEGACY_STATE_MARKERS = (
    "KNOWLEDGE.md",
    "evidence-index.json",
    "relationships.json",
    "repo-map.json",
    "symbol-index.json",
    "symbols.json",
)
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
HTML_BLOCK_TAG_RE = re.compile(
    r"^ {0,3}</?(?:address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details|"
    r"dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|h[1-6]|head|header|"
    r"hr|html|iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|param|search|"
    r"section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul)(?:\s|/?>|$)",
    re.IGNORECASE,
)
HTML_RAW_OPEN_RE = re.compile(r"^ {0,3}<(script|pre|style|textarea)(?:\s|>|$)", re.IGNORECASE)
HTML_COMPLETE_TAG_RE = re.compile(
    r"^ {0,3}</?[A-Za-z][A-Za-z0-9-]*(?:\s+[^<>]*)?/?>\s*$",
    re.IGNORECASE,
)


@dataclass
class Page:
    path: PurePosixPath
    file: Path
    role: str
    parent: PurePosixPath | None
    content_sha256: str
    byte_count: int
    line_count: int
    links: list[str] = field(default_factory=list)
    link_cues: list[str] = field(default_factory=list)
    indexed_children: set[PurePosixPath] = field(default_factory=set)
    cross_links: set[PurePosixPath] = field(default_factory=set)
    source_links: set[PurePosixPath] = field(default_factory=set)
    map_entry: tuple[str, str] | None = None

    @property
    def depth(self) -> int:
        return max(1, len(self.path.parts) - 2)


@dataclass
class MarkdownScan:
    links: list[str]
    unsupported_html_anchor: bool = False
    cues: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ContainerLine:
    start: int
    end: int
    content: str
    container: tuple[int, bool]
    starts_container: bool


class _HtmlLinkDetector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.unsupported_anchor = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"a", "area"} and any(name.casefold() == "href" for name, _ in attrs):
            self.unsupported_anchor = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


def _read_page(path: Path) -> tuple[str, str, int, int]:
    payload = path.read_bytes()
    text = payload.decode("utf-8")
    return text, hashlib.sha256(payload).hexdigest(), len(payload), len(text.splitlines())


def _has_unsupported_html_anchor(text: str) -> bool:
    detector = _HtmlLinkDetector()
    detector.feed(text)
    detector.close()
    return detector.unsupported_anchor


def role_for(path: PurePosixPath) -> str | None:
    if len(path.parts) < 2 or path.parts[0] != WIKI_ROOT or path.suffix != ".md":
        return None
    return "landmark" if path.name == "LANDMARK.md" else "satellite"


def parent_for(
    path: PurePosixPath,
    role: str,
    landmarks: set[PurePosixPath] | None = None,
) -> PurePosixPath | None:
    if role == "satellite":
        return path.parent / "LANDMARK.md"
    if len(path.parts) == 3:
        return None
    candidates = landmarks or set()
    directory = path.parent.parent
    cluster_root = PurePosixPath(WIKI_ROOT, path.parts[1])
    while len(directory.parts) >= len(cluster_root.parts):
        candidate = directory / "LANDMARK.md"
        if candidate in candidates:
            return candidate
        if directory == cluster_root:
            break
        directory = directory.parent
    return cluster_root / "LANDMARK.md"


def _reference_destination(value: str) -> str | None:
    position = 0
    while position < len(value) and value[position].isspace():
        position += 1
    if position == len(value):
        return None
    if value[position] == "<":
        end = position + 1
        escaped = False
        while end < len(value):
            character = value[end]
            if character == ">" and not escaped:
                return _unescape_destination(value[position + 1 : end])
            escaped = character == "\\" and not escaped
            if character != "\\":
                escaped = False
            end += 1
        return None

    result: list[str] = []
    depth = 0
    escaped = False
    while position < len(value):
        character = value[position]
        if escaped:
            result.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "(":
            depth += 1
            result.append(character)
        elif character == ")":
            if depth == 0:
                return None
            depth -= 1
            result.append(character)
        elif character.isspace() and depth == 0:
            return "".join(result) or None
        else:
            result.append(character)
        position += 1
    return "".join(result) if result and depth == 0 else None


def _escaped_character(text: str, position: int) -> bool:
    slashes = 0
    while position > slashes and text[position - slashes - 1] == "\\":
        slashes += 1
    return slashes % 2 == 1


def _strip_code_spans(text: str) -> str:
    result = list(text)
    position = 0
    while position < len(text):
        if text[position] != "`" or _escaped_character(text, position):
            position += 1
            continue
        end = position
        while end < len(text) and text[end] == "`":
            end += 1
        run = end - position
        search = end
        closing: int | None = None
        while search < len(text):
            candidate = text.find("`" * run, search)
            if candidate < 0:
                break
            before_same = candidate > 0 and text[candidate - 1] == "`"
            after_same = candidate + run < len(text) and text[candidate + run] == "`"
            if not before_same and not after_same and not _escaped_character(text, candidate):
                closing = candidate
                break
            search = candidate + run
        if closing is None:
            position = end
            continue
        for index in range(position, closing + run):
            if result[index] != "\n":
                result[index] = " "
        position = closing + run
    return "".join(result)


def _reference_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _unescape_destination(value: str) -> str:
    result: list[str] = []
    position = 0
    while position < len(value):
        if value[position] == "\\" and position + 1 < len(value) and value[position + 1] in string.punctuation:
            position += 1
        result.append(value[position])
        position += 1
    return "".join(result)


def _blank(result: list[str], start: int, end: int) -> None:
    for index in range(start, end):
        if result[index] != "\n":
            result[index] = " "


def _block_content(line: str) -> str:
    return _quote_content(line)[0]


def _quote_content(line: str) -> tuple[str, int]:
    content = line
    depth = 0
    while (quote := re.match(r"^ {0,3}>[ \t]?", content)) is not None:
        content = content[quote.end() :]
        depth += 1
    return content, depth


def _container_lines(text: str) -> list[ContainerLine]:
    lines: list[ContainerLine] = []
    list_indent: int | None = None
    previous_container = (0, False)
    offset = 0
    for line_with_end in text.splitlines(keepends=True):
        line = line_with_end.rstrip("\r\n")
        content, quote_depth = _quote_content(line)
        list_item = re.match(r"^ {0,3}(?:[*+-]|\d{1,9}[.)])([ \t]+)", content)
        if list_item is not None:
            list_indent = list_item.end()
            content = content[list_indent:]
        elif list_indent is not None and content.strip():
            leading = len(content) - len(content.lstrip(" "))
            if leading >= list_indent:
                content = content[list_indent:]
            else:
                list_indent = None
        container = (quote_depth, list_indent is not None)
        end = offset + len(line_with_end)
        lines.append(ContainerLine(offset, end, content, container, list_item is not None or container != previous_container))
        previous_container = container
        offset = end
    return lines


def _mask_blocks(text: str) -> tuple[str, bool]:
    """Mask Markdown regions where link syntax is literal, preserving offsets."""
    result = list(text)
    fence: tuple[str, int] | None = None
    raw_until: str | None = None
    html_block = False
    indented = False
    previous_blank = True
    list_indent: int | None = None
    html_start: int | None = None
    html_ranges: list[tuple[int, int]] = []
    offset = 0
    for line_with_end in text.splitlines(keepends=True):
        line = line_with_end.rstrip("\r\n")
        content = _block_content(line)
        list_item = re.match(r"^ {0,3}(?:[*+-]|\d{1,9}[.)])([ \t]+)", content)
        if list_item is not None:
            list_indent = list_item.end()
            content = content[list_indent:]
        elif list_indent is not None and content.strip():
            leading = len(content) - len(content.lstrip(" "))
            if leading >= list_indent:
                content = content[list_indent:]
            else:
                list_indent = None
        fence_content = content
        end = offset + len(line_with_end)
        marker = FENCE_RE.match(fence_content)
        if marker and fence is None:
            run, remainder = marker.groups()
            if run[0] == "`" and "`" in remainder:
                marker = None
            else:
                fence = (run[0], len(run))
                _blank(result, offset, end)
                offset = end
                previous_blank = False
                continue
        elif marker and fence is not None:
            run, remainder = marker.groups()
            if run[0] == fence[0] and len(run) >= fence[1] and not remainder.strip():
                fence = None
            _blank(result, offset, end)
            offset = end
            previous_blank = False
            continue
        if fence is not None:
            _blank(result, offset, end)
            offset = end
            previous_blank = False
            continue

        stripped = content.lstrip()
        if raw_until is not None:
            _blank(result, offset, end)
            if raw_until.casefold() in content.casefold():
                raw_until = None
                if html_start is not None:
                    html_ranges.append((html_start, end))
                    html_start = None
            offset = end
            previous_blank = not stripped
            continue
        if html_block:
            if stripped:
                _blank(result, offset, end)
                offset = end
                previous_blank = False
                continue
            html_block = False
            if html_start is not None:
                html_ranges.append((html_start, offset))
                html_start = None
        raw_match = HTML_RAW_OPEN_RE.match(content)
        if raw_match:
            html_start = offset
            raw_until = f"</{raw_match.group(1)}>"
            _blank(result, offset, end)
            if raw_until.casefold() in content.casefold()[raw_match.end() :]:
                raw_until = None
                html_ranges.append((html_start, end))
                html_start = None
            offset = end
            previous_blank = not stripped
            continue
        if stripped.startswith(("<!--", "<?", "<![CDATA[")):
            html_start = offset
            terminator = "-->" if stripped.startswith("<!--") else "?>" if stripped.startswith("<?") else "]]>"
            _blank(result, offset, end)
            if terminator not in stripped:
                raw_until = terminator
            else:
                html_ranges.append((html_start, end))
                html_start = None
            offset = end
            previous_blank = not stripped
            continue
        if re.match(r"^ {0,3}<![A-Z]", content):
            html_start = offset
            _blank(result, offset, end)
            if ">" not in content:
                raw_until = ">"
            else:
                html_ranges.append((html_start, end))
                html_start = None
            offset = end
            previous_blank = not stripped
            continue
        if HTML_BLOCK_TAG_RE.match(content) or (previous_blank and HTML_COMPLETE_TAG_RE.match(content)):
            html_start = offset
            html_block = True
            _blank(result, offset, end)
            offset = end
            previous_blank = False
            continue

        starts_indented = content.startswith("\t") or content.startswith("    ")
        if starts_indented and (indented or previous_blank):
            indented = True
            _blank(result, offset, end)
            offset = end
            previous_blank = False
            continue
        if indented and not stripped:
            _blank(result, offset, end)
            offset = end
            previous_blank = True
            continue
        indented = False
        previous_blank = not stripped
        offset = end
    if html_start is not None:
        html_ranges.append((html_start, len(text)))
    unsupported = any(_has_unsupported_html_anchor(text[start:end]) for start, end in html_ranges)
    return "".join(result), unsupported


def _mask_inline_html(text: str) -> tuple[str, bool]:
    result = list(text)
    unsupported = False
    position = 0
    while position < len(text):
        if text.startswith("<!--", position):
            end = text.find("-->", position + 4)
            end = len(text) if end < 0 else end + 3
            _blank(result, position, end)
            position = end
            continue
        if text[position] != "<" or _escaped_character(text, position):
            position += 1
            continue
        prefix = text[:position].rstrip()
        if prefix.endswith("(") and prefix[:-1].rstrip().endswith("]"):
            position += 1
            continue
        if not re.match(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s|/?>)", text[position:]):
            position += 1
            continue
        quote: str | None = None
        end = position + 1
        closing: int | None = None
        while end < len(text):
            character = text[end]
            if character == "\n" and quote is None and end + 1 < len(text) and text[end + 1] == "\n":
                break
            if quote is not None:
                if character == quote and not _escaped_character(text, end):
                    quote = None
            elif character in {'"', "'"}:
                quote = character
            elif character == ">":
                end += 1
                closing = end
                break
            end += 1
        if closing is None:
            position += 1
            continue
        segment = text[position:closing]
        unsupported = unsupported or _has_unsupported_html_anchor(segment)
        _blank(result, position, closing)
        position = closing
    return "".join(result), unsupported


def _bracket(text: str, position: int) -> tuple[str, int] | None:
    if position >= len(text) or text[position] != "[":
        return None
    depth = 1
    cursor = position + 1
    while cursor < len(text):
        character = text[cursor]
        if character == "\n" and cursor + 1 < len(text) and text[cursor + 1] == "\n":
            return None
        if character == "[" and not _escaped_character(text, cursor):
            depth += 1
        elif character == "]" and not _escaped_character(text, cursor):
            depth -= 1
            if depth == 0:
                return text[position + 1 : cursor], cursor + 1
        cursor += 1
    return None


def _link_whitespace(text: str, position: int) -> int | None:
    cursor = position
    line_endings = 0
    while cursor < len(text) and text[cursor].isspace():
        if text[cursor] == "\n":
            line_endings += 1
            if line_endings > 1:
                return None
        cursor += 1
    return cursor


def _inline_destination(text: str, position: int) -> tuple[str, int] | None:
    cursor = _link_whitespace(text, position)
    if cursor is None or cursor >= len(text):
        return None
    if text[cursor] == "<":
        start = cursor + 1
        cursor = start
        while cursor < len(text) and text[cursor] != "\n":
            if text[cursor] == ">" and not _escaped_character(text, cursor):
                target = text[start:cursor]
                cursor += 1
                break
            cursor += 1
        else:
            return None
    else:
        start = cursor
        depth = 0
        while cursor < len(text):
            character = text[cursor]
            if character == "\\":
                cursor += 2
                continue
            if character == "(":
                depth += 1
            elif character == ")":
                if depth == 0:
                    break
                depth -= 1
            elif character.isspace() and depth == 0:
                break
            cursor += 1
        if depth:
            return None
        target = text[start:cursor]

    whitespace_start = cursor
    spaced = _link_whitespace(text, cursor)
    if spaced is None:
        return None
    cursor = spaced
    if cursor < len(text) and text[cursor] in {'"', "'", "("} and cursor > whitespace_start:
        opener = text[cursor]
        closer = ")" if opener == "(" else opener
        cursor += 1
        while cursor < len(text):
            if text[cursor] == closer and not _escaped_character(text, cursor):
                cursor += 1
                break
            if text[cursor] == "\n" and cursor + 1 < len(text) and text[cursor + 1] == "\n":
                return None
            cursor += 1
        else:
            return None
        spaced = _link_whitespace(text, cursor)
        if spaced is None:
            return None
        cursor = spaced
    if cursor >= len(text) or text[cursor] != ")":
        return None
    return _unescape_destination(target), cursor + 1


def _mask_inline_destinations(text: str) -> str:
    result = list(text)
    position = 0
    while position < len(text):
        if text[position] != "[" or _escaped_character(text, position):
            position += 1
            continue
        label = _bracket(text, position)
        if label is None:
            position += 1
            continue
        after_label = label[1]
        if after_label < len(text) and text[after_label] == "(":
            destination = _inline_destination(text, after_label + 1)
            if destination is not None:
                _blank(result, after_label, destination[1])
                position = destination[1]
                continue
        position = after_label
    return "".join(result)


def _line_ends_block(content: str, setext_subject: str | None = None) -> bool:
    stripped = content.strip()
    if re.match(r"^#{1,6}(?:\s|$)", stripped):
        return True
    compact = re.sub(r"[ \t]", "", stripped)
    if len(compact) < 3 or len(set(compact)) != 1:
        return False
    if compact[0] in "*-_":
        return True
    if compact[0] != "=" or not setext_subject:
        return False
    subject = setext_subject.strip()
    return bool(subject) and not re.match(
        r"^(?:#{1,6}(?:\s|$)|(?:[*+-]|\d{1,9}[.)])\s|`{3,}|~{3,}|<)",
        subject,
    )


def _reference_title_line(value: str) -> bool:
    indent = len(value) - len(value.lstrip(" "))
    if indent > 3:
        return False
    text = value.strip()
    if len(text) < 2 or text[0] not in {'"', "'", "("}:
        return False
    closer = ")" if text[0] == "(" else text[0]
    position = 1
    while position < len(text):
        if text[position] == closer and not _escaped_character(text, position):
            return not text[position + 1 :].strip()
        position += 1
    return False


def _reference_definitions(text: str) -> tuple[dict[str, str], str]:
    definitions: dict[str, str] = {}
    result = list(text)
    lines = _container_lines(text)
    position = 0
    previous_definition = False
    while position < len(lines):
        current = lines[position]
        line = current.content
        indent = len(line) - len(line.lstrip(" "))
        can_start = (
            position == 0
            or not lines[position - 1].content.strip()
            or previous_definition
            or current.starts_container
            or _line_ends_block(
                lines[position - 1].content,
                lines[position - 2].content if position >= 2 else None,
            )
        )
        found_definition = False
        if can_start and indent <= 3 and indent < len(line) and line[indent] == "[":
            label = _bracket(line, indent)
            if label is not None and label[1] < len(line) and line[label[1]] == ":":
                remainder = line[label[1] + 1 :]
                target = _reference_destination(remainder)
                definition_end = current.end
                consumed = position
                if target is None and not remainder.strip() and position + 1 < len(lines):
                    next_line = lines[position + 1]
                    next_indent = len(next_line.content) - len(next_line.content.lstrip(" "))
                    if next_line.container == current.container and next_indent <= 3:
                        target = _reference_destination(next_line.content)
                        if target is not None:
                            definition_end = next_line.end
                            consumed = position + 1
                if target is not None:
                    title_position = consumed + 1
                    if (
                        title_position < len(lines)
                        and lines[title_position].container == current.container
                        and _reference_title_line(lines[title_position].content)
                    ):
                        definition_end = lines[title_position].end
                        consumed = title_position
                    definitions.setdefault(_reference_key(label[0]), target)
                    _blank(result, current.start, definition_end)
                    found_definition = True
                    position = consumed
        previous_definition = found_definition
        position += 1
    return definitions, "".join(result)


def _label_contains_link(text: str, definitions: dict[str, str]) -> bool:
    position = 0
    while position < len(text):
        if text[position] != "[" or _escaped_character(text, position):
            position += 1
            continue
        label = _bracket(text, position)
        if label is None:
            position += 1
            continue
        label_text, after_label = label
        is_image = position > 0 and text[position - 1] == "!" and not _escaped_character(text, position - 1)
        if after_label < len(text) and text[after_label] == "(":
            parsed = _inline_destination(text, after_label + 1)
            if parsed is not None:
                if not is_image:
                    return True
                position = parsed[1]
                continue
        if after_label < len(text) and text[after_label] == "[":
            reference = _bracket(text, after_label)
            if reference is not None:
                key = _reference_key(reference[0] or label_text)
                if not is_image and key in definitions:
                    return True
                position = reference[1]
                continue
        if not is_image and _reference_key(label_text) in definitions:
            return True
        position = after_label
    return False


def _scan_markdown(text: str) -> MarkdownScan:
    body, block_anchor = _mask_blocks(text)
    body = _strip_code_spans(body)
    _, reference_visibility = _reference_definitions(body)
    html_visibility = _mask_inline_destinations(reference_visibility)
    _, inline_anchor = _mask_inline_html(html_visibility)
    body, _ = _mask_inline_html(body)
    definitions, body = _reference_definitions(body)
    links: list[str] = []
    starts: list[int] = []
    position = 0
    while position < len(body):
        if body[position] != "[" or _escaped_character(body, position):
            position += 1
            continue
        label = _bracket(body, position)
        if label is None:
            position += 1
            continue
        label_text, after_label = label
        if _label_contains_link(label_text, definitions):
            position += 1
            continue
        if after_label < len(body) and body[after_label] == ":":
            position = after_label + 1
            continue
        is_image = position > 0 and body[position - 1] == "!" and not _escaped_character(body, position - 1)
        if after_label < len(body) and body[after_label] == "(":
            parsed = _inline_destination(body, after_label + 1)
            if parsed is not None:
                if not is_image:
                    links.append(parsed[0])
                    starts.append(position)
                position = parsed[1]
                continue
        if after_label < len(body) and body[after_label] == "[":
            reference = _bracket(body, after_label)
            if reference is not None:
                key = _reference_key(reference[0] or label_text)
                if not is_image and key in definitions:
                    links.append(definitions[key])
                    starts.append(position)
                position = reference[1]
                continue
        key = _reference_key(label_text)
        if not is_image and key in definitions:
            links.append(definitions[key])
            starts.append(position)
        position = after_label
    cues: list[str] = []
    for index, start in enumerate(starts):
        line_end = text.find("\n", start)
        end = len(text) if line_end < 0 else line_end
        if index + 1 < len(starts) and starts[index + 1] < end:
            end = starts[index + 1]
        cues.append(text[start:end])
    return MarkdownScan(links, block_anchor or inline_anchor, cues)


ATX_HEADING_RE = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+(.*?))?[ \t]*$")
CLOSING_HASHES_RE = re.compile(r"(?:^|[ \t]+)#+$")
INLINE_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
CODE_SPAN_RE = re.compile(r"(`+)(.+?)(?<!`)\1(?!`)", re.DOTALL)
SYMBOL_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")


def _render_heading(content: str) -> str:
    content = INLINE_LINK_RE.sub(lambda match: match.group(1), content)
    rendered: list[str] = []
    position = 0
    for match in CODE_SPAN_RE.finditer(content):
        rendered.append(_strip_emphasis(content[position : match.start()]))
        rendered.append(match.group(2))
        position = match.end()
    rendered.append(_strip_emphasis(content[position:]))
    return "".join(rendered)


def _strip_emphasis(text: str) -> str:
    return "".join(
        character
        for index, character in enumerate(text)
        if character != "_"
        or 0 < index < len(text) - 1
        and text[index - 1].isalnum()
        and text[index + 1].isalnum()
    )


def _heading_slugs(text: str) -> set[str]:
    # GitHub's slugger: a repeated slug takes the next unused numeric suffix.
    issued: dict[str, int] = {}
    for line in _mask_blocks(text)[0].splitlines():
        match = ATX_HEADING_RE.match(line)
        if match is None:
            continue
        content = CLOSING_HASHES_RE.sub("", (match.group(1) or "").strip()).strip()
        rendered = _render_heading(content).lower()
        slug = "".join(
            character for character in rendered if character.isalnum() or character in "-_ "
        ).replace(" ", "-")
        result = slug
        while result in issued:
            issued[slug] += 1
            result = f"{slug}-{issued[slug]}"
        issued[result] = 0
    return set(issued)


H1_RE = re.compile(r"^ {0,3}#(?:[ \t]+(.*?))?[ \t]*$")
BLOCK_START_RE = re.compile(
    r"^(?:\t| {4}| {0,3}(?:[*+-](?:[ \t]|$)|\d{1,9}[.)](?:[ \t]|$)|#|>|\||`{3}|~{3}"
    r"|=+[ \t]*$|-+[ \t]*$|(?:[*_][ \t]*){3,}$))"
)
UNSAFE_CLUSTER_RE = re.compile(r"[\s()<>\[\]#%?\\]")


def _landmark_entry(text: str) -> tuple[str, str] | str:
    """Return a top-level Landmark's Map title and cue, or why it cannot be listed."""
    lines = text.splitlines()
    position = 0
    while position < len(lines) and not lines[position].strip():
        position += 1
    heading = H1_RE.match(lines[position]) if position < len(lines) else None
    title = CLOSING_HASHES_RE.sub("", (heading.group(1) or "").strip()).strip() if heading else ""
    if not title:
        return "it does not open with a `# Title` line"
    position += 1
    while position < len(lines) and not lines[position].strip():
        position += 1
    paragraph: list[str] = []
    while position < len(lines) and lines[position].strip():
        paragraph.append(lines[position])
        position += 1
    if not paragraph:
        return "it has no opening paragraph after its title"
    if any(BLOCK_START_RE.match(line) for line in paragraph):
        return "its opening paragraph must be plain text, not a list, heading, quote, table, fence, or indented block"
    cue = " ".join(line.strip() for line in paragraph)
    for value in (title, cue):
        visible = _strip_code_spans(value)
        if any(token in visible for token in ("[", "]", "<", "://")):
            return "its title or opening paragraph holds a link, image, HTML, or URL outside code spans"
        if any(token in value for token in RESERVED_GUIDANCE_TEXT):
            return "its title or opening paragraph holds `<!--` or `## Repository Knowledge`, which root guidance reserves"
    return title, cue


def _cue_symbols(cue: str) -> list[str]:
    return [
        content
        for match in CODE_SPAN_RE.finditer(cue)
        if SYMBOL_RE.fullmatch(content := match.group(2).strip())
    ]


def _contains_word(text: str, symbol: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(symbol)}(?![A-Za-z0-9_])", text) is not None


def _path_collision_groups(paths: Iterable[PurePosixPath]) -> list[list[PurePosixPath]]:
    groups: dict[str, list[PurePosixPath]] = {}
    for path in paths:
        groups.setdefault(path.as_posix().casefold(), []).append(path)
    return [values for values in groups.values() if len(values) > 1]


def _resolve(page: PurePosixPath, target: str) -> tuple[str, PurePosixPath | None]:
    value = target.strip()
    if not value:
        return "unsafe", None
    if value.startswith("#"):
        return "fragment", page
    path_text = value.split("#", 1)[0]
    if (
        not path_text
        or "://" in path_text
        or path_text.startswith(("/", "\\"))
        or SCHEME_RE.match(path_text)
        or "\\" in path_text
        or "?" in path_text
        or "%" in path_text
    ):
        return "unsafe", None
    parts: list[str] = []
    for part in (page.parent / PurePosixPath(path_text)).parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return "unsafe", None
            parts.pop()
        else:
            parts.append(part)
    return "path", PurePosixPath(*parts)


def _disk_state(root: Path, relative: PurePosixPath) -> str:
    current = root
    for part in relative.parts:
        try:
            names = [entry.name for entry in os.scandir(current)]
        except OSError:
            return "missing"
        if part in names:
            current /= part
            continue
        if part.casefold() in {name.casefold() for name in names}:
            return "case_mismatch"
        return "missing"
    try:
        if not current.resolve().is_relative_to(root.resolve()):
            return "outside"
    except OSError:
        return "missing"
    return "file" if current.is_file() else "directory" if current.is_dir() else "missing"


def _diagnostic(code: str, message: str, path: PurePosixPath, action: str) -> dict[str, object]:
    category = (
        "unsafe_state"
        if any(token in code for token in ("unsafe", "outside", "case_collision", "case_mismatch"))
        else "missing_evidence"
        if any(token in code for token in ("missing", "broken", "unreachable"))
        else "contract_contradiction"
    )
    return normalize_diagnostic(
        {
            "code": code,
            "category": category,
            "severity": "error",
            "message": message,
            "required_action": action,
            "valid_repairs": [action],
            "supporting_evidence": [path.as_posix()],
            "path": path.as_posix(),
        },
        skill="atlas",
        phase="run",
        artifact="wiki-structure",
        path=path.as_posix(),
    )


def _legacy_state_diagnostics(root: Path) -> list[dict[str, object]]:
    matches = [
        LEGACY_STATE_ROOT / name
        for name in LEGACY_STATE_MARKERS
        if (root / LEGACY_STATE_ROOT / name).is_file()
    ]
    if not matches:
        return []
    action = (
        "Delete only the reported legacy files; leave any other .agent/knowledge content in place "
        "and report it to the user for review; then author `.map/` from current source and run "
        "`setup-guidance`, without translating legacy artifacts into wiki authority."
    )
    rendered = ", ".join(path.as_posix() for path in matches)
    return [
        normalize_diagnostic(
            {
                "code": "map.legacy_generated_state",
                "category": "contract_contradiction",
                "severity": "error",
                "message": f"Legacy generated repository-intelligence state remains: {rendered}.",
                "required_action": action,
                "valid_repairs": [action],
                "supporting_evidence": [path.as_posix() for path in matches],
                "path": LEGACY_STATE_ROOT.as_posix(),
            },
            skill="atlas",
            phase="run",
            artifact="wiki-structure",
            path=LEGACY_STATE_ROOT.as_posix(),
        )
    ]


def _wiki_candidates(root: Path, wiki_dir: Path) -> tuple[list[Path], list[dict[str, object]]]:
    candidates: list[Path] = []
    diagnostics: list[dict[str, object]] = []
    pending: list[tuple[Path, frozenset[Path]]] = [(wiki_dir, frozenset())]
    while pending:
        directory, ancestors = pending.pop()
        try:
            resolved_directory = directory.resolve(strict=True)
            entries = sorted(directory.iterdir(), key=lambda item: item.name)
        except (OSError, RuntimeError):
            continue
        if resolved_directory in ancestors:
            continue
        descendants = ancestors | {resolved_directory}
        for path in reversed(entries):
            relative = PurePosixPath(path.relative_to(root).as_posix())
            state = _disk_state(root, relative)
            try:
                is_directory = path.is_dir()
                is_markdown = path.is_file() and path.suffix.casefold() == ".md"
            except OSError:
                continue
            if state == "outside" and (is_directory or is_markdown):
                diagnostics.append(_diagnostic(
                    "map.path_outside_repository",
                    f"Wiki path resolves outside the repository: {relative.as_posix()}.",
                    relative,
                    "Replace the external symlink with a repository-contained wiki path.",
                ))
                continue
            if is_directory:
                pending.append((path, descendants))
            elif is_markdown:
                candidates.append(path)
    return candidates, diagnostics


def _discover(root: Path) -> tuple[dict[PurePosixPath, Page], list[dict[str, object]]]:
    pages: dict[PurePosixPath, Page] = {}
    diagnostics = _legacy_state_diagnostics(root)
    candidates: list[Path] = []
    for entry in root.iterdir():
        if entry.name.casefold() == WIKI_ROOT and entry.name != WIKI_ROOT:
            diagnostics.append(_diagnostic(
                "map.path_case_mismatch",
                f"Wiki directory must be exactly .map, not {entry.name}.",
                PurePosixPath(entry.name),
                "Rename the wiki directory to .map with exact casing.",
            ))
    wiki_dir = root / WIKI_ROOT
    wiki_state = _disk_state(root, PurePosixPath(WIKI_ROOT))
    if wiki_state == "outside":
        diagnostics.append(_diagnostic(
            "map.path_outside_repository",
            "Wiki directory .map resolves outside the repository.",
            PurePosixPath(WIKI_ROOT),
            "Replace .map with a repository-contained directory and contained wiki pages.",
        ))
    elif wiki_dir.is_dir():
        wiki_candidates, wiki_diagnostics = _wiki_candidates(root, wiki_dir)
        candidates.extend(wiki_candidates)
        diagnostics.extend(wiki_diagnostics)

    safe_candidates: list[Path] = []
    relative_paths: list[PurePosixPath] = []
    for path in candidates:
        relative = PurePosixPath(path.relative_to(root).as_posix())
        if _disk_state(root, relative) == "outside":
            diagnostics.append(_diagnostic(
                "map.path_outside_repository",
                f"Wiki page resolves outside the repository: {relative.as_posix()}.",
                relative,
                "Replace the external symlink with a repository-contained Markdown page.",
            ))
            continue
        safe_candidates.append(path)
        relative_paths.append(relative)
    for group in _path_collision_groups(relative_paths):
        rendered = ", ".join(path.as_posix() for path in sorted(group))
        diagnostics.append(_diagnostic(
            "map.path_case_collision",
            f"Wiki paths collide under portable case rules: {rendered}.",
            min(group),
            "Rename the colliding pages so every case-folded path is unique.",
        ))

    for path, relative in sorted(zip(safe_candidates, relative_paths), key=lambda item: item[1].as_posix()):
        role = role_for(relative)
        if role is None or path.suffix != ".md":
            diagnostics.append(_diagnostic(
                "map.layout_unsupported",
                f"Markdown page has an unsupported wiki path: {relative.as_posix()}.",
                relative,
                "Move the page to a path under .map using the documented role layout.",
            ))
            continue
        if relative == PurePosixPath(WIKI_ROOT, "LANDMARK.md") or (
            role == "satellite" and len(relative.parts) < 3
        ):
            diagnostics.append(_diagnostic(
                "map.layout_unsupported",
                f"Wiki page has no valid cluster parent: {relative.as_posix()}.",
                relative,
                "Place the page inside a named .map/<cluster>/ directory.",
            ))
        text, content_sha256, byte_count, line_count = _read_page(path)
        if text.startswith("---\n") or text.startswith("---\r\n"):
            diagnostics.append(_diagnostic(
                "map.page_metadata_forbidden",
                f"Wiki role and identity must come from the path, not page metadata: {relative.as_posix()}.",
                relative,
                "Remove the page front matter and retain the path-derived role.",
            ))
        map_entry: tuple[str, str] | None = None
        if role == "landmark" and len(relative.parts) == 3:
            entry = (
                "its cluster directory name cannot appear in a Map link"
                if UNSAFE_CLUSTER_RE.search(relative.parts[1])
                else _landmark_entry(text)
            )
            if isinstance(entry, str):
                diagnostics.append(_diagnostic(
                    "map.landmark_entry_invalid",
                    f"Top-level Landmark {relative.as_posix()} cannot be listed in the Map: {entry}.",
                    relative,
                    "Open the Landmark with one `# Title` line, then a blank line and a plain opening paragraph "
                    "that says when to follow it, keeping links, HTML, and URLs inside code spans or after that "
                    "paragraph and `<!--` and `## Repository Knowledge` out of both, and name its cluster directory "
                    "without whitespace or ()<>[]#%?\\; then rerun `run` and `setup-guidance`.",
                ))
            else:
                map_entry = entry
        markdown = _scan_markdown(text)
        if markdown.unsupported_html_anchor:
            diagnostics.append(_diagnostic(
                "map.html_anchor_unsupported",
                f"Wiki page uses an HTML anchor for navigation: {relative.as_posix()}.",
                relative,
                "Replace every HTML anchor href with an ordinary inline or reference-style Markdown link.",
            ))
        pages[relative] = Page(
            path=relative,
            file=path,
            role=role,
            parent=None,
            content_sha256=content_sha256,
            byte_count=byte_count,
            line_count=line_count,
            links=markdown.links,
            link_cues=markdown.cues,
            map_entry=map_entry,
        )
    landmarks = {path for path, page in pages.items() if page.role == "landmark"}
    for page in pages.values():
        page.parent = parent_for(page.path, page.role, landmarks)
    if not any(page.role == "landmark" and page.parent is None for page in pages.values()):
        diagnostics.append(_diagnostic(
            "map.landmark_missing",
            "The wiki has no top-level Landmark (.map/<cluster>/LANDMARK.md), so there is no Map to write.",
            PurePosixPath(WIKI_ROOT),
            "Create at least one top-level Landmark under .map/, then rerun `run` and `setup-guidance`.",
        ))
    return pages, diagnostics


def analyze(
    root: Path,
) -> tuple[dict[str, object], dict[PurePosixPath, Page], list[dict[str, object]]]:
    pages, diagnostics = _discover(root)
    wiki_lookup = {path.as_posix().casefold(): path for path in pages}
    children: dict[PurePosixPath, set[PurePosixPath]] = {path: set() for path in pages}

    for page in pages.values():
        if page.parent is not None:
            if page.parent in pages:
                children[page.parent].add(page.path)
            else:
                diagnostics.append(_diagnostic(
                    "map.parent_missing",
                    f"Structural parent {page.parent.as_posix()} is missing for {page.path.as_posix()}.",
                    page.path,
                    f"Create {page.parent.as_posix()} or move the child beneath an existing Landmark.",
                ))

    target_texts: dict[PurePosixPath, str] = {}
    target_slugs: dict[PurePosixPath, set[str]] = {}

    def target_text(resolved: PurePosixPath) -> str:
        if resolved not in target_texts:
            target_texts[resolved] = (root / resolved).read_text(encoding="utf-8", errors="replace")
        return target_texts[resolved]

    for page in pages.values():
        for target, cue in zip(page.links, page.link_cues):
            state, resolved = _resolve(page.path, target)
            if state == "fragment":
                continue
            if state == "unsafe" or resolved is None:
                diagnostics.append(_diagnostic(
                    "map.link_unsafe",
                    f"Link target is not a safe repository-relative path in {page.path.as_posix()}: {target}.",
                    page.path,
                    "Replace the link with a page-relative literal path contained by the repository.",
                ))
                continue
            actual_wiki = wiki_lookup.get(resolved.as_posix().casefold())
            if actual_wiki is not None:
                if actual_wiki != resolved:
                    diagnostics.append(_diagnostic(
                        "map.link_case_mismatch",
                        f"Link casing does not match {actual_wiki.as_posix()} in {page.path.as_posix()}.",
                        page.path,
                        f"Change the link target to {actual_wiki.as_posix()} with exact casing.",
                    ))
                    continue
                if resolved in children.get(page.path, set()):
                    page.indexed_children.add(resolved)
                else:
                    page.cross_links.add(resolved)
                continue

            looks_like_wiki = (
                bool(resolved.parts)
                and resolved.parts[0] == WIKI_ROOT
                and resolved.suffix.casefold() == ".md"
            )
            if page.role == "landmark" and not looks_like_wiki:
                diagnostics.append(_diagnostic(
                    "map.source_link_forbidden",
                    f"{page.role.title()} page links directly to a repository location: {page.path.as_posix()} -> {resolved.as_posix()}.",
                    page.path,
                    "Move durable source orientation into a cohesive Satellite and route to it from this index.",
                ))
                continue
            disk_state = _disk_state(root, resolved)
            if disk_state == "case_mismatch":
                diagnostics.append(_diagnostic(
                    "map.link_case_mismatch",
                    f"Link casing does not match the repository path in {page.path.as_posix()}: {target}.",
                    page.path,
                    "Repair the link to use the target's exact repository-relative casing.",
                ))
            elif disk_state == "outside":
                diagnostics.append(_diagnostic(
                    "map.link_unsafe",
                    f"Link target resolves outside the repository in {page.path.as_posix()}: {target}.",
                    page.path,
                    "Replace the link with a non-escaping repository-contained target.",
                ))
            elif disk_state == "directory":
                diagnostics.append(_diagnostic(
                    "map.source_link_directory_unsupported",
                    f"Satellite source link must name a regular file, not a directory: {page.path.as_posix()} -> {resolved.as_posix()}.",
                    page.path,
                    "Replace the directory link with links to the productive files inside it.",
                ))
            elif disk_state != "file":
                diagnostics.append(_diagnostic(
                    "map.link_broken",
                    f"Link target does not resolve to a repository file in {page.path.as_posix()}: {target}.",
                    page.path,
                    "Repair or remove the stale link after the rename, promotion, collapse, or deletion.",
                ))
            else:
                page.source_links.add(resolved)
                if resolved.suffix.casefold() == ".md":
                    fragment = target.strip().partition("#")[2]
                    if fragment:
                        if resolved not in target_slugs:
                            target_slugs[resolved] = _heading_slugs(target_text(resolved))
                        if urllib.parse.unquote(fragment).casefold() not in target_slugs[resolved]:
                            diagnostics.append(_diagnostic(
                                "map.link_fragment_missing",
                                f"Link fragment #{fragment} matches no heading in {resolved.as_posix()} from {page.path.as_posix()}.",
                                page.path,
                                "Point the fragment at an existing ATX heading's GitHub-style slug in the target, or drop it and say in the cue why the whole file is read.",
                            ))
                else:
                    for symbol in _cue_symbols(cue):
                        if not _contains_word(target_text(resolved), symbol):
                            diagnostics.append(_diagnostic(
                                "map.cue_symbol_missing",
                                f"Cue symbol `{symbol}` does not occur in {resolved.as_posix()} linked from {page.path.as_posix()}.",
                                page.path,
                                "Rename the backticked symbol in the cue to one the target contains, or remove it and say in the cue why the whole file is read.",
                            ))

    for parent, expected in children.items():
        page = pages[parent]
        if page.role != "landmark":
            continue
        for child in sorted(expected - page.indexed_children):
            diagnostics.append(_diagnostic(
                "map.index_missing_child",
                f"Structural parent {parent.as_posix()} does not index immediate child {child.as_posix()}.",
                parent,
                f"Add an ordinary Markdown link from {parent.as_posix()} to {child.as_posix()}.",
            ))

    reachable: set[PurePosixPath] = set()
    pending = sorted(
        (path for path, page in pages.items() if page.role == "landmark" and page.parent is None),
        reverse=True,
    )
    while pending:
        current = pending.pop()
        if current in reachable:
            continue
        reachable.add(current)
        pending.extend(sorted(pages[current].indexed_children, reverse=True))
    for path in sorted(set(pages) - reachable):
        diagnostics.append(_diagnostic(
            "map.page_unreachable",
            f"Wiki page is not reachable through structural indexes: {path.as_posix()}.",
            path,
            "Repair every structural parent link from the top-level Landmark down to this page.",
        ))

    page_rows = []
    for path, page in sorted(pages.items()):
        page_rows.append(
            {
                "path": path.as_posix(),
                "role": page.role,
                "parent": page.parent.as_posix() if page.parent else MAP_PARENT,
                "depth": page.depth,
                "bytes": page.byte_count,
                "lines": page.line_count,
                "children": len(children[path]),
                "source_links": len(page.source_links),
                "cross_links": len(page.cross_links),
            }
        )
    report: dict[str, object] = {
        "summary": {
            "landmarks": sum(page.role == "landmark" for page in pages.values()),
            "satellites": sum(page.role == "satellite" for page in pages.values()),
            "source_links": sum(len(page.source_links) for page in pages.values()),
            "cross_links": sum(len(page.cross_links) for page in pages.values()),
        },
        "pages": page_rows,
    }
    return report, pages, sorted_diagnostics(diagnostics)


def validate(root: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    report, _pages, diagnostics = analyze(root)
    return report, diagnostics


def run_checks(root: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Validate the hierarchy, then the root Map blocks once a Map can be derived from it."""
    report, pages, diagnostics = analyze(root)
    if diagnostics:
        return report, diagnostics
    from repository_guidance import map_diagnostics

    return report, sorted_diagnostics(map_diagnostics(root, pages))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.repo_root.resolve()
    if not root.is_dir():
        parser.error(f"repository root is not a directory: {root}")
    report, diagnostics = run_checks(root)
    payload = {"diagnostics": diagnostics} if diagnostics else report
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 3 if diagnostics else 0


if __name__ == "__main__":
    raise SystemExit(main())

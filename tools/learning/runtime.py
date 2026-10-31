#!/usr/bin/env python3
"""Scaffold Tutor and Examiner files from skeletons and check saved pages under .learning/<subject>/.

Canonical source: tools/learning/runtime.py. tools/validation/sync_learning_runtime.py copies it unchanged
into each learning skill as scripts/learning_files.py, which is the only place it runs.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import http.client
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = SKILL_ROOT / "templates"
PAPER_RUNTIME = SKILL_ROOT / "assets" / "paper-runtime.html"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _diagnostic_contract import normalize_diagnostic  # noqa: E402

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RESERVED = frozenset({"con", "prn", "aux", "nul", *(f"com{n}" for n in range(1, 10)), *(f"lpt{n}" for n in range(1, 10))})
KINDS = {"tutor": ("lesson", "study-plan", "start-here"), "examiner": ("set", "study-plan", "start-here")}
PRACTICE_KINDS = ("full-mock", "section-practice", "topic-practice", "supplied-paper")
LESSON_NUMBER_RE = re.compile(r"^(\d+)-")
SET_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-(full-mock|section-practice|topic-practice|supplied-paper)-(\d+)$")
RUNTIME_MARKER = "<!-- paper-runtime -->"
SEGMENT_RE = r"[^/\\]+"
CHECK_FILE_RES = (
    re.compile(r"^START_HERE\.html$"),
    re.compile(r"^study-plan\.html$"),
    re.compile(rf"^lessons/{SEGMENT_RE}\.html$"),
    re.compile(rf"^exams/{SEGMENT_RE}/{SEGMENT_RE}/{SEGMENT_RE}\.html$"),
)
DRIVE_RE = re.compile(r"^[A-Za-z]:/")
MAX_EXTERNAL = 50
RETRY_WITH_GET = frozenset({400, 403, 405, 429, 501})
USER_AGENT = "first-four-hours-learning-check"

ACTIONS = {
    "learning.input_invalid": "Pass valid inputs: lowercase slugs joined by hyphens, real YYYY-MM-DD dates, and only the inputs the kind uses.",
    "learning.unsafe_path": "Pass the learner's folder as --repo-root and replace any linked or non-directory component of .learning/ with a real folder.",
    "learning.exists": "Leave the existing file untouched and scaffold again so the next free name is taken.",
    "learning.write_failed": "Fix the filesystem problem named in the message, then scaffold again.",
    "learning.package_incomplete": "Reinstall the skill package; a template or the paper runtime is missing.",
    "learning.unreadable": "Save the file as UTF-8 text, or report it to the learner if you may not change it.",
    "learning.unfilled": "Replace the fill marker with the content it describes, or report it to the learner if the text is protected.",
    "learning.link_broken": "Point the link at a file that exists, or remove it; report it to the learner if the text is protected.",
    "learning.fragment_missing": "Point the link at an id that exists in the target page, or add that id.",
    "learning.link_absolute": "Prefer a relative link so the page still works when the folder moves.",
    "learning.external_dead": "Replace the citation with a live source, or tell the learner it is dead.",
    "learning.external_unverified": "Correct the URL if it is malformed, else open the citation yourself, or tell the learner it could not be verified.",
    "learning.external_unreachable": "Retry later, or tell the learner the citation could not be reached.",
    "learning.external_offline": "Retry when the network is available, or rerun with external=skip and say the citations were not checked.",
    "learning.external_capped": "Check the remaining citations in a later run with fewer files.",
}


class Problem(Exception):
    """A blocking diagnostic raised during validation or writing."""

    def __init__(self, code: str, message: str, path: str | Path) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = str(path)


def diagnostic(skill: str, phase: str, code: str, message: str, path: str | Path, severity: str = "error", line: int | None = None) -> dict[str, Any]:
    text = f"{message} (line {line})" if line is not None else message
    value = {"code": code, "message": text, "severity": severity, "required_action": ACTIONS[code]}
    return normalize_diagnostic(value, skill=skill, phase=phase, artifact="learning-file", path=str(path))


def emit(payload: Any) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def title(slug: str) -> str:
    words = slug.replace("-", " ")
    return words[:1].upper() + words[1:]


def check_slug(name: str, value: str) -> None:
    if not SLUG_RE.fullmatch(value) or value in RESERVED:
        raise Problem("learning.input_invalid", f"{name} {value!r} must be lowercase words joined by hyphens and not a reserved device name", name)


def check_date(value: str) -> None:
    try:
        if not DATE_RE.fullmatch(value):
            raise ValueError(value)
        datetime.date.fromisoformat(value)
    except ValueError:
        raise Problem("learning.input_invalid", f"date {value!r} must be a real YYYY-MM-DD date", "date") from None


def repo_base(value: str) -> Path:
    root = Path(value)
    if not root.is_dir():
        raise Problem("learning.unsafe_path", f"--repo-root is not an existing directory: {value}", value)
    base = root.resolve()
    if base == SKILL_ROOT or SKILL_ROOT in base.parents:
        raise Problem("learning.unsafe_path", f"--repo-root {base} lies inside the installed skill; pass the learner's folder", base)
    return base


def contained(base: Path, parts: tuple[str, ...]) -> Path:
    """Return base/parts after proving every existing component is a real directory at its expected place."""
    for depth in range(1, len(parts) + 1):
        expected = base.joinpath(*parts[:depth])
        if not os.path.lexists(expected):
            continue
        if not expected.is_dir():
            raise Problem("learning.unsafe_path", f"{expected} exists but is not a directory", expected)
        if os.path.normcase(str(expected.resolve())) != os.path.normcase(str(expected)):
            raise Problem("learning.unsafe_path", f"{expected} resolves elsewhere through a link or junction; nothing was written", expected)
    return base.joinpath(*parts)


def read_template(name: str) -> str:
    path = TEMPLATES / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        raise Problem("learning.package_incomplete", f"template {name} is missing from the skill package", path) from None


def substitute(text: str, values: dict[str, str]) -> str:
    for token, value in values.items():
        text = text.replace("{{" + token + "}}", value)
    return text


def next_number(folder: Path, pattern: re.Pattern[str], group: int) -> int:
    highest = 0
    if folder.is_dir():
        for entry in folder.iterdir():
            match = pattern.match(entry.name)
            if match:
                highest = max(highest, int(match.group(group)))
    return highest + 1


class Writer:
    """Create directories and files exclusively, undoing only what this run created on failure."""

    def __init__(self) -> None:
        self.created: list[Path] = []

    def mkdirs(self, path: Path) -> None:
        missing = []
        current = path
        while not os.path.lexists(current):
            missing.append(current)
            current = current.parent
        for folder in reversed(missing):
            try:
                folder.mkdir()
            except FileExistsError:
                raise Problem("learning.exists", f"{folder} appeared while scaffolding", folder) from None
            except OSError as exc:
                raise Problem("learning.write_failed", f"could not create {folder}: {exc}", folder) from None
            self.created.append(folder)

    def write(self, path: Path, data: bytes) -> None:
        try:
            handle = open(path, "xb")
        except FileExistsError:
            raise Problem("learning.exists", f"{path} already exists and was left untouched", path) from None
        except OSError as exc:
            raise Problem("learning.write_failed", f"could not create {path}: {exc}", path) from None
        self.created.append(path)
        try:
            with handle:
                handle.write(data)
        except OSError as exc:
            raise Problem("learning.write_failed", f"could not write {path}: {exc}", path) from None

    def undo(self) -> None:
        for path in reversed(self.created):
            try:
                if path.is_dir() and not path.is_symlink():
                    path.rmdir()
                else:
                    path.unlink()
            except OSError:
                pass
        self.created.clear()


def scaffold(args: argparse.Namespace) -> dict[str, Any]:
    skill, kind = args.skill, args.kind
    if kind not in KINDS[skill]:
        raise Problem("learning.input_invalid", f"kind {kind!r} is not one {skill} scaffolds: {', '.join(KINDS[skill])}", "kind")
    base = repo_base(args.repo_root)
    check_slug("subject", args.subject)
    used = {
        "lesson": {"topic", "date"},
        "set": {"exam", "practice_kind", "date", "marking_scheme"},
        "study-plan": set(),
        "start-here": set(),
    }[kind]
    given = {name for name in ("topic", "date", "exam", "practice_kind", "marking_scheme") if getattr(args, name) is not None}
    unused = sorted(given - used)
    if unused:
        raise Problem("learning.input_invalid", f"kind {kind} does not use: {', '.join(unused)}", "kind")
    missing = sorted(name for name in used - {"marking_scheme"} if getattr(args, name) is None)
    if missing:
        raise Problem("learning.input_invalid", f"kind {kind} requires: {', '.join(missing)}", "kind")
    if args.topic is not None:
        check_slug("topic", args.topic)
    if args.exam is not None:
        check_slug("exam", args.exam)
    if args.date is not None:
        check_date(args.date)
    if args.practice_kind is not None and args.practice_kind not in PRACTICE_KINDS:
        raise Problem("learning.input_invalid", f"practice-kind must be one of {', '.join(PRACTICE_KINDS)}", "practice_kind")
    if args.marking_scheme not in (None, "yes", "no"):
        raise Problem("learning.input_invalid", "marking-scheme must be yes or no", "marking_scheme")
    if args.practice_kind == "supplied-paper" and args.marking_scheme == "yes":
        raise Problem("learning.input_invalid", "a supplied-paper set holds only Examiner's source notes; marking-scheme must not be yes", "marking_scheme")

    values = {"subject_title": title(args.subject), "date": args.date or ""}
    subject_parts = (".learning", args.subject)
    subject_dir = contained(base, subject_parts)
    plan: list[tuple[Path, bytes]] = []
    existing: list[str] = []
    folder_parts: tuple[str, ...]
    if kind in ("start-here", "study-plan"):
        name = "START_HERE.html" if kind == "start-here" else "study-plan.html"
        template = read_template("start-here.html" if kind == "start-here" else "study-plan.html")
        target = subject_dir / name
        folder_parts = subject_parts
        if os.path.lexists(target):
            existing.append(str(target))
        else:
            plan.append((target, substitute(template, values).encode("utf-8")))
    elif kind == "lesson":
        folder_parts = subject_parts + ("lessons",)
        lessons = contained(base, folder_parts)
        template = read_template("lesson.html")
        number = next_number(lessons, LESSON_NUMBER_RE, 1)
        values["topic_title"] = title(args.topic)
        plan.append((lessons / f"{number:02d}-{args.topic}.html", substitute(template, values).encode("utf-8")))
    else:
        exam_parts = subject_parts + ("exams", args.exam)
        exam_dir = contained(base, exam_parts)
        number = next_number(exam_dir, SET_RE, 2)
        folder = f"{args.date}-{args.practice_kind}-{number:02d}"
        folder_parts = exam_parts + (folder,)
        set_dir = contained(base, folder_parts)
        if os.path.lexists(set_dir):
            raise Problem("learning.exists", f"{set_dir} already exists and was left untouched", set_dir)
        values.update({"exam_title": title(args.exam), "set_id": f"{args.subject}/{args.exam}/{folder}"})
        if args.practice_kind == "supplied-paper":
            names = ["source-notes.html"]
        else:
            names = ["paper.html", "answer-key.html", "source-notes.html"]
            if args.marking_scheme == "yes":
                names.append("marking-scheme.html")
        templates = {name: read_template(name) for name in names}
        runtime = b""
        if "paper.html" in names:
            try:
                runtime = PAPER_RUNTIME.read_bytes()
            except OSError:
                raise Problem("learning.package_incomplete", "assets/paper-runtime.html is missing from the skill package", PAPER_RUNTIME) from None
        for name in names:
            text = substitute(templates[name], values)
            if name == "paper.html":
                lines = text.splitlines(keepends=True)
                marks = [index for index, line in enumerate(lines) if line.rstrip("\r\n") == RUNTIME_MARKER]
                if len(marks) != 1:
                    raise Problem("learning.package_incomplete", "the paper template must hold the paper-runtime marker line exactly once", TEMPLATES / name)
                index = marks[0]
                data = "".join(lines[:index]).encode("utf-8") + runtime + "".join(lines[index + 1:]).encode("utf-8")
            else:
                data = text.encode("utf-8")
            plan.append((set_dir / name, data))

    writer = Writer()
    try:
        for target, data in plan:
            contained(base, folder_parts)
            writer.mkdirs(target.parent)
            writer.write(target, data)
    except Problem:
        writer.undo()
        raise
    return {
        "status": "scaffolded",
        "kind": kind,
        "created": [str(target) for target, _ in plan],
        "existing": existing,
    }


class PageParser(HTMLParser):
    """Collect ids, href/src references with their lines, and fill markers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.refs: list[tuple[str, int]] = []
        self.fills: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        line = self.getpos()[0]
        for key, value in attrs:
            if value is None:
                continue
            if key == "id" or (key == "name" and tag == "a"):
                self.ids.add(value)
            elif key in ("href", "src"):
                self.refs.append((value, line))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_comment(self, data: str) -> None:
        if data.strip().startswith("fill:"):
            self.fills.append(self.getpos()[0])


def parse_page(path: Path) -> PageParser | None:
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    parser = PageParser()
    parser.feed(text)
    parser.close()
    return parser


def fetch(url: str) -> tuple[str, str] | None:
    """Return (code, detail) for a warning, or None when the URL responded."""
    def request(method: str) -> None:
        req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as response:
            if method == "GET":
                response.read(1)

    try:
        try:
            request("HEAD")
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRY_WITH_GET:
                raise
            request("GET")
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 410):
            return "learning.external_dead", f"returned HTTP {exc.code}"
        return "learning.external_unverified", f"returned HTTP {exc.code}"
    except (urllib.error.URLError, OSError, TimeoutError, http.client.HTTPException, ValueError) as exc:
        return "learning.external_unreachable", f"could not be reached: {exc}"
    return None


def check(args: argparse.Namespace) -> tuple[int, Any]:
    skill = args.skill
    base = repo_base(args.repo_root)
    check_slug("subject", args.subject)
    subject_parts = (".learning", args.subject)
    subject_dir = contained(base, subject_parts)
    if not subject_dir.is_dir():
        raise Problem("learning.input_invalid", f"{subject_dir} does not exist", subject_dir)
    names: list[str] = []
    for value in args.file:
        if not any(pattern.fullmatch(value) for pattern in CHECK_FILE_RES) or any(part in (".", "..") for part in value.split("/")):
            raise Problem("learning.input_invalid", f"file {value!r} is not a page under .learning/{args.subject}/", value)
        parts = tuple(value.split("/"))
        contained(base, subject_parts + parts[:-1])
        target = subject_dir.joinpath(*parts)
        if not target.is_file() or target.is_symlink():
            raise Problem("learning.input_invalid", f"file {value!r} is not an existing regular file", target)
        if value not in names:
            names.append(value)
    names.sort()

    found: list[tuple[int, dict[str, Any]]] = []
    cache: dict[str, PageParser | None] = {}
    external: dict[str, list[str]] = {}
    relative_count = 0

    def page(path: Path) -> PageParser | None:
        key = os.path.normcase(str(path))
        if key not in cache:
            cache[key] = parse_page(path)
        return cache[key]

    def add(code: str, message: str, path: Path | str, line: int | None = None, severity: str = "error") -> None:
        found.append((line or 0, diagnostic(skill, "check", code, message, path, severity, line)))

    for name in names:
        path = subject_dir.joinpath(*name.split("/"))
        parsed = page(path)
        if parsed is None:
            add("learning.unreadable", f"{name} is not readable UTF-8 text", path)
            continue
        for line in parsed.fills:
            add("learning.unfilled", f"{name} still holds a fill marker", path, line)
        for raw, line in parsed.refs:
            ref = raw.strip()
            if not ref or ref == "#":
                continue
            if ref.startswith("#"):
                fragment = urllib.parse.unquote(ref[1:])
                if fragment not in parsed.ids and fragment != "top":
                    add("learning.fragment_missing", f"{name} links #{fragment}, which no id in it matches", path, line)
                continue
            slashed = ref.replace("\\", "/")
            try:
                parts = urllib.parse.urlsplit(slashed)
            except ValueError as exc:
                # Only a URL with a host part can fail to split, so this is never a relative link.
                add("learning.external_unverified", f"{name} links {ref}, which is not a valid URL: {exc}", path, line, "warning")
                continue
            scheme = parts.scheme.lower()
            if slashed.startswith("/") or DRIVE_RE.match(slashed) or scheme == "file":
                add("learning.link_absolute", f"{name} uses the absolute link {ref}", path, line, "warning")
                continue
            if scheme in ("http", "https"):
                if not parts.netloc:
                    add("learning.external_unverified", f"{name} links {ref}, which has no host", path, line, "warning")
                else:
                    url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
                    external.setdefault(url, []).append(f"{name}:{line}")
                continue
            if scheme:
                continue
            relative_count += 1
            target = Path(os.path.normpath(path.parent / urllib.parse.unquote(parts.path))) if parts.path else path
            if not target.exists():
                add("learning.link_broken", f"{name} links {ref}, but {target} does not exist", path, line)
                continue
            fragment = urllib.parse.unquote(parts.fragment)
            if fragment and target.is_file() and target.suffix.lower() in (".html", ".htm"):
                linked = page(target)
                if linked is not None and fragment not in linked.ids and fragment != "top":
                    add("learning.fragment_missing", f"{name} links {ref}, but no id {fragment!r} exists in {target.name}", path, line)

    urls = sorted(external)
    checked = urls[:MAX_EXTERNAL]
    if len(urls) > MAX_EXTERNAL:
        add("learning.external_capped", f"{len(urls) - MAX_EXTERNAL} external links were not checked; at most {MAX_EXTERNAL} are checked per run", subject_dir, None, "warning")
    external_checked = args.external == "check"
    if external_checked and checked:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = dict(zip(checked, pool.map(fetch, checked)))
        failures = {url: outcome for url, outcome in outcomes.items() if outcome is not None}
        unreachable = [url for url, outcome in failures.items() if outcome[0] == "learning.external_unreachable"]
        if len(checked) >= 2 and len(unreachable) == len(checked):
            add("learning.external_offline", "no external link could be reached; the network may be unavailable", subject_dir, None, "warning")
        else:
            for url, (code, detail) in sorted(failures.items()):
                citers = ", ".join(external[url])
                add(code, f"{url} {detail}; cited at {citers}", subject_dir / external[url][0].split(":")[0], None, "warning")

    found.sort(key=lambda item: (item[1]["path"], item[0], item[1]["code"]))
    diagnostics = [item for _, item in found]
    if any(item["severity"] == "error" for item in diagnostics):
        return 1, diagnostics
    return 0, {
        "status": "checked",
        "subject": args.subject,
        "files": names,
        "relative_links": relative_count,
        "external_links": len(urls),
        "external_checked": external_checked,
        "warnings": diagnostics,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("scaffold", "check"):
        command = commands.add_parser(name)
        command.add_argument("--skill", choices=sorted(KINDS), required=True)
        command.add_argument("--repo-root", required=True)
        command.add_argument("--subject", required=True)
    build = commands.choices["scaffold"]
    build.add_argument("--kind", required=True)
    build.add_argument("--topic")
    build.add_argument("--date")
    build.add_argument("--exam")
    build.add_argument("--practice-kind", dest="practice_kind")
    build.add_argument("--marking-scheme", dest="marking_scheme")
    inspect = commands.choices["check"]
    inspect.add_argument("--file", action="append", required=True)
    inspect.add_argument("--external", choices=("check", "skip"), default="check")
    args = parser.parse_args(argv)
    try:
        if args.command == "scaffold":
            emit(scaffold(args))
            return 0
        code, payload = check(args)
        emit(payload)
        return code
    except Problem as problem:
        emit([diagnostic(args.skill, args.command, problem.code, problem.message, problem.path)])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

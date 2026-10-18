#!/usr/bin/env python3
"""Check a PR description draft for grounded citations, recorded runs, and Mermaid shape."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _diagnostic_contract import normalize_diagnostic  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parent.parent
Problem = tuple[str, str, str]  # (code, message, required_action)

FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
DIAGRAM_TYPES = frozenset(
    {
        "flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram", "stateDiagram-v2",
        "erDiagram", "journey", "gantt", "pie", "gitGraph", "mindmap", "timeline",
    }
)
SEQUENCE_OPENERS = frozenset({"loop", "alt", "opt", "par", "critical", "break", "rect", "box"})
SYMBOL = r"(?:::(?P<symbol>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*))?"
CITATION_RE = re.compile(
    r"(?P<path>(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_-][A-Za-z0-9_.-]*\.[A-Za-z][A-Za-z0-9]*)" + SYMBOL
)
ROOT_RE = re.compile(
    r"(?P<path>[A-Za-z0-9_-][A-Za-z0-9_.-]*\.(?:md|txt|json|toml|yaml|yml|cfg|ini|py|js|ts|sh|lock))" + SYMBOL
)
LINE_SUFFIX_RE = re.compile(r"(?::\d+(?:-\d+)?|#L\d+(?:-L?\d+)?)$")
SPAN_RE = re.compile(r"`([^`\n]+)`")
LINK_RE = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)\)")
URL_RE = re.compile(r"https?://\S+")
CLAIM_PREFIX = r"^\s*(?:>\s*)*(?:(?:[-*+]|\d+[.)])\s+)?(?:\[[ xX]\]\s+)?"
CLAIM_RE = re.compile(CLAIM_PREFIX + r"Ran:\s*`(?P<command>[^`]+)`")
CLAIM_LINE_RE = re.compile(CLAIM_PREFIX + r"Ran:")


class GitError(Exception):
    """A Git command failed or could not start."""


def git(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        raise GitError(str(exc)) from exc
    if result.returncode:
        raise GitError(result.stderr.strip() or f"git {args[0]} failed")
    return result.stdout


def inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def head_commit(repo: Path) -> str:
    return git(repo, "rev-parse", "--verify", "HEAD").strip()


def is_clean(repo: Path) -> bool:
    return not git(repo, "status", "--porcelain", "--untracked-files=normal").strip()


def emit(problems: list[Problem], path: Path) -> int:
    print(
        json.dumps(
            [
                normalize_diagnostic(
                    {"code": code, "message": message, "required_action": action},
                    skill="pr",
                    phase="validate",
                    artifact="description",
                    path=path,
                )
                for code, message, action in problems
            ],
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 1


class _Tree:
    """Memoized blob reads at HEAD and the merge base."""

    def __init__(self, repo: Path, head: str, merge_base: str) -> None:
        self.repo = repo
        self.commits = (head, merge_base)
        self._blob: dict[tuple[str, str], bool] = {}
        self._text: dict[tuple[str, str], str] = {}

    def is_blob(self, commit: str, path: str) -> bool:
        key = (commit, path)
        if key not in self._blob:
            try:
                self._blob[key] = git(self.repo, "cat-file", "-t", f"{commit}:{path}").strip() == "blob"
            except GitError:
                self._blob[key] = False
        return self._blob[key]

    def text(self, path: str) -> str | None:
        """Return the path's HEAD text, else its merge-base text, else None."""
        for commit in self.commits:
            if self.is_blob(commit, path):
                key = (commit, path)
                if key not in self._text:
                    try:
                        self._text[key] = git(self.repo, "show", f"{commit}:{path}")
                    except GitError:
                        self._text[key] = ""
                return self._text[key]
        return None


def _split(lines: list[str]) -> tuple[list[tuple[int, str]], list[tuple[int, str, list[tuple[int, str]], bool]]]:
    """Return prose lines and fenced blocks (opening line, info, body lines, closed)."""
    prose: list[tuple[int, str]] = []
    blocks: list[tuple[int, str, list[tuple[int, str]], bool]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        opening = FENCE_OPEN_RE.match(line)
        if not opening or (opening.group(1)[0] == "`" and "`" in opening.group(2)):
            prose.append((index + 1, line))
            index += 1
            continue
        fence = opening.group(1)
        close_re = re.compile(r"^ {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$")
        body: list[tuple[int, str]] = []
        closed = False
        cursor = index + 1
        while cursor < len(lines):
            if close_re.match(lines[cursor]):
                closed = True
                break
            body.append((cursor + 1, lines[cursor]))
            cursor += 1
        blocks.append((index + 1, opening.group(2).strip(), body, closed))
        index = cursor + 1
    return prose, blocks


def _first_word(text: str) -> str:
    parts = text.split()
    return parts[0] if parts else ""


def _statements(body: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Stripped diagram lines without blanks, `%%` comments, leading front matter, or accessibility text."""
    statements: list[tuple[int, str]] = []
    in_front_matter = False
    seen_front_matter = False
    description: tuple[int, str] | None = None
    for number, line in body:
        stripped = line.strip()
        if in_front_matter:
            if stripped == "---":
                in_front_matter = False
            continue
        if description:
            if "}" in stripped:
                description = None
            continue
        if not stripped or stripped.startswith("%%"):
            continue
        if stripped == "---" and not statements and not seen_front_matter:
            in_front_matter = seen_front_matter = True
            continue
        if statements and re.match(r"acc(?:Title|Descr)\b", stripped):
            if re.match(r"accDescr\s*\{", stripped) and "}" not in stripped:
                description = (number, stripped)
            continue
        statements.append((number, stripped))
    if description:
        statements.append(description)  # an unclosed `accDescr {` stays visible to the bracket check
    return statements


def _brackets_balanced(line: str) -> bool:
    """Balance ()[]{}; outside every bracket, a `>` right after a node id opens an asymmetric node closed by `]`."""
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for index, char in enumerate(line):
        if char in "([{":
            stack.append(char)
        elif char == ">" and not stack and index and (line[index - 1].isalnum() or line[index - 1] == "_"):
            stack.append(">")
        elif char in pairs:
            opener = stack.pop() if stack else None
            if opener != pairs[char] and not (char == "]" and opener == ">"):
                return False
    return not stack


def _mermaid_problems(start: int, body: list[tuple[int, str]]) -> list[Problem]:
    statements = _statements(body)
    kind = _first_word(statements[0][1]) if statements else ""
    if kind not in DIAGRAM_TYPES:
        found = kind or "(empty)"
        return [
            (
                "pr.mermaid_type",
                f"line {start}: the Mermaid block starts with `{found}`, not a supported diagram type.",
                "Start the block with one of: " + ", ".join(sorted(DIAGRAM_TYPES)) + ".",
            )
        ]
    lines = [line for _, line in statements]
    failure: str | None = None
    if kind in {"flowchart", "graph"}:
        if sum(_first_word(line) == "subgraph" for line in lines) != sum(line == "end" for line in lines):
            failure = "its `subgraph` and `end` lines do not balance"
        else:
            for number, line in statements:
                unquoted = re.sub(r'"[^"]*"', "", line)
                if '"' in unquoted:
                    failure = f"line {number} has an unbalanced quote"
                    break
                stripped = re.sub(
                    r"(?<![-=.])(?:--|==|-\.)(?![->.=])[^\[\](){}]*?(?:-->|==>|\.->|---|===)",
                    " --> ",
                    re.sub(r"\|[^|]*\|", "", unquoted),
                )
                if not _brackets_balanced(stripped):
                    failure = f"line {number} has unbalanced brackets"
                    break
    elif kind == "sequenceDiagram":
        if sum(_first_word(line) in SEQUENCE_OPENERS for line in lines) != sum(line == "end" for line in lines):
            failure = "its block openers and `end` lines do not balance"
    if failure is None:
        return []
    return [
        (
            "pr.mermaid_syntax",
            f"line {start}: the Mermaid block will not render because {failure}.",
            "Repair the diagram so every block, quote, and bracket is closed.",
        )
    ]


def _candidate(raw: str) -> tuple[str, str | None] | None:
    value = raw.removeprefix("./")
    value = LINE_SUFFIX_RE.sub("", value, count=1)
    for pattern in (CITATION_RE, ROOT_RE):
        match = pattern.fullmatch(value)
        if match:
            return match.group("path"), match.group("symbol")
    return None


def _link_target(target: str) -> str | None:
    if target.startswith(("http://", "https://", "mailto:", "#")):
        return None
    path, hash_mark, fragment = target.partition("#")
    if hash_mark and LINE_SUFFIX_RE.fullmatch("#" + fragment):
        return target
    return path


def _citation_problems(
    citations: list[tuple[int, str, str | None]], tree: _Tree, changed: set[str]
) -> list[Problem]:
    problems: list[Problem] = []
    changed_dirs = {posixpath.dirname(path) for path in changed}
    changed_texts: list[str] | None = None
    seen: set[tuple[str, str | None, int]] = set()
    for line, path, symbol in citations:
        if (path, symbol, line) in seen:
            continue
        seen.add((path, symbol, line))
        text = None if path.startswith("/") or ".." in path.split("/") else tree.text(path)
        if text is None:
            problems.append(
                (
                    "pr.citation_missing",
                    f"line {line}: `{path}` does not exist at HEAD or at the merge base.",
                    "Cite the real repo-relative path or drop the citation.",
                )
            )
            continue
        in_scope = path in changed or posixpath.dirname(path) in changed_dirs
        if not in_scope:
            if changed_texts is None:
                changed_texts = [tree.text(item) or "" for item in sorted(changed)]
            in_scope = any(path in item for item in changed_texts)
        if not in_scope:
            problems.append(
                (
                    "pr.citation_out_of_scope",
                    f"line {line}: `{path}` is not changed by this branch, beside a changed file, "
                    "or named by a changed file.",
                    "Describe it without a path or cite the changed file that uses it.",
                )
            )
            continue
        if symbol:
            name = symbol.rsplit(".", 1)[-1]
            if not re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", text):
                problems.append(
                    (
                        "pr.symbol_missing",
                        f"line {line}: `{name}` does not appear in `{path}` at HEAD or at the merge base.",
                        "Cite a symbol that exists in that file.",
                    )
                )
    return problems


def _claim_problems(prose: list[tuple[int, str]], records: list[dict[str, object]], head: str) -> list[Problem]:
    problems: list[Problem] = []
    for line, text in prose:
        claim = CLAIM_RE.match(text)
        if not claim:
            if CLAIM_LINE_RE.match(text):
                problems.append(
                    (
                        "pr.verification_malformed",
                        f"line {line}: a `Ran:` line must name its command in backticks.",
                        "Write it as - Ran: `<command>` with the command string `record` returned, "
                        "or state it on a `Not verified:` line.",
                    )
                )
            continue
        command = claim.group("command")
        matching = [record for record in records if record["command"] == command]
        if not matching:
            problems.append(
                (
                    "pr.verification_unrecorded",
                    f"line {line}: `{command}` has no recorded run.",
                    "Run it through `record` and copy its `command` string, or state it on a `Not verified:` line.",
                )
            )
            continue
        latest = matching[-1]
        if latest["exit_code"] != 0:
            problems.append(
                (
                    "pr.verification_failed",
                    f"line {line}: the latest recorded run of `{command}` exited {latest['exit_code']}.",
                    "Fix the failure and rerun it through `record`, or describe it as not verified.",
                )
            )
        elif latest["head"] != head or not latest["clean"]:
            problems.append(
                (
                    "pr.verification_stale",
                    f"line {line}: the latest recorded run of `{command}` was not at the current HEAD {head} "
                    "on a clean worktree.",
                    "Rerun it through `record` at the current HEAD on a clean worktree.",
                )
            )
    return problems


def _read_records(runs: Path) -> tuple[list[dict[str, object]], list[Problem]]:
    if not runs.is_file():
        return [], []
    records: list[dict[str, object]] = []
    problems: list[Problem] = []
    for number, line in enumerate(runs.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            record = None
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("command"), str)
            or type(record.get("exit_code")) is not int
            or not isinstance(record.get("head"), str)
            or not isinstance(record.get("clean"), bool)
        ):
            problems.append(
                (
                    "pr.runs_unreadable",
                    f"line {number} of the run log is not a recorded run.",
                    "Remove the malformed line, or start a fresh run log and record the runs again.",
                )
            )
            continue
        records.append(record)
    return records, problems


def check_description(repo: Path, draft: Path, runs: Path, base: str) -> tuple[list[Problem], dict[str, str]]:
    problems: list[Problem] = []
    if not draft.is_file() or inside(draft, repo) or inside(draft, SKILL_ROOT):
        problems.append(
            (
                "pr.draft_location",
                "the draft must be an existing file outside the target repository and the installed skill.",
                "Write the draft outside the repository and pass its path.",
            )
        )
    if inside(runs, repo) or inside(runs, SKILL_ROOT):
        problems.append(
            (
                "pr.runs_location",
                "the run log must be outside the target repository and the installed skill.",
                "Pass a run log path outside the repository.",
            )
        )
    if problems:
        return problems, {}

    try:
        head = head_commit(repo)
    except GitError as exc:
        return [
            (
                "pr.repository_unreadable",
                f"cannot read HEAD of the repository: {exc}.",
                "Run from a Git repository with at least one commit.",
            )
        ], {}
    try:
        merge_base = git(repo, "merge-base", base, "HEAD").strip()
    except GitError as exc:
        return [
            (
                "pr.base_unresolved",
                f"base `{base}` has no merge base with HEAD: {exc}.",
                "Pass a base ref that exists locally, such as origin/main, after fetching it.",
            )
        ], {}
    try:
        fields = [item for item in git(repo, "diff", "--name-status", "-z", "-M", merge_base, "HEAD").split("\0") if item]
    except GitError as exc:
        return [("pr.repository_unreadable", f"cannot read the diff: {exc}.", "Repair the repository and retry.")], {}
    changed: set[str] = set()
    index = 0
    while index < len(fields):
        status = fields[index]
        width = 2 if status[:1] in {"R", "C"} else 1
        changed.update(fields[index + 1 : index + 1 + width])
        index += 1 + width
    if not changed:
        return [
            (
                "pr.empty_diff",
                f"HEAD has no changes against `{base}`.",
                "Commit the change on this branch, or pass the base the PR targets.",
            )
        ], {}

    raw = draft.read_bytes()
    try:
        text = raw.decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeDecodeError:
        return [("pr.draft_unreadable", "the draft must be UTF-8 text.", "Save the draft as UTF-8.")], {}
    records, record_problems = _read_records(runs)
    if record_problems:
        return record_problems, {}

    tree = _Tree(repo, head, merge_base)
    prose, blocks = _split(text.split("\n"))
    citations: list[tuple[int, str, str | None]] = []
    for number, line in prose:
        claim = CLAIM_RE.match(line)
        scanned = line[claim.end() :] if claim else line
        candidates = list(SPAN_RE.findall(scanned))
        for target in LINK_RE.findall(scanned):
            resolved = _link_target(target)
            if resolved:
                candidates.append(resolved)
        for raw_candidate in candidates:
            found = _candidate(raw_candidate)
            if found:
                citations.append((number, *found))
    for start, info, body, closed in blocks:
        if _first_word(info).lower() != "mermaid":
            continue
        if info != "mermaid" or not closed:
            reason = "is not closed" if info == "mermaid" else f"has info `{info}`, not exactly `mermaid`"
            problems.append(
                (
                    "pr.mermaid_fence",
                    f"line {start}: the diagram fence {reason}, so GitHub shows it as raw code.",
                    "Open the block with ```mermaid exactly and close it with a matching fence.",
                )
            )
            continue
        problems.extend(_mermaid_problems(start, body))
        for number, line in body:
            scanned = URL_RE.sub("", line)
            for match in CITATION_RE.finditer(scanned):
                if match.start() and re.match(r"[A-Za-z0-9_./-]", scanned[match.start() - 1]):
                    continue
                citations.append((number, match.group("path"), match.group("symbol")))
    problems.extend(_citation_problems(citations, tree, changed))
    problems.extend(_claim_problems(prose, records, head))
    if problems:
        return problems, {}
    return [], {"status": "checked", "head": head, "body_sha256": hashlib.sha256(raw).hexdigest()}

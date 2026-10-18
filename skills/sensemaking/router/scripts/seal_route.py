#!/usr/bin/env python3
"""Check an agent-authored route draft and seal it as ignored .first-four-hours/routes/<slug>/route.md."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = SKILL_ROOT / "assets" / "capabilities.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _diagnostic_contract import normalize_diagnostic  # noqa: E402
from route_workspace import WorkspaceError, prepare_workspace  # noqa: E402

TITLE_RE = re.compile(r"^# Route: \S.*$")
STEPS_HEADING = "## Steps"
STEP_RE = re.compile(r"^(\d+)\. `([^`]+)`$")
FIELD_RE = re.compile(r"^\s+- (Why|Input|Result|Prompt):(.*)$")
FENCE_RE = re.compile(r"^\s+(`{3,})[^`]*$")  # an indented opening fence and its backtick run
REPOSITORY_RE = re.compile(r"^Repository: (\S.*)$")
NONE_RE = re.compile(r"^None:(.*)$")
MARKER_RE = re.compile(r"^(\d+\. |- [^:]*:|None:)")  # structure that must never pass as wrapped text
FIELDS = ("Why", "Input", "Result")
Problem = tuple[str, str]  # (code, message)


@dataclasses.dataclass
class _Step:
    number: int
    capability: str
    fields: dict[str, list[str]] = dataclasses.field(default_factory=dict)
    prompts: list[list[str]] = dataclasses.field(default_factory=list)  # fenced prompt bodies
    last: str | None = None  # the most recent field name


def capability_names() -> frozenset[str]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return frozenset(str(entry["name"]) for entry in payload["capabilities"])


def _check_repository(lines: list[str], repo: Path) -> list[Problem]:
    non_empty = [line for line in lines if line.strip()]
    declared = non_empty[1] if len(non_empty) > 1 else None
    match = REPOSITORY_RE.match(declared.rstrip()) if declared is not None else None
    value = match.group(1).strip() if match else ""
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        value = value[1:-1].strip()
    if not value or not Path(value).is_absolute():
        return [
            (
                "route.repository",
                "the first line after the title must be `Repository: <absolute path of the target repository>`",
            )
        ]
    if os.path.normcase(str(Path(value).resolve())) != os.path.normcase(str(repo)):
        return [
            (
                "route.repository_mismatch",
                f"the route names repository {value} but is being sealed into {repo}; "
                "pass the intended repository as --repo-root, and do not rewrite the line to match where you run",
            )
        ]
    return []


def check_route(text: str, capabilities: frozenset[str], repo: Path) -> list[Problem]:
    lines = text.split("\n")
    problems: list[Problem] = _check_repository(lines, repo)
    first = next((line for line in lines if line.strip()), "")
    if not TITLE_RE.match(first.rstrip()):
        problems.append(("route.title", "the first non-empty line must be `# Route: <target>`"))
    headings = [i for i, line in enumerate(lines) if line.rstrip() == STEPS_HEADING]
    if len(headings) != 1:
        problems.append(("route.steps_missing", "the route needs exactly one `## Steps` section"))
        return problems
    start = headings[0] + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    steps: list[_Step] = []
    none_lines: list[str] = []
    fence: str | None = None  # backtick run of the open prompt fence
    for number, line in enumerate(lines[start:end], start=start + 1):
        stripped = line.rstrip()
        if fence is not None:
            body = stripped.strip()
            if body and set(body) == {"`"} and len(body) >= len(fence):
                fence = None
            else:
                steps[-1].prompts[-1].append(stripped)
            continue  # fence content is opaque: no marker or step checks
        if not stripped:
            continue
        if step := STEP_RE.match(stripped):
            steps.append(_Step(int(step.group(1)), step.group(2)))
        elif (field := FIELD_RE.match(stripped)) and steps:
            steps[-1].fields.setdefault(field.group(1), []).append(field.group(2).strip())
            steps[-1].last = field.group(1)
        elif (opening := FENCE_RE.match(stripped)) and steps:
            if steps[-1].last == "Prompt" and not steps[-1].prompts:
                fence = opening.group(1)
                steps[-1].prompts.append([])
            else:
                problems.append(
                    ("route.step_prompt", f"line {number}: only a step's `- Prompt:` line takes one indented fenced block")
                )
        elif none := NONE_RE.match(stripped):
            none_lines.append(none.group(1).strip())
        elif line[:1].isspace() and steps and steps[-1].fields and not MARKER_RE.match(stripped.lstrip()):
            continue  # wrapped text of the previous field
        else:
            problems.append(
                (
                    "route.step_line",
                    f"line {number}: expected a numbered `capability` step, an indented Why/Input/Result/Prompt field "
                    "with the Prompt's indented fenced block, or one `None:` line",
                )
            )
    if fence is not None:
        problems.append(("route.step_prompt", f"step {len(steps)}: close the Prompt's fenced block with a matching fence"))
    if none_lines:
        if steps or len(none_lines) != 1 or not none_lines[0]:
            problems.append(("route.none_mixed", "use either numbered steps or exactly one non-empty `None:` line"))
        return problems
    if not steps:
        problems.append(
            (
                "route.steps_empty",
                "add the needed steps, or one `None: <established postcondition>` "
                "line when current state already satisfies the target",
            )
        )
        return problems
    for index, entry in enumerate(steps, start=1):
        if entry.number != index:
            problems.append(
                ("route.step_numbering", f"step {entry.number} must be numbered {index}; number steps 1..n in order")
            )
        if entry.capability not in capabilities:
            problems.append(
                (
                    "route.capability_unknown",
                    f"step {index}: `{entry.capability}` is not a routable capability; "
                    f"use one of {', '.join(sorted(capabilities))}",
                )
            )
        for name in FIELDS:
            values = entry.fields.get(name, [])
            if len(values) != 1 or not values[0]:
                problems.append(("route.step_field", f"step {index}: give exactly one non-empty `{name}:` field"))
        prompt_values = entry.fields.get("Prompt", [])
        if (
            len(prompt_values) != 1
            or prompt_values[0]
            or len(entry.prompts) != 1
            or not any(text.strip() for text in entry.prompts[0])
        ):
            problems.append(
                (
                    "route.step_prompt",
                    f"step {index}: give exactly one empty `- Prompt:` line followed by one "
                    "indented fenced block holding the copyable prompt",
                )
            )
    return problems


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _write_atomic(destination: Path, text: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}-",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
            temporary_name = tmp.name
        os.replace(temporary_name, destination)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--slug", required=True)
    args = parser.parse_args(argv)

    def emit(problems: list[Problem]) -> int:
        print(
            json.dumps(
                [
                    normalize_diagnostic(
                        {"code": code, "message": message},
                        skill="router",
                        phase="validate",
                        artifact="route",
                        path=args.draft,
                    )
                    for code, message in problems
                ],
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1

    if not args.repo_root.is_dir():
        return emit([("route.workspace_unsafe", f"repo-root is not an existing directory: {args.repo_root}")])
    repo = args.repo_root.resolve()
    if _inside(repo, SKILL_ROOT.resolve()):
        return emit(
            [
                (
                    "route.workspace_unsafe",
                    f"repo-root {repo} is the installed Router skill or lies inside it; "
                    "pass the intended project repository as --repo-root",
                )
            ]
        )
    draft = args.draft.resolve()
    if not draft.is_file() or _inside(draft, repo) or _inside(draft, SKILL_ROOT.resolve()):
        return emit(
            [
                (
                    "route.draft_location",
                    "the draft must be an existing file outside the target repository and the installed skill",
                )
            ]
        )
    try:
        text = draft.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeDecodeError:
        return emit([("route.draft_unreadable", "the draft must be UTF-8 text")])
    try:
        capabilities = capability_names()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return emit([("route.manifest_unreadable", f"{MANIFEST}: {exc}; reinstall the router package")])
    problems = check_route(text, capabilities, repo)
    if problems:
        return emit(problems)
    if not text.endswith("\n"):
        text += "\n"
    try:
        destination, git_ignored = prepare_workspace(repo, args.slug)
    except (WorkspaceError, OSError, subprocess.SubprocessError) as exc:
        return emit([("route.workspace_unsafe", str(exc))])
    extras = sorted(entry.name for entry in destination.parent.iterdir() if entry.name != destination.name)
    if extras:
        return emit(
            [
                (
                    "route.output_not_exclusive",
                    f"{destination.parent} holds files other than route.md: {extras}; "
                    "remove them or choose a fresh slug",
                )
            ]
        )
    _write_atomic(destination, text)
    print(
        json.dumps(
            {"status": "sealed", "path": str(destination), "git_ignored": git_ignored},
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

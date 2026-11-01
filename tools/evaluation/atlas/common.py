"""Shared pieces of the Atlas evaluation: fixed method, headless runs, and tool-call capture."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
ATLAS_SKILL_SOURCE = REPO_ROOT / "skills" / "workbench" / "atlas"
EMPTY_MCP = HERE / "empty-mcp.json"
DEFAULT_WORK = REPO_ROOT / ".scratch" / "atlas-eval"

ANSWER_MODEL = "claude-sonnet-5-5"
ANSWER_EFFORT = "medium"
GRADER_MODEL = "claude-opus-5-5"
GRADER_EFFORT = "high"
ARMS = ("baseline", "atlas")

READ_ONLY_TOOLS = ["Read", "Grep", "Glob", "Skill"]
DENIED_TOOLS = ["Bash", "PowerShell", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch", "Agent", "Task"]
BUILD_TOOLS = ["Read", "Grep", "Glob", "Skill", "Bash", "PowerShell", "Write", "Edit"]
BUILD_DENIED = ["NotebookEdit", "WebFetch", "WebSearch", "Agent", "Task"]
ATLAS_MARKER = "<!-- ATLAS -->"


def load_questions(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def is_control(q: dict[str, Any]) -> bool:
    return bool(q.get("control"))


def claude_cmd(prompt: str | None, *, model: str, effort: str, allowed: list[str], denied: list[str]) -> list[str]:
    cmd = ["claude", "-p"]
    if prompt is not None:
        cmd.append(prompt)
    cmd += [
        "--model", model, "--effort", effort,
        "--output-format", "stream-json", "--verbose",
        "--setting-sources", "project",
        "--no-session-persistence",
        "--strict-mcp-config", "--mcp-config", str(EMPTY_MCP),
    ]
    if allowed:
        cmd += ["--allowedTools", *allowed]
    cmd += ["--disallowedTools", *denied]
    return cmd


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def _touches_map(value: str) -> bool:
    v = _norm(value)
    return v.startswith(".map/") or "/.map/" in v or v in (".map", "./.map") or v.endswith("/.map")


def classify_call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Reduce one tool call to its name, a short target, and whether it used the map."""
    target = ""
    if name == "Read":
        target = str(args.get("file_path", ""))
    elif name in ("Grep", "Glob"):
        target = f'{args.get("pattern", "")} @ {args.get("path", "")}'.strip(" @")
    elif name == "Skill":
        target = str(args.get("skill") or args.get("command") or args.get("name") or "")
    else:
        target = json.dumps(args)[:200]
    map_use = False
    if name == "Read":
        map_use = _touches_map(target)
    elif name in ("Grep", "Glob"):
        map_use = _touches_map(str(args.get("path", ""))) or _touches_map(str(args.get("pattern", "")))
        glob = str(args.get("glob", ""))
        map_use = map_use or glob.startswith(".map")
    elif name == "Skill":
        map_use = "atlas" in target.lower()
    return {"tool": name, "target": target, "map": map_use}


def run_stream(cmd: list[str], *, cwd: Path, timeout: int, stdin_text: str | None = None) -> dict[str, Any]:
    """Run one headless session; return its result event, loaded skills, and every tool call."""
    started = time.time()
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
            input=stdin_text, stdin=None if stdin_text is not None else subprocess.DEVNULL,
        )
        stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout
        stdout = out.decode("utf-8", "replace") if isinstance(out, bytes) else (out or "")
        stderr, code = "timeout", -1
    result: dict[str, Any] | None = None
    skills: list[str] = []
    calls: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            skills = [str(s) for s in event.get("skills") or []]
        elif kind == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    calls.append(classify_call(str(block.get("name")), block.get("input") or {}))
        elif kind == "result":
            result = event
    return {
        "returncode": code,
        "wall_s": round(time.time() - started, 1),
        "stderr": stderr[-2000:],
        "result_event": result,
        "skills_loaded": skills,
        "tool_calls": calls,
    }


def run_ok(raw: dict[str, Any], model: str) -> tuple[bool, str]:
    data = raw["result_event"]
    if not data:
        return False, "no result event"
    if raw["returncode"] != 0 or data.get("is_error") or data.get("subtype") != "success":
        return False, f'error: {data.get("subtype")} {data.get("api_error_status") or ""}'.strip()
    models = list((data.get("modelUsage") or {}).keys())
    if not any(m.startswith(model) for m in models):
        return False, f"unexpected models {models}"
    return True, ""


def tool_counts(calls: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"reads": 0, "greps": 0, "globs": 0, "skills": 0, "map_calls": 0, "tool_calls": len(calls)}
    for c in calls:
        key = {"Read": "reads", "Grep": "greps", "Glob": "globs", "Skill": "skills"}.get(c["tool"])
        if key:
            counts[key] += 1
        if c["map"]:
            counts["map_calls"] += 1
    return counts


def tokens(usage: dict[str, Any]) -> dict[str, int]:
    inp = int(usage.get("input_tokens", 0))
    cc = int(usage.get("cache_creation_input_tokens", 0))
    cr = int(usage.get("cache_read_input_tokens", 0))
    out = int(usage.get("output_tokens", 0))
    return {"input": inp, "cache_creation": cc, "cache_read": cr, "output": out, "total": inp + cc + cr + out}


def git_head(repo: Path) -> str:
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def arm_state(repo: Path) -> dict[str, bool]:
    guidance = any(
        (repo / name).is_file() and ATLAS_MARKER in (repo / name).read_text(encoding="utf-8", errors="replace")
        for name in ("CLAUDE.md", "AGENTS.md")
    )
    return {
        "map": (repo / ".map").is_dir(),
        "guidance": guidance,
        "skill": (repo / ".claude" / "skills" / "atlas" / "SKILL.md").is_file(),
    }


def check_arm(repo: Path, arm: str, commit: str) -> list[str]:
    """Return every reason the checkout does not match the arm's fixed setup."""
    problems = []
    head = git_head(repo)
    if not head.startswith(commit) and not commit.startswith(head):
        problems.append(f"checkout is at {head}, question set pins {commit}")
    state = arm_state(repo)
    want = arm == "atlas"
    for part, present in state.items():
        if present != want:
            problems.append(f'{arm} arm needs {part} {"present" if want else "absent"}')
    return problems

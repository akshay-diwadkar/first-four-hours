"""PreToolUse guard that Provision installs beside batch-ops on Claude Code and Codex.

It refuses the main agent's native reads, searches, shell commands, and edits
inside the project, naming the batch-ops tool to use instead.

On Claude Code, which tells a hook nothing about MCP connections, it refuses
only while the session transcript's latest batch-ops addition or removal says
batch-ops is connected. A transcript or payload it cannot read or recognize
allows the call, so it never strands an agent that has no batch-ops tools.
Subagents, files outside the project, images, PDFs, and notebooks, background
shell commands, and shell commands in plan mode keep their native tools.

On Codex (a `codex` argument), hooks see neither MCP connections nor
subagents, so the guard refuses every agent's shell commands, and patches that
touch the project, for as long as it is installed. Shell commands in plan mode
and patches wholly outside the project pass.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

SERVER = "batch-ops"
DELTAS = {"mcp_instructions_delta": SERVER, "deferred_tools_delta": "mcp__batch-ops__batch_read"}
LOAD = (
    'ToolSearch with query "select:mcp__batch-ops__batch_read,'
    'mcp__batch-ops__batch_run,mcp__batch-ops__batch_edit"'
)
MEDIA = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".pdf", ".ipynb"})
SHELLS = frozenset({"Bash", "PowerShell"})
PATHS = {"Read": "file_path", "Edit": "file_path", "Write": "file_path", "Grep": "path", "Glob": "path"}
PATCH_HEADERS = ("*** Add File: ", "*** Update File: ", "*** Delete File: ", "*** Move to: ")
USE = {
    "Read": 'mcp__batch-ops__batch_read with a "path" or "path:N-M" spec',
    "Grep": 'mcp__batch-ops__batch_read with a "grep:RE [in PATH..]" spec',
    "Glob": 'mcp__batch-ops__batch_read with a "glob:PATTERN" spec',
    "Edit": "mcp__batch-ops__batch_edit",
    "Write": "mcp__batch-ops__batch_edit (new_files; overwrite=true replaces a file)",
    "Bash": "mcp__batch-ops__batch_run",
    "PowerShell": 'mcp__batch-ops__batch_run (shell: "powershell")',
}
CODEX_USE = {
    "Bash": "the batch_ops batch_read tool for reads and searches, and batch_run for other commands",
    "apply_patch": "the batch_ops batch_edit tool",
}


def connected(transcript: str) -> bool:
    """Whether the latest batch-ops delta in the transcript added it."""
    state = False
    with open(transcript, encoding="utf-8", errors="replace") as lines:
        for line in lines:
            if SERVER not in line or "_delta" not in line:
                continue
            try:
                delta = json.loads(line).get("attachment") or {}
                kind = delta.get("type")
                name = DELTAS.get(kind) if isinstance(kind, str) else None
            except (ValueError, AttributeError):
                continue
            if name is None:
                continue
            if name in (delta.get("addedNames") or []) + (delta.get("readdedNames") or []):
                state = True
            if name in (delta.get("removedNames") or []):
                state = False
    return state


def inside(path: str | None, root: str, cwd: str) -> bool:
    if not path:
        return True
    full = os.path.normcase(os.path.abspath(os.path.join(cwd, path)))
    base = os.path.normcase(os.path.abspath(root))
    try:
        return os.path.commonpath([full, base]) == base
    except ValueError:  # another drive
        return False


def patch_paths(patch: object) -> list[str]:
    if not isinstance(patch, str):
        return []
    return [line[len(head):].strip() for line in patch.splitlines() for head in PATCH_HEADERS if line.startswith(head)]


def refusal(event: dict[str, Any], codex: bool = False) -> str | None:
    """The reason to refuse this tool call, or None to allow it."""
    tool = event.get("tool_name")
    if not isinstance(tool, str):
        return None
    use = (CODEX_USE if codex else USE).get(tool)
    if use is None or event.get("agent_id"):
        return None
    args = event.get("tool_input") or {}
    cwd = event.get("cwd") or os.getcwd()
    root = cwd if codex else os.environ.get("CLAUDE_PROJECT_DIR") or cwd
    if tool in SHELLS:
        if args.get("run_in_background") or event.get("permission_mode") == "plan":
            return None
    elif tool == "apply_patch":
        paths = patch_paths(args.get("command"))
        if paths and not any(inside(path, root, cwd) for path in paths):
            return None
    else:
        path = args.get(PATHS[tool])
        if tool == "Read" and os.path.splitext(path or "")[1].lower() in MEDIA:
            return None
        if not inside(path, root, cwd):
            return None
    if codex:
        return (
            f"Provision's batch_ops guard sends {tool} inside this project through {use}. "
            "If batch_ops tools are missing or fail, tell the user, who can remove this hook."
        )
    if not connected(event["transcript_path"]):
        return None
    return (
        f"batch-ops is connected, so {tool} inside this project goes through {use}. "
        f"If that tool's schema is not loaded, call {LOAD} first. "
        "If batch-ops calls fail, tell the user rather than retrying natively."
    )


def main() -> int:
    try:
        reason = refusal(json.load(sys.stdin), codex="codex" in sys.argv[1:])
    except Exception:  # anything unreadable allows the call
        return 0
    if reason:
        json.dump({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())

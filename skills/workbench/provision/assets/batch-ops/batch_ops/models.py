"""Pydantic models, JSON serialization helpers, and common result envelope.

Defines typed schemas for ReadSpec, RunSpec, EditSpec, NewFileSpec, RenameSpec,
and VerifySpec so FastMCP emits structured tool schemas. Also formats results into
the common envelope specified in the design doc.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from .types import Coverage, EditReport, FileChange, ReadResult, Report, RunResult, Workspace


# ---------------------------------------------------------------------------
# Request Models for FastMCP Schema Generation
# ---------------------------------------------------------------------------
class FileReadSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    path: str = Field(description="Relative path to file")
    range: str | None = Field(default=None, description="1-based line range e.g. '120-180'")
    mode: Literal["auto", "lines", "raw", "target", "context", "grep", "list"] = Field(
        default="auto", description="Read mode"
    )
    pattern: str | None = Field(default=None, description="Regex or substring for context/grep mode")
    context: int = Field(default=3, description="Lines of context surrounding matches")
    label: str = Field(default="", description="Descriptive label for this item")
    priority: Literal["must", "should", "nice"] = Field(default="should", description="Budget priority")
    encoding: str | None = Field(default=None, description="Explicit encoding hint")
    max_bytes: int | None = Field(default=None, description="Per-item byte ceiling")
    max_lines: int | None = Field(default=None, description="Per-item line ceiling")


class GlobReadSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    glob: str = Field(description="Glob pattern e.g. 'src/**/*.txt'")
    mode: Literal["list", "auto"] = Field(default="list", description="Glob mode: 'list' returns manifest")
    expand: bool = Field(default=False, description="Whether to read contents under budget")
    max_files: int = Field(default=200, description="Max files to match")
    label: str = Field(default="", description="Descriptive label")
    priority: Literal["must", "should", "nice"] = Field(default="should", description="Budget priority")


class GrepReadSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    grep: str = Field(description="Regex search pattern")
    paths: list[str] = Field(default_factory=list, description="Subdirectories or files to search in")
    context: int = Field(default=0, description="Surrounding context lines")
    ignore_case: bool = Field(default=False, description="Case-insensitive matching")
    fixed: bool = Field(default=False, description="Literal substring match instead of regex")
    max_matches: int = Field(default=200, description="Max total matches")
    max_files: int = Field(default=5000, description="Max files to search (non-ignored files when inside a git repository)")
    label: str = Field(default="", description="Descriptive label")
    priority: Literal["must", "should", "nice"] = Field(default="should", description="Budget priority")


class GitReadSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    git: Literal["diff", "changed"] = Field(description="'diff' for unified diff, 'changed' for modified files")
    base: str = Field(default="HEAD", description="Git ref to diff against")
    staged: bool = Field(default=False, description="Check staged changes")
    paths: list[str] = Field(default_factory=list, description="Specific path filters")
    context: int = Field(default=3, description="Diff context lines")
    label: str = Field(default="", description="Descriptive label")
    priority: Literal["must", "should", "nice"] = Field(default="should", description="Budget priority")


class CompareReadSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    compare: list[Any] = Field(description="List of two file or handle specs to compare")
    label: str = Field(default="", description="Descriptive label")
    priority: Literal["must", "should", "nice"] = Field(default="should", description="Budget priority")


class HandleReadSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    handle: str = Field(description="Stateless read handle e.g. 'read:src/app.txt:5b288c9eb85dd1fb:120-180'")
    label: str = Field(default="", description="Descriptive label")
    priority: Literal["must", "should", "nice"] = Field(default="should", description="Budget priority")


ReadSpec = Union[FileReadSpec, GlobReadSpec, GrepReadSpec, GitReadSpec, CompareReadSpec, HandleReadSpec, str, dict[str, Any]]


class CmdRunSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    cmd: str = Field(description="Shell command string to execute")
    label: str = Field(default="", description="Label for command in report")
    cwd: str = Field(default=".", description="Working directory relative to root")
    timeout: float = Field(default=120.0, description="Per-command timeout in seconds")
    env: dict[str, str] = Field(default_factory=dict, description="Custom environment variables")
    shell: Literal["auto", "bash", "sh", "cmd", "powershell", "direct"] = Field(
        default="auto", description="Shell type"
    )
    slices: list[str] = Field(default_factory=list, description="Post-capture stream slices e.g. ['fails', 'tail:50']")
    priority: Literal["must", "should", "nice"] = Field(default="should", description="Budget priority")
    stdin: str | None = Field(default=None, description="Standard input string")
    merge_streams: bool = Field(default=False, description="Merge stderr into stdout")
    max_bytes: int = Field(default=16384, description="Maximum inline bytes before truncation")


class ArgvRunSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    argv: list[str] = Field(description="Process arguments without shell invocation")
    label: str = Field(default="", description="Label for command")
    cwd: str = Field(default=".", description="Working directory relative to root")
    timeout: float = Field(default=120.0, description="Per-command timeout in seconds")
    env: dict[str, str] = Field(default_factory=dict, description="Custom environment variables")
    shell: Literal["auto", "bash", "sh", "cmd", "powershell", "direct"] = Field(
        default="direct", description="Direct process invocation"
    )
    slices: list[str] = Field(default_factory=list, description="Post-capture stream slices")
    priority: Literal["must", "should", "nice"] = Field(default="should", description="Budget priority")
    stdin: str | None = Field(default=None, description="Standard input string")
    merge_streams: bool = False
    max_bytes: int = Field(default=16384, description="Maximum inline bytes")


RunSpec = Union[CmdRunSpec, ArgvRunSpec, str, dict[str, Any]]


class EditSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    path: str = Field(description="Target file path relative to root")
    search: str = Field(description="Exact literal string to search (must not be whitespace-only)")
    replace: str = Field(description="Replacement string")
    replace_all: bool = Field(default=False, description="Replace every occurrence if True")
    occurrence: int | None = Field(default=None, description="1-based occurrence number to replace")
    encoding: str | None = Field(default=None, description="Encoding override")
    label: str = Field(default="", description="Label for this edit")


class NewFileSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    path: str = Field(description="File path to create")
    content: str = Field(description="File content")
    overwrite: bool = Field(default=False, description="Allow overwriting an existing file")
    mode: int | str | None = Field(default=None, description="File permissions mode e.g. 0o644 or '644'")
    encoding: str = Field(default="utf-8", description="File encoding")


class RenameSpec(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    from_path: str = Field(default="", alias="from", description="Source path")
    to_path: str = Field(default="", alias="to", description="Destination path")
    source: str = Field(default="", description="Alias for from_path")
    destination: str = Field(default="", description="Alias for to_path")
    overwrite: bool = Field(default=False, description="Overwrite destination if it exists")


class VerifySpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    cmd: str | None = Field(default=None, description="Verification command string")
    argv: list[str] | None = Field(default=None, description="Verification argv list")
    cwd: str | None = Field(default=None, description="Verification cwd")
    timeout: float = Field(default=120.0, description="Verification timeout in seconds")
    env: dict[str, str] = Field(default_factory=dict, description="Verification environment")
    shell: Literal["auto", "bash", "sh", "cmd", "powershell", "direct"] = Field(
        default="auto", description="Verification shell"
    )
    label: str = Field(default="verify", description="Label for verification command")


# ---------------------------------------------------------------------------
# Serialization and Envelope Construction
# ---------------------------------------------------------------------------
def jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: jsonable(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    return value


def _format_workspace(ws: Workspace, cwd: str) -> dict[str, Any]:
    root = ws.root or cwd
    git_info: dict[str, Any] | None = None
    if ws.git_root:
        git_info = {
            "head": ws.head,
            "branch": ws.branch,
            "dirty": ws.dirty,
            "changed_count": ws.changed_count,
        }
    return {"root": root, "git": git_info}


def _format_budget(
    tokens: int,
    bytes_limit: int,
    time_s: float,
    used_bytes: int,
    used_tokens: int | None = None,
) -> dict[str, Any]:
    actual_tokens = used_tokens if used_tokens is not None else max(1, used_bytes // 4)
    return {
        "tokens": tokens,
        "bytes": bytes_limit,
        "time_s": time_s,
        "used": {
            "tokens": actual_tokens,
            "bytes": used_bytes,
        },
    }


def _format_coverage(cov: Coverage) -> dict[str, Any]:
    return {
        "requested": cov.requested,
        "read": cov.read,
        "ok": cov.ok,
        "missing": cov.missing,
        "skipped": cov.skipped,
        "truncated": cov.truncated,
        "binary": cov.binary,
        "stale": cov.stale,
        "lossy": cov.lossy,
        "no_match": cov.no_match,
        "deferred": cov.deferred,
        "not_inspected": list(cov.not_inspected),
        "notes": list(cov.notes),
    }


def build_read_envelope(
    report: Report,
    *,
    time_s: float = 30.0,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for r in report.reads:
        rng = list(r.range) if r.range else None
        items.append({
            "id": r.id,
            "kind": r.kind,
            "label": r.label,
            "status": r.status,
            "path": r.path,
            "range": rng,
            "hash": r.hash,
            "bytes_total": r.bytes_total,
            "bytes_shown": r.bytes_shown,
            "lines_total": r.lines_total,
            "lines_shown": r.lines_shown,
            "truncated": r.truncated,
            "exit_code": None,
            "elapsed_ms": r.meta.get("elapsed_ms"),
            "handle": r.handle,
            "artifact": r.artifact,
        })

    summary = dict(report.summary)
    if not summary:
        summary = {
            "files": len(report.reads),
            "bytes_shown": report.used_bytes,
        }

    return {
        "ok": report.ok,
        "tool": "batch_read",
        "mode": "survey" if report.mode == "survey" else "files",
        "cwd": report.cwd,
        "workspace": _format_workspace(report.workspace, report.cwd),
        "budget": _format_budget(
            report.budget_tokens,
            report.budget_bytes,
            time_s,
            report.used_bytes,
            used_tokens=report.budget_tokens if report.mode == "survey" else None,
        ),
        "items": items,
        "coverage": _format_coverage(report.coverage),
        "unknowns": list(report.unknowns),
        "summary": summary,
    }


def build_run_envelope(
    report: Report,
    *,
    time_s: float = 60.0,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for r in report.runs:
        items.append({
            "id": r.id,
            "kind": "command",
            "label": r.label,
            "status": r.status,
            "path": None,
            "range": None,
            "hash": None,
            "bytes_total": r.bytes_total,
            "bytes_shown": r.bytes_shown,
            "lines_total": None,
            "lines_shown": None,
            "truncated": r.truncated,
            "exit_code": r.exit_code,
            "elapsed_ms": r.elapsed_ms,
            "handle": None,
            "artifact": r.stdout_artifact or r.stderr_artifact,
        })

    summary = {
        "commands": len(report.runs),
        "ok": report.coverage.ok,
        "failed": report.coverage.failed,
        "timed_out": report.coverage.commands_timed_out,
        "skipped": report.coverage.skipped,
        "bytes_shown": report.used_bytes,
    }

    return {
        "ok": report.ok and (report.coverage.failed == 0),
        "tool": "batch_run",
        "mode": "commands",
        "cwd": report.cwd,
        "workspace": _format_workspace(report.workspace, report.cwd),
        "budget": _format_budget(
            report.budget_tokens,
            report.budget_bytes,
            time_s,
            report.used_bytes,
        ),
        "items": items,
        "coverage": _format_coverage(report.coverage),
        "unknowns": list(report.unknowns),
        "summary": summary,
    }


def build_edit_envelope(
    edit_report: EditReport,
    cwd: str,
    ws: Workspace,
    *,
    tokens: int = 8000,
    time_s: float = 60.0,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for idx, change in enumerate(edit_report.changes, start=1):
        items.append({
            "id": f"E{idx}",
            "kind": change.action,
            "label": "",
            "status": change.status,
            "path": change.path,
            "range": None,
            "hash": change.after_hash,
            "bytes_total": None,
            "bytes_shown": len(change.diff.encode("utf-8", errors="replace")),
            "lines_total": None,
            "lines_shown": None,
            "truncated": change.diff_truncated,
            "exit_code": None,
            "elapsed_ms": None,
            "handle": None,
            "artifact": change.diff_artifact,
        })

    for idx, v in enumerate(edit_report.verify, start=1):
        items.append({
            "id": f"V{idx}",
            "kind": "verify",
            "label": v.label,
            "status": v.status,
            "path": None,
            "range": None,
            "hash": None,
            "bytes_total": v.bytes_total,
            "bytes_shown": v.bytes_shown,
            "lines_total": None,
            "lines_shown": None,
            "truncated": v.truncated,
            "exit_code": v.exit_code,
            "elapsed_ms": v.elapsed_ms,
            "handle": None,
            "artifact": v.stdout_artifact or v.stderr_artifact,
        })

    used_bytes = sum(item["bytes_shown"] for item in items)
    cov = Coverage(
        requested=len(edit_report.changes),
        read=len(edit_report.changes),
        ok=sum(1 for c in edit_report.changes if c.status == "ok"),
        failed=len(edit_report.errors),
        bytes_shown=used_bytes,
    )

    summary = {
        "changes": len(edit_report.changes),
        "ok": edit_report.ok,
        "dry_run": edit_report.dry_run,
        "rolled_back": edit_report.rolled_back,
        "rollback_status": edit_report.rollback_status,
        "verify_runs": len(edit_report.verify),
    }

    return {
        "ok": edit_report.ok,
        "tool": "batch_edit",
        "mode": "transaction",
        "cwd": cwd,
        "workspace": _format_workspace(ws, cwd),
        "budget": _format_budget(tokens, tokens * 4, time_s, used_bytes),
        "items": items,
        "coverage": _format_coverage(cov),
        "unknowns": list(edit_report.errors),
        "summary": summary,
    }


def report_dict(report: Report) -> dict[str, Any]:
    if report.tool == "batch_run":
        return build_run_envelope(report)
    return build_read_envelope(report)


def edit_dict(report: EditReport, cwd: str = "", ws: Workspace | None = None) -> dict[str, Any]:
    return build_edit_envelope(report, cwd, ws or Workspace(root=cwd))


def coverage_dict(coverage: Coverage) -> dict[str, Any]:
    return _format_coverage(coverage)


def workspace_dict(workspace: Workspace) -> dict[str, Any]:
    return _format_workspace(workspace, workspace.root)

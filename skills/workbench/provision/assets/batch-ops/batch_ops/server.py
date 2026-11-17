"""FastMCP surface: exactly three budget-aware, evidence-oriented tools.

Exposes:
  - batch_read: read many files, slices, greps, git diffs, handles, or a whole-repo survey.
  - batch_run: execute commands concurrently with process-tree kills, slices, and failure-first output.
  - batch_edit: transactional multi-file edits with dry-run, atomic writes, verify, and rollback.

All tools return a BatchToolResult providing an agent-readable text report and a
machine-readable summary envelope in _meta["batch_ops/envelope"] (see BatchToolResult).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import model_validator

from .artifacts import ArtifactStore
from .budget import Budget, BudgetTracker, cap_tokens
from .safety import format_bytes
from .editor import apply_edits, fit_diffs
from .models import (
    build_edit_envelope,
    build_read_envelope,
    build_run_envelope,
)
from .reader import collect_coverage, read_batch, survey
from .render import render_edit_report, render_read_report, render_run_report
from .runner import run_commands
from .specs import (
    parse_edit_spec,
    parse_manifest,
    parse_new_file,
    parse_read_spec,
    parse_rename,
    parse_run_spec,
    parse_verify,
)
from .types import (
    Coverage,
    EditReport,
    EditRequestBundle,
    ReadRequest,
    Report,
    RunRequest,
    RunResult,
    Workspace,
)


ENVELOPE_META_KEY = "batch_ops/envelope"
# Specs stay loosely typed in the schema: the docstrings document them, and every tool
# schema is carried in the agent's context each turn. specs.py validates the shapes.
Spec = str | dict[str, Any]


class BatchToolResult(CallToolResult):
    """CallToolResult subclass that stringifies to its primary text report.

    The machine-readable envelope travels in ``_meta`` (key ``batch_ops/envelope``), not in
    ``structuredContent``: clients such as Claude Code show the model only structuredContent
    when it is present, which hid every file body, grep hit and command output in the text
    report. Read it with ``result.envelope``.
    """

    @model_validator(mode="before")
    @classmethod
    def _envelope_to_meta(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("structuredContent") is not None:
            data = dict(data)
            envelope = data.pop("structuredContent")
            meta = dict(data.pop("_meta", None) or data.pop("meta", None) or {})
            meta[ENVELOPE_META_KEY] = envelope
            data["_meta"] = meta
        return data

    @property
    def envelope(self) -> dict[str, Any]:
        return (self.meta or {}).get(ENVELOPE_META_KEY) or {}

    def __str__(self) -> str:
        if self.content and hasattr(self.content[0], "text"):
            return str(self.content[0].text)
        return super().__str__()


mcp = FastMCP(
    "batch-ops",
    instructions=(
        "Batch evidence tools for coding agents. batch_read gathers files, greps, git history "
        "or a repository map (mode='survey') in one turn; batch_run runs several commands with "
        "per-command timeouts, failures first; batch_edit applies several edits atomically with "
        "dry-run and rollback on verification failure. Your client may list these tools under "
        "prefixed names: call them by the names it lists. Reads and edits stay inside cwd unless "
        "allow_outside=true."
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _root(cwd: str | None) -> Path:
    raw = cwd or os.environ.get("BATCH_OPS_ROOT") or os.getcwd()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    if not path.exists():
        raise ValueError(f"cwd does not exist: {path}")
    if not path.is_dir():
        raise ValueError(f"cwd is not a directory: {path}")
    return path


def _unknown_budget_keys(budget_arg: dict[str, Any], allowed: tuple[str, ...]) -> None:
    extra = set(budget_arg) - set(allowed)
    if extra:
        raise ValueError(
            "budget: unknown key(s) " + ", ".join(sorted(extra)) + "; use " + ", ".join(allowed)
        )


def _resolve_budget(
    budget_arg: int | dict[str, Any] | None,
    item_count: int,
    *,
    tokens: int,
    item_tokens: int,
    time_s: float,
    max_output: int,
) -> tuple[Budget, BudgetTracker, float, str | None, int]:
    """Budget, tracker, time limit, a note when the request was clamped to the report cap, and max_output."""
    tok = tokens
    itok = item_tokens
    t_sec = time_s
    max_out = max_output
    if isinstance(budget_arg, int):
        tok = max(256, budget_arg)
    elif isinstance(budget_arg, dict):
        _unknown_budget_keys(budget_arg, ("tokens", "item_tokens", "time_s", "max_output"))
        if "tokens" in budget_arg:
            tok = max(256, int(budget_arg["tokens"]))
        if "item_tokens" in budget_arg:
            itok = max(64, int(budget_arg["item_tokens"]))
        if "time_s" in budget_arg:
            t_sec = max(0.5, float(budget_arg["time_s"]))
        if "max_output" in budget_arg:
            max_out = max(4096, int(budget_arg["max_output"]))
    asked = tok
    tok = cap_tokens(tok)
    itok = min(itok, tok)
    budget = Budget(tokens=tok, item_tokens=itok, time_s=t_sec, max_items=max(1, item_count))
    return budget, BudgetTracker(budget), t_sec, _cap_note(asked, tok), max(4096, max_out)


def _cap_note(asked_tokens: int, tokens: int) -> str | None:
    if asked_tokens <= tokens:
        return None
    return (f"budget capped at {format_bytes(tokens * 4)} so the client shows this report inline "
            f"(asked for {format_bytes(asked_tokens * 4)}); cut items name their continuation")


def _artifacts() -> ArtifactStore:
    store = ArtifactStore()
    try:
        store.cleanup()
    except Exception:
        pass
    return store


def _error_text(tool: str, exc: BaseException, hint: str = "") -> str:
    msg = f"# {tool} error\n{type(exc).__name__}: {exc}\n"
    if hint:
        msg += f"\nHint: {hint}\n"
    return msg


def _read_error(spec_index: int, exc: BaseException) -> ReadRequest:
    return ReadRequest(kind="invalid", label=f"spec {spec_index}", error=f"{type(exc).__name__}: {exc}")


def _run_error(spec_index: int, exc: BaseException) -> RunResult:
    return RunResult(
        id=f"run{spec_index}",
        label=f"spec {spec_index}",
        status="error",
        message=f"{type(exc).__name__}: {exc}",
        cmd_display="",
    )


# ---------------------------------------------------------------------------
# batch_read
# ---------------------------------------------------------------------------
@mcp.tool(
    annotations=ToolAnnotations(
        title="Batch read evidence",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
async def batch_read(
    specs: list[Spec] | None = None,
    cwd: str = ".",
    mode: Literal["files", "survey", "batch", "auto"] = "files",
    focus: list[str] | None = None,
    budget: int | dict[str, Any] | None = None,
    allow_outside: bool = False,
    ctx: Context | None = None,
) -> BatchToolResult:
    """Read files, ranges, blocks, outlines, greps, globs and git history in one call.

    cwd: absolute working directory. specs (strings): "a.txt" | "a.txt:10-50" | "a.txt@block:RE" |
    "a.txt@outline" | "a.txt@context:RE:3" | "a.txt@target:10-20" (verbatim edit search text) |
    "grep:RE" | "glob:src/**/*.txt" | "git:diff" | "git:changed" | "git:log:PATH[:N-M]" |
    "git:cochange:PATH" (files committed with PATH) | "artifact:NAME:N-M".
    Objects: {"path": p, "since": SHA} omits the body while the file keeps the sha an earlier
    read printed; {"grep": RE, "paths": [..], "exclude": [..], "context": 2, "ignore_case": true,
    "mode": "files"} ("files": per-file counts only); {"git": "diff", "base": REF, "paths": [..]};
    {"compare": [spec, spec]}. mode="survey" maps the repository. budget: tokens, or {"tokens",
    "item_tokens", "time_s", "max_output"}. A cut file read adds an indentation outline of its
    unshown lines, and the `next:` line lists specs to pass back to this tool as-is with the same
    cwd. allow_outside=true reads absolute paths outside cwd.
    """
    raw_specs = specs
    try:
        root = _root(cwd)
        store = _artifacts()
        budget_obj, tracker, actual_time_s, cap_note, max_output = _resolve_budget(
            budget, max(1, len(raw_specs or [])),
            tokens=10000, item_tokens=10000, time_s=30.0, max_output=65536,
        )
        max_bytes = budget_obj.bytes

        if mode == "survey" or (mode == "auto" and not raw_specs):
            if ctx:
                await ctx.report_progress(50, 100)
            report = survey(
                root,
                focus=focus,
                artifacts=store,
                max_bytes=max(1024, min(max_bytes, max_output) - 1024),  # room for coverage lines
            )
            if cap_note:
                report.coverage.notes.append(cap_note)
            text = render_read_report(report, max_bytes=max_bytes)
            envelope = build_read_envelope(report, time_s=actual_time_s)
            if ctx:
                await ctx.report_progress(100, 100)
            return BatchToolResult(
                content=[TextContent(type="text", text=text)],
                structuredContent=envelope,
                isError=False,
            )

        if mode not in ("files", "batch", "auto", "survey"):
            err_msg = (
                f"# batch_read error\nunknown mode: {mode}\n"
                "Expected mode='files' (default) or mode='survey'."
            )
            return BatchToolResult(
                content=[TextContent(type="text", text=err_msg)],
                structuredContent={"ok": False, "tool": "batch_read", "mode": mode, "error": f"unknown mode: {mode}"},
                isError=True,
            )

        if not raw_specs:
            err_msg = (
                "# batch_read error\nspecs must not be empty (or pass mode='survey' for a repository map)\n"
                "Example: specs=['src/app.txt:1-50']"
            )
            return BatchToolResult(
                content=[TextContent(type="text", text=err_msg)],
                structuredContent={"ok": False, "tool": "batch_read", "mode": mode, "error": "specs must not be empty"},
                isError=True,
            )

        spec_list: list[ReadRequest] = []
        for index, spec in enumerate(raw_specs, start=1):
            try:
                parsed = parse_read_spec(spec)
                if parsed.kind in ("file", "handle") and parsed.path is None and parsed.handle is None:
                    raise ValueError("read spec has neither path nor handle")
                if allow_outside:
                    for item in (parsed, *parsed.children):
                        item.allow_outside = True
                spec_list.append(parsed)
            except Exception as exc:
                spec_list.append(_read_error(index, exc))

        if ctx:
            await ctx.report_progress(10, 100)

        results = await read_batch(
            spec_list,
            root=root,
            tracker=tracker,
            artifacts=store,
            parallel=8,
            max_output=max_output,
        )

        if ctx:
            await ctx.report_progress(90, 100)

        report = Report(
            tool="batch_read",
            mode="files",
            cwd=str(root),
            workspace=Workspace(root=str(root)),
            budget_tokens=budget_obj.tokens,
            budget_bytes=max_bytes,
            reads=results,
            coverage=collect_coverage(len(results), results),
        )
        report.used_bytes = sum(result.bytes_shown for result in results)
        if cap_note:
            report.coverage.notes.append(cap_note)
        for result in results:
            if result.artifact:
                report.artifacts.append(result.artifact)
            if result.status in ("missing", "error", "stale", "binary", "skipped"):
                report.unknowns.append(f"{result.id}: {result.status}" + (f" ({result.path})" if result.path else ""))

        text = render_read_report(report, max_bytes=max_bytes)
        envelope = build_read_envelope(report, time_s=actual_time_s)
        if ctx:
            await ctx.report_progress(100, 100)

        return BatchToolResult(
            content=[TextContent(type="text", text=text)],
            structuredContent=envelope,
            isError=not report.ok,
        )
    except Exception as exc:
        err_text = _error_text(
            "batch_read",
            exc,
            hint="Specs accept string sugar ('src/app.txt:1-50') or objects ({'path': 'src/app.txt', 'range': '1-50'}).",
        )
        return BatchToolResult(
            content=[TextContent(type="text", text=err_text)],
            structuredContent={
                "ok": False,
                "tool": "batch_read",
                "mode": mode,
                "cwd": cwd,
                "error": str(exc),
                "items": [],
                "coverage": {"requested": 0, "read": 0, "ok": 0, "missing": 0, "skipped": 0, "truncated": 0, "binary": 0, "stale": 0, "lossy": 0, "not_inspected": [], "notes": [str(exc)]},
                "unknowns": [str(exc)],
                "summary": {},
            },
            isError=True,
        )


# ---------------------------------------------------------------------------
# batch_run
# ---------------------------------------------------------------------------
@mcp.tool(
    annotations=ToolAnnotations(
        title="Batch run commands",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=True,
    )
)
async def batch_run(
    commands: list[Spec] | None = None,
    cwd: str = ".",
    parallel: int = 4,
    fail_fast: bool = False,
    dry_run: bool = False,
    budget: int | dict[str, Any] | None = None,
    ctx: Context | None = None,
) -> BatchToolResult:
    """Run commands concurrently; failures are reported first.

    cwd: absolute working directory. commands: "@label: <cmd> ||| fails ||| tail:30" (slices:
    fails, head:N, tail:N, lines:N-M, grep:RE, grepv:RE, count, dedupe); {"cmd": "...",
    "timeout": 60, "cwd": "sub", "shell": "auto|cmd|powershell|bash|sh", "slices": ["tail:30"]};
    or {"argv": [...], "slices": [...]} (no shell). An object's cmd may end in " ||| " slices
    instead of "slices", not both. A timeout kills the process tree and keeps partial output.
    parallel=1 runs in order; fail_fast=true skips the rest after a failure; dry_run=true
    validates only. budget: tokens, or {"tokens", "item_tokens", "time_s", "max_output"}.
    Passing output keeps its last lines; cut output is kept as "artifact:NAME", which the read
    tool reads as "artifact:NAME:N-M".
    """
    raw_cmds = commands
    try:
        root = _root(cwd)
        store = _artifacts()
        if not raw_cmds:
            err_msg = (
                "# batch_run error\ncommands must not be empty\n"
                "Example: commands=['<test command> ||| fails']"
            )
            return BatchToolResult(
                content=[TextContent(type="text", text=err_msg)],
                structuredContent={"ok": False, "tool": "batch_run", "error": "commands must not be empty"},
                isError=True,
            )

        budget_obj, tracker, actual_time_s, cap_note, max_output = _resolve_budget(
            budget, len(raw_cmds),
            tokens=10000, item_tokens=10000, time_s=60.0, max_output=65536,
        )

        parsed: list[RunRequest] = []
        slots: list[RunResult | None] = [None] * len(raw_cmds)
        for index, spec in enumerate(raw_cmds):
            try:
                parsed.append(parse_run_spec(spec, index + 1, default_timeout=min(120.0, max(1.0, actual_time_s))))
            except Exception as exc:
                slots[index] = _run_error(index + 1, exc)

        # A command's own timeout wins over the batch time limit.
        longest = max((req.timeout for req in parsed), default=0.0)
        if longest > tracker.budget.time_s:
            tracker.budget.time_s = longest + 5

        if ctx:
            await ctx.report_progress(10, 100)

        results = await run_commands(
            parsed,
            root=root,
            tracker=tracker,
            artifacts=store,
            parallel=max(1, min(int(parallel), 16)),
            fail_fast=fail_fast,
            dry_run=dry_run,
            max_output=max_output,
        )

        valid_slots = [i for i, slot in enumerate(slots) if slot is None]
        for slot_index, result in zip(valid_slots, results):
            slots[slot_index] = result
        final = [
            slot or RunResult(id=f"run{i + 1}", label="", status="skipped", message="not run")
            for i, slot in enumerate(slots)
        ]

        coverage = Coverage(requested=len(final), read=len(final))
        if cap_note:
            coverage.notes.append(cap_note)
        for result in final:
            if result.status == "ok":
                coverage.ok += 1
            elif result.status == "timeout":
                coverage.commands_timed_out += 1
                coverage.failed += 1
            elif result.status == "error":
                coverage.commands_failed += 1
                coverage.failed += 1
            elif result.status == "skipped":
                coverage.skipped += 1
            if result.status in ("ok", "error", "timeout"):
                coverage.commands_run += 1
            coverage.bytes_shown += result.bytes_shown
            coverage.bytes_total += result.bytes_total

        report = Report(
            tool="batch_run",
            mode="commands",
            cwd=str(root),
            workspace=Workspace(root=str(root)),
            budget_tokens=budget_obj.tokens,
            budget_bytes=budget_obj.bytes,
            runs=final,
            coverage=coverage,
        )
        report.used_bytes = coverage.bytes_shown
        for result in final:
            if result.stdout_artifact:
                report.artifacts.append(result.stdout_artifact)
            if result.stderr_artifact:
                report.artifacts.append(result.stderr_artifact)
            if result.status == "skipped":
                report.unknowns.append(f"{result.id}: skipped ({result.message or 'not run'})")

        text = render_run_report(report, max_bytes=budget_obj.bytes)
        envelope = build_run_envelope(report, time_s=actual_time_s)
        if ctx:
            await ctx.report_progress(100, 100)

        is_error = (coverage.failed > 0)
        return BatchToolResult(
            content=[TextContent(type="text", text=text)],
            structuredContent=envelope,
            isError=is_error,
        )
    except Exception as exc:
        err_text = _error_text(
            "batch_run",
            exc,
            hint="Commands accept strings ('<test command> ||| fails') or objects ({'cmd': '...', 'timeout': 60}).",
        )
        return BatchToolResult(
            content=[TextContent(type="text", text=err_text)],
            structuredContent={
                "ok": False,
                "tool": "batch_run",
                "cwd": cwd,
                "error": str(exc),
                "items": [],
                "coverage": {"requested": 0, "read": 0, "ok": 0, "failed": 1, "missing": 0, "skipped": 0, "truncated": 0, "binary": 0, "stale": 0, "lossy": 0, "not_inspected": [], "notes": [str(exc)]},
                "unknowns": [str(exc)],
                "summary": {},
            },
            isError=True,
        )


# ---------------------------------------------------------------------------
# batch_edit
# ---------------------------------------------------------------------------
@mcp.tool(
    annotations=ToolAnnotations(
        title="Batch edit files atomically",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    )
)
async def batch_edit(
    edits: list[dict[str, Any]] | None = None,
    new_files: dict[str, str] | list[dict[str, Any]] | None = None,
    deletes: list[str] | None = None,
    renames: list[dict[str, Any]] | None = None,
    manifest: str | None = None,
    cwd: str = ".",
    dry_run: bool = False,
    full_diff: bool = False,
    verify: str | dict[str, Any] | None = None,
    rollback_on_failure: bool = True,
    overwrite: bool = False,
    normalize_eol: bool = False,
    allow_outside: bool = False,
    budget: int | dict[str, Any] | None = None,
    ctx: Context | None = None,
) -> BatchToolResult:
    """Apply edits, new files, deletes and renames atomically, then optionally verify.

    cwd: absolute working directory. edits: [{"path": p, "search": "exact old text", "replace":
    "new"}], search matching once unless "replace_all": true or "occurrence": N; new_files:
    {"path": "content"}; deletes: ["path"]; renames: [{"from": a, "to": b}]; manifest: a unified
    diff with repository-root paths. verify: "<cmd>" or {"cmd": "...", "timeout": 120}; on
    failure every file is restored. dry_run=true shows diffs without writing. Diffs show hunk
    headers and changed lines; full_diff=true or dry_run=true shows full diffs. budget: tokens.
    Copy search text from the read spec "path@target:N-M".
    """
    try:
        root = _root(cwd)
        store = _artifacts()
        ws = Workspace(root=str(root))
        spec_errors: list[str] = []

        budget_tok = 8000
        if isinstance(budget, int):
            budget_tok = budget
        elif isinstance(budget, dict):
            _unknown_budget_keys(budget, ("tokens",))
            if "tokens" in budget:
                budget_tok = int(budget["tokens"])
        asked_tok, budget_tok = budget_tok, cap_tokens(budget_tok)
        cap_note = _cap_note(asked_tok, budget_tok)

        edit_reqs = []
        for index, spec in enumerate(edits or [], start=1):
            try:
                edit_reqs.append(parse_edit_spec(spec))
            except Exception as exc:
                spec_errors.append(f"edit {index}: {type(exc).__name__}: {exc}")

        new_reqs = []
        if isinstance(new_files, dict):
            for path, content in new_files.items():
                try:
                    new_reqs.append(parse_new_file({"path": path, "content": content, "overwrite": overwrite}))
                except Exception as exc:
                    spec_errors.append(f"new file {path}: {type(exc).__name__}: {exc}")
        else:
            for index, spec in enumerate(new_files or [], start=1):
                try:
                    new_reqs.append(parse_new_file(spec))
                except Exception as exc:
                    spec_errors.append(f"new file {index}: {type(exc).__name__}: {exc}")

        delete_reqs: list[str] = []
        for index, path in enumerate(deletes or [], start=1):
            if not isinstance(path, str) or not path.strip():
                spec_errors.append(f"delete {index}: path must be a non-empty string")
            else:
                delete_reqs.append(path)

        rename_reqs = []
        for index, spec in enumerate(renames or [], start=1):
            try:
                rename_reqs.append(parse_rename(spec))
            except Exception as exc:
                spec_errors.append(f"rename {index}: {type(exc).__name__}: {exc}")

        verify_req = None
        if verify is not None:
            try:
                verify_req = parse_verify(verify)
            except Exception as exc:
                spec_errors.append(f"verify: {type(exc).__name__}: {exc}")

        if manifest:
            try:
                kind, manifest_edits, manifest_new = parse_manifest(manifest, str(root))
                if kind == "diff":
                    if edit_reqs or new_reqs or delete_reqs or rename_reqs:
                        spec_errors.append("manifest diff cannot be combined with edits/new_files/deletes/renames")
                else:
                    edit_reqs.extend(manifest_edits)
                    new_reqs.extend(manifest_new)
                    manifest = None
            except Exception as exc:
                spec_errors.append(f"manifest: {type(exc).__name__}: {exc}")
                manifest = None

        if not (edit_reqs or new_reqs or delete_reqs or rename_reqs or manifest):
            if not spec_errors:
                spec_errors.append("nothing to do: provide edits, new_files, deletes, renames or manifest")
            report = EditReport(ok=False, dry_run=dry_run, errors=spec_errors)
            text = render_edit_report(report, max_bytes=budget_tok * 4)
            envelope = build_edit_envelope(report, str(root), ws, tokens=budget_tok)
            return BatchToolResult(
                content=[TextContent(type="text", text=text)],
                structuredContent=envelope,
                isError=True,
            )

        bundle = EditRequestBundle(
            edits=edit_reqs,
            new_files=new_reqs,
            deletes=delete_reqs,
            renames=rename_reqs,
            manifest=manifest,
            cwd=str(root),
            dry_run=dry_run,
            verify=verify_req,
            rollback_on_failure=rollback_on_failure,
            overwrite=overwrite,
            normalize_eol=normalize_eol,
            allow_outside=allow_outside,
        )

        verify_timeout = verify_req.timeout if verify_req else 120.0
        tracker = BudgetTracker(
            Budget(
                tokens=max(1000, min(budget_tok, 4000)),
                item_tokens=4000,
                time_s=max(30.0, verify_timeout + 10),
                max_items=1,
            )
        )

        if ctx:
            await ctx.report_progress(10, 100)

        report = await apply_edits(
            bundle,
            root=root,
            artifacts=store,
            tracker=tracker,
            spec_errors=spec_errors,
        )

        if ctx:
            await ctx.report_progress(90, 100)

        fit_diffs(report, budget_tok * 4, store, condense=not (dry_run or full_diff))  # every file's status stays visible
        if cap_note:
            report.message = f"{report.message}; {cap_note}" if report.message else cap_note
        text = render_edit_report(report, max_bytes=budget_tok * 4)
        envelope = build_edit_envelope(report, str(root), ws, tokens=budget_tok)

        if ctx:
            await ctx.report_progress(100, 100)

        return BatchToolResult(
            content=[TextContent(type="text", text=text)],
            structuredContent=envelope,
            isError=not report.ok,
        )
    except Exception as exc:
        err_text = _error_text(
            "batch_edit",
            exc,
            hint="Specify edits as [{'path': '...', 'search': '...', 'replace': '...'}].",
        )
        return BatchToolResult(
            content=[TextContent(type="text", text=err_text)],
            structuredContent={
                "ok": False,
                "tool": "batch_edit",
                "cwd": cwd,
                "error": str(exc),
                "items": [],
                "coverage": {"requested": 0, "read": 0, "ok": 0, "failed": 1, "missing": 0, "skipped": 0, "truncated": 0, "binary": 0, "stale": 0, "lossy": 0, "not_inspected": [], "notes": [str(exc)]},
                "unknowns": [str(exc)],
                "summary": {},
            },
            isError=True,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()

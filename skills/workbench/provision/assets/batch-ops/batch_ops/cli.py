"""Command-line entry point for the batch engine.

Examples:
  python -m batch_ops read --survey
  python -m batch_ops read src/app.txt "grep:TODO" "git:changed"
  python -m batch_ops read --payload '[{"path":"src/app.txt","range":"1-40"}]' --json
  python -m batch_ops run "<test command> ||| fails:30" --time 120
  python -m batch_ops edit --payload '{"edits":[...],"dry_run":true}'
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from .artifacts import ArtifactStore
from .budget import Budget, BudgetTracker
from .editor import apply_edits, fit_diffs
from .models import build_edit_envelope, build_read_envelope, build_run_envelope, edit_dict, report_dict
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
)
from .workspace import workspace_info


def _load_json(value: str | None, path: str | None, what: str) -> Any:
    if value and path:
        raise SystemExit(f"use either --{what} or --{what}-file, not both")
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    if value:
        return json.loads(value)
    return None


def _read_specs(args: argparse.Namespace) -> list[Any]:
    specs: list[Any] = list(args.specs or [])
    payload = _load_json(args.payload, args.payload_file, "payload")
    if payload is not None:
        if not isinstance(payload, list):
            raise SystemExit("--payload must be a JSON array for read")
        specs.extend(payload)
    return specs


async def _cmd_read(args: argparse.Namespace, root: Path) -> tuple[str, dict[str, Any], bool]:
    store = ArtifactStore()
    store.cleanup()
    budget = Budget(tokens=args.tokens, item_tokens=args.item_tokens, time_s=args.time,
                    max_items=max(1, len(args.specs or []) + 64))
    if args.survey or args.mode == "survey":
        report = survey(root, focus=args.focus, max_files=args.max_files,
                        artifacts=store, max_bytes=min(budget.bytes, args.max_output))
        return render_read_report(report, max_bytes=budget.bytes), build_read_envelope(report, time_s=args.time), True

    raw = _read_specs(args)
    if not raw:
        raise SystemExit("read needs at least one spec, or --survey")
    tracker = BudgetTracker(budget)
    requests: list[ReadRequest] = []
    for index, spec in enumerate(raw, start=1):
        try:
            requests.append(parse_read_spec(spec))
        except Exception as exc:
            requests.append(ReadRequest(kind="invalid", label=f"spec {index}",
                                        error=f"{type(exc).__name__}: {exc}"))
    results = await read_batch(requests, root=root, tracker=tracker, artifacts=store,
                               parallel=args.parallel, max_output=args.max_output)
    report = Report(
        tool="batch_read", mode="files", cwd=str(root), workspace=workspace_info(root),
        budget_tokens=budget.tokens, budget_bytes=budget.bytes, reads=results,
        coverage=collect_coverage(len(results), results),
    )
    report.used_bytes = sum(result.bytes_shown for result in results)
    for result in results:
        if result.artifact:
            report.artifacts.append(result.artifact)
        if result.status in ("error", "missing", "stale", "binary", "skipped"):
            report.unknowns.append(f"{result.id}: {result.status}")
    ok = not any(r.status in ("error", "missing", "stale", "skipped") for r in results)
    return render_read_report(report, max_bytes=budget.bytes), build_read_envelope(report, time_s=args.time), ok


async def _cmd_run(args: argparse.Namespace, root: Path) -> tuple[str, dict[str, Any], bool]:
    store = ArtifactStore()
    store.cleanup()
    raw: list[Any] = list(args.commands or [])
    payload = _load_json(args.payload, args.payload_file, "payload")
    if payload is not None:
        if not isinstance(payload, list):
            raise SystemExit("--payload must be a JSON array for run")
        raw.extend(payload)
    if not raw:
        raise SystemExit("run needs at least one command")

    budget = Budget(tokens=args.tokens, item_tokens=args.item_tokens, time_s=args.time,
                    max_items=len(raw))
    tracker = BudgetTracker(budget)
    parsed: list[RunRequest] = []
    slots: list[RunResult | None] = [None] * len(raw)
    for index, spec in enumerate(raw):
        try:
            parsed.append(parse_run_spec(spec, index + 1, default_timeout=min(120.0, max(1.0, args.time))))
        except Exception as exc:
            slots[index] = RunResult(id=f"run{index + 1}", label=f"spec {index + 1}", status="error",
                                     message=f"{type(exc).__name__}: {exc}")
    results = await run_commands(parsed, root=root, tracker=tracker, artifacts=store,
                                 parallel=args.parallel, fail_fast=args.fail_fast,
                                 dry_run=args.dry_run, max_output=args.max_output)
    valid = [i for i, slot in enumerate(slots) if slot is None]
    for slot_index, result in zip(valid, results):
        slots[slot_index] = result
    final = [slot or RunResult(id=f"run{i + 1}", label="", status="skipped", message="not run")
             for i, slot in enumerate(slots)]

    coverage = Coverage(requested=len(final), read=len(final))
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
        tool="batch_run", mode="commands", cwd=str(root), workspace=workspace_info(root),
        budget_tokens=budget.tokens, budget_bytes=budget.bytes, runs=final, coverage=coverage,
    )
    report.used_bytes = coverage.bytes_shown
    for result in final:
        if result.stdout_artifact:
            report.artifacts.append(result.stdout_artifact)
        if result.stderr_artifact:
            report.artifacts.append(result.stderr_artifact)
    ok = all(result.status in ("ok", "skipped") for result in final)
    return render_run_report(report, max_bytes=budget.bytes), build_run_envelope(report, time_s=args.time), ok


async def _cmd_edit(args: argparse.Namespace, root: Path) -> tuple[str, dict[str, Any], bool]:
    payload = _load_json(args.payload, args.payload_file, "payload") or {}
    if not isinstance(payload, dict):
        raise SystemExit("--payload must be a JSON object for edit")
    if args.manifest_file:
        payload["manifest"] = Path(args.manifest_file).read_text(encoding="utf-8")
    if args.dry_run:
        payload["dry_run"] = True
    if args.verify:
        payload["verify"] = args.verify
    if args.no_rollback:
        payload["rollback_on_failure"] = False
    if args.overwrite:
        payload["overwrite"] = True
    if args.allow_outside:
        payload["allow_outside"] = True

    spec_errors: list[str] = []
    edit_reqs = []
    for index, spec in enumerate(payload.get("edits") or [], start=1):
        try:
            edit_reqs.append(parse_edit_spec(spec))
        except Exception as exc:
            spec_errors.append(f"edit {index}: {type(exc).__name__}: {exc}")
    new_reqs = []
    new_files = payload.get("new_files")
    if isinstance(new_files, dict):
        for path, content in new_files.items():
            try:
                new_reqs.append(parse_new_file({"path": path, "content": content}))
            except Exception as exc:
                spec_errors.append(f"new file {path}: {type(exc).__name__}: {exc}")
    else:
        for index, spec in enumerate(new_files or [], start=1):
            try:
                new_reqs.append(parse_new_file(spec))
            except Exception as exc:
                spec_errors.append(f"new file {index}: {type(exc).__name__}: {exc}")
    delete_reqs = []
    for index, path in enumerate(payload.get("deletes") or [], start=1):
        if not isinstance(path, str) or not path.strip():
            spec_errors.append(f"delete {index}: path must be a non-empty string")
        else:
            delete_reqs.append(path)
    rename_reqs = []
    for index, spec in enumerate(payload.get("renames") or [], start=1):
        try:
            rename_reqs.append(parse_rename(spec))
        except Exception as exc:
            spec_errors.append(f"rename {index}: {type(exc).__name__}: {exc}")
    verify_req = None
    if payload.get("verify") is not None:
        try:
            verify_req = parse_verify(payload["verify"])
        except Exception as exc:
            spec_errors.append(f"verify: {type(exc).__name__}: {exc}")

    manifest = payload.get("manifest")
    if manifest:
        try:
            kind, manifest_edits, manifest_new = parse_manifest(manifest, str(root))
            if kind == "diff":
                if edit_reqs or new_reqs or delete_reqs or rename_reqs:
                    spec_errors.append("manifest diff cannot be combined with other edits")
            else:
                edit_reqs.extend(manifest_edits)
                new_reqs.extend(manifest_new)
                manifest = None
        except Exception as exc:
            spec_errors.append(f"manifest: {type(exc).__name__}: {exc}")
            manifest = None

    ws = workspace_info(root)
    if not (edit_reqs or new_reqs or delete_reqs or rename_reqs or manifest):
        report = EditReport(ok=False, dry_run=bool(payload.get("dry_run")), errors=spec_errors or ["nothing to do"])
        return render_edit_report(report, max_bytes=args.tokens * 4, cwd=str(root)), build_edit_envelope(report, str(root), ws, tokens=args.tokens), False

    bundle = EditRequestBundle(
        edits=edit_reqs, new_files=new_reqs, deletes=delete_reqs, renames=rename_reqs,
        manifest=manifest, cwd=str(root), dry_run=bool(payload.get("dry_run", False)),
        verify=verify_req, rollback_on_failure=bool(payload.get("rollback_on_failure", True)),
        overwrite=bool(payload.get("overwrite", False)),
        normalize_eol=bool(payload.get("normalize_eol", getattr(args, "normalize_eol", False))),
        allow_outside=bool(payload.get("allow_outside", False)),
        max_files=int(payload.get("max_files", 100)),
    )
    tracker = BudgetTracker(Budget(tokens=4000, item_tokens=4000,
                                  time_s=max(30.0, (verify_req.timeout if verify_req else 120.0) + 10),
                                  max_items=1))
    store = ArtifactStore()
    report = await apply_edits(bundle, root=root, artifacts=store, tracker=tracker,
                               spec_errors=spec_errors)
    fit_diffs(report, args.tokens * 4, store)
    return (render_edit_report(report, max_bytes=args.tokens * 4, cwd=str(root)),
            build_edit_envelope(report, str(root), ws, tokens=args.tokens), report.ok)


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", "--cwd", dest="root", default=".", help="workspace root (default: current directory)")
    parser.add_argument("--tokens", type=int, default=8000, help="shared output budget in tokens")
    parser.add_argument("--item-tokens", type=int, default=2000, help="per-item output budget")
    parser.add_argument("--time", type=float, default=60.0, help="total deadline in seconds")
    parser.add_argument("--output", help="write the report to this file")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="batch_ops", description="Batch evidence tools for coding agents.")
    sub = parser.add_subparsers(dest="command", required=True)

    read = sub.add_parser("read", help="read files, grep, glob, git diff, compare or survey")
    _common(read)
    read.add_argument("specs", nargs="*", help="read specs (paths, grep:..., glob:..., git:diff, ...)")
    read.add_argument("--payload", help="JSON array of read specs")
    read.add_argument("--payload-file", help="path to a JSON array of read specs")
    read.add_argument("--mode", choices=["files", "survey", "batch", "auto"], default="files", help="read mode")
    read.add_argument("--survey", action="store_true", help="git-aware repository survey")
    read.add_argument("--focus", action="append", help="survey focus substring or glob (repeatable)")
    read.add_argument("--max-files", type=int, default=2000)
    read.add_argument("--max-output", type=int, default=65536, help="per item bytes")
    read.add_argument("--parallel", type=int, default=8)

    run = sub.add_parser("run", help="run commands concurrently")
    _common(run)
    run.add_argument("commands", nargs="*", help="command specs (string form or JSON objects)")
    run.add_argument("--payload", help="JSON array of command specs")
    run.add_argument("--payload-file", help="path to a JSON array of command specs")
    run.add_argument("--parallel", type=int, default=4)
    run.add_argument("--fail-fast", action="store_true")
    run.add_argument("--dry-run", action="store_true", help="validate specs without executing")
    run.add_argument("--max-output", type=int, default=65536, help="per command bytes")

    edit = sub.add_parser("edit", help="apply edits, creates, deletes and renames transactionally")
    _common(edit)
    edit.add_argument("--payload", help="JSON edit bundle")
    edit.add_argument("--payload-file", help="path to a JSON edit bundle")
    edit.add_argument("--manifest-file", help="path to a block or unified-diff manifest")
    edit.add_argument("--dry-run", action="store_true")
    edit.add_argument("--verify", help="verification command")
    edit.add_argument("--no-rollback", action="store_true")
    edit.add_argument("--overwrite", action="store_true")
    edit.add_argument("--normalize-eol", action="store_true", help="normalize mixed line endings")
    edit.add_argument("--allow-outside", action="store_true")

    serve = sub.add_parser("serve", help="start the MCP server over stdio")
    serve.add_argument("--transport", default="stdio", choices=["stdio", "sse", "streamable-http"])
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        from .server import mcp

        if args.transport == "stdio":
            mcp.run("stdio")
        else:
            mcp.settings.host = args.host
            mcp.settings.port = args.port
            mcp.run(args.transport)
        return 0

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2

    async def dispatch() -> tuple[str, dict[str, Any], bool]:
        if args.command == "read":
            return await _cmd_read(args, root)
        if args.command == "run":
            return await _cmd_run(args, root)
        return await _cmd_edit(args, root)

    try:
        text, data, ok = asyncio.run(dispatch())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(text, end="" if text.endswith("\n") else "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

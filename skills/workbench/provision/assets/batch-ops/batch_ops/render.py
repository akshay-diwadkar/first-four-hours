"""Human- and agent-readable report rendering.

Reports are deliberately plain text: stable IDs, explicit status words, exact
counts, and fenced bodies.  Nothing claims more coverage than it has.
"""

from __future__ import annotations

import json

from . import BUILD
from .safety import estimate_tokens, format_bytes, truncate_text
from .types import Coverage, EditReport, ReadResult, Report, RunResult


def _budget_line(report: Report) -> str:
    """Shown only when the budget cut something, so the agent knows a smaller batch reads more."""
    line = f"budget: used {format_bytes(report.used_bytes)}"
    return line + (f" of {format_bytes(report.budget_bytes)}" if report.budget_bytes else "")


def _coverage_lines(coverage: Coverage, *, counts: bool = True) -> list[str]:
    parts = []
    for label in ("failed", "missing", "skipped", "binary", "lossy", "stale", "truncated", "unchanged", "no_match"):
        value = getattr(coverage, label)
        if value:
            parts.append(f"{label} {value}")
    lines = ["coverage: " + ", ".join(parts)] if parts and counts else []
    if coverage.not_inspected:
        lines.append("not inspected:")
        lines.extend(f"  - {item}" for item in coverage.not_inspected)
    if coverage.notes:
        lines.extend(f"note: {note}" for note in coverage.notes)
    return lines


def _footer(all_refs: list[str], inline_refs: list[str | None]) -> list[str]:
    """The artifacts: footer, listing only references not already shown next to their item."""
    shown = {ref for ref in inline_refs if ref}
    rest = [ref for ref in dict.fromkeys(all_refs) if ref not in shown]
    return ["artifacts:", *(f"  - {ref}" for ref in rest)] if rest else []


def _fence(text: str) -> str:
    if not text:
        return "~~~\n(empty)\n~~~"
    return f"~~~\n{text}\n~~~"


def _read_status(result: ReadResult) -> str:
    if result.status == "ok":
        return "ok"
    return result.status


def _render_read_item(result: ReadResult) -> list[str]:
    bits = [f"[{result.id}] {_read_status(result)}"]
    if result.label:
        bits.append(result.label)
    if result.path:
        bits.append(result.path)
    head = " ".join(bits)
    detail: list[str] = []
    if result.range:
        detail.append(f"lines {result.range[0]}-{result.range[1]}")
    if result.kind == "grep":
        meta = result.meta or {}
        detail.append(f"{meta.get('matches', 0)} match(es) in {meta.get('files_with_hits', 0)} file(s)")
    elif result.lines_total is not None:
        detail.append(f"{result.lines_shown} of {result.lines_total} line(s)")
    if result.bytes_total is not None and result.kind in ("file", "handle"):
        detail.append(f"file {format_bytes(result.bytes_total)}")
    elif result.bytes_total is not None and result.truncated:
        detail.append(f"{format_bytes(result.bytes_shown)} of {format_bytes(result.bytes_total)}")
    if detail:
        head += " (" + ", ".join(detail) + ")"
    lines = [head]
    if result.message:
        lines.append(f"  {result.message}")
    if result.hash:
        lines.append(f"  sha: {result.hash[:12]}")
    meta = result.meta or {}
    encoding = str(meta.get("encoding") or "").lower()
    if (encoding and encoding not in ("utf-8", "ascii", "utf-8-sig")) or meta.get("mixed_eol") or meta.get("lossy"):
        lines.append(f"  encoding: {meta.get('encoding', '?')} / eol: {meta.get('eol', '?')}")
    if meta.get("matches") and result.kind != "grep":
        lines.append(f"  matches: {meta['matches']}")
    if meta.get("handles"):
        lines.append(f"  expanded handles: {len(meta['handles'])}")
        for entry in meta["handles"][:8]:
            lines.append(f"    {entry.get('path')}  {entry.get('handle')}")
    if meta.get("files") and isinstance(meta["files"], list):
        shown = ", ".join(str(p) for p in meta["files"][:10])
        lines.append(f"  files: {shown}" + (" ..." if len(meta["files"]) > 10 else ""))
    if result.artifact:
        lines.append(f"  artifact: {result.artifact}")
    lines.append(_fence(result.body))
    return lines


def _next_line(report: Report) -> str | None:
    """Every cut or misspelled item's continuation, as the specs to pass back to the read tool."""
    specs = [str(r.meta["continuation"]) for r in report.reads if r.meta and r.meta.get("continuation")]
    if not specs:
        return None
    line = f"next (read tool): specs={json.dumps(specs)}"
    if any(r.meta and r.meta.get("outside") and r.meta.get("continuation") for r in report.reads):
        line += " allow_outside=true"
    return line


def render_read_report(report: Report, *, max_bytes: int = 32 * 1024) -> str:
    lines = [f"# batch_read ({report.mode}) build {BUILD}"]
    if any(r.truncated and not (r.meta or {}).get("outline_first") for r in report.reads):
        lines.append(_budget_line(report))
    problems = [r for r in report.reads if r.status not in ("ok", "truncated", "lossy", "unchanged")]
    if problems:
        lines.append("problems: " + ", ".join(f"{r.id} {r.status}" for r in problems))
    next_line = _next_line(report)
    if next_line:
        lines.append(next_line)
    lines.append("")
    if report.reads:
        for result in report.reads:
            lines.extend(_render_read_item(result))
            lines.append("")
    elif report.body:
        lines.append(report.body)
        lines.append("")
    if report.coverage.requested or report.coverage.read:
        lines.extend(_coverage_lines(report.coverage))
    if report.unknowns:
        lines.append("unknowns:")
        lines.extend(f"  - {item}" for item in report.unknowns)
    lines.extend(_footer(report.artifacts, [r.artifact for r in report.reads]))
    text = "\n".join(lines).rstrip() + "\n"
    if report.mode == "survey" and report.body:
        text = f"# batch_read (survey) build {BUILD}\n" + report.body.rstrip() + "\n\n" + "\n".join(_coverage_lines(report.coverage)) + "\n"
        if report.artifacts:
            text += "artifacts:\n" + "\n".join(f"  - {item}" for item in dict.fromkeys(report.artifacts)) + "\n"
    return _finish(text, report, max_bytes)


def _run_status(result: RunResult) -> str:
    return result.status


def _render_run_item(result: RunResult) -> list[str]:
    bits = [f"[{result.id}]", _run_status(result)]
    if result.exit_code is not None:
        bits.append(f"exit {result.exit_code}")
    bits.append(f"{result.elapsed_ms}ms")
    bits.append(result.shell or "?")
    if result.label:
        bits.append(f"- {result.label}")
    lines = [" ".join(bits)]
    lines.append(f"  cmd: {result.cmd_display}")
    if result.cwd not in ("", "."):
        lines.append(f"  cwd: {result.cwd}")
    if result.message:
        lines.append(f"  {result.message}")
    if result.bytes_total and result.budget_cut:
        lines.append(f"  output: {format_bytes(result.bytes_shown)} shown of {format_bytes(result.bytes_total)}")
    if result.slice_errors:
        lines.extend(f"  slice error: {error}" for error in result.slice_errors)
    if result.stdout:
        lines.append("  stdout:")
        lines.append(_fence(result.stdout))
    if result.stderr:
        lines.append("  stderr:")
        lines.append(_fence(result.stderr))
    if not result.stdout and not result.stderr:
        lines.append("  (no output)")
    named = f"{result.message or ''}\n{result.stdout}\n{result.stderr}"
    if result.stdout_artifact and result.stdout_artifact not in named:
        lines.append(f"  stdout artifact: {result.stdout_artifact}")
    if result.stderr_artifact and result.stderr_artifact not in named:
        lines.append(f"  stderr artifact: {result.stderr_artifact}")
    return lines


def render_run_report(report: Report, *, max_bytes: int = 64 * 1024) -> str:
    lines = [f"# batch_run build {BUILD}"]
    runs = report.runs
    if any(r.budget_cut for r in runs):
        lines.append(_budget_line(report))
    failed = [r for r in runs if r.status in ("error", "timeout")]
    others = [r for r in runs if r.status not in ("error", "timeout")]
    summary = f"{len(runs)} command(s): {sum(1 for r in runs if r.status == 'ok')} ok, {len(failed)} failed/timed out"
    if any(r.status == "skipped" for r in runs):
        summary += f", {sum(1 for r in runs if r.status == 'skipped')} skipped"
    lines.append(summary)
    if failed:
        lines.append("failure-first: " + ", ".join(f"{r.id} ({r.status})" for r in failed))
    lines.append("")
    for result in [*failed, *others]:
        lines.extend(_render_run_item(result))
        lines.append("")
    lines.extend(_coverage_lines(report.coverage, counts=False))
    if report.unknowns:
        lines.append("unknowns:")
        lines.extend(f"  - {item}" for item in report.unknowns)
    lines.extend(_footer(report.artifacts, [a for r in runs for a in (r.stdout_artifact, r.stderr_artifact)]))
    return _finish("\n".join(lines).rstrip() + "\n", report, max_bytes)


def _render_edit(report: EditReport) -> list[str]:
    lines: list[str] = []
    for result in report.verify:
        lines.extend(_render_run_item(result))
        lines.append("")
    return lines


def render_edit_report(report: EditReport, *, max_bytes: int = 32 * 1024) -> str:
    lines = [f"# batch_edit{' (dry run)' if report.dry_run else ''}" + (" - ok" if report.ok else " - failed")
             + f" build {BUILD}"]
    if report.message:
        lines.append(report.message)
    if report.errors:
        lines.append("errors:")
        lines.extend(f"  - {error}" for error in report.errors)
    if report.changes:
        counts: dict[str, int] = {}
        for change in report.changes:
            counts[change.status] = counts.get(change.status, 0) + 1
        names = {"ok": "ok", "error": "error", "rolled_back": "rolled back", "skipped": "skipped"}
        tally = ", ".join(f"{n} {names.get(s, s)}" for s, n in counts.items() if n)
        lines.append(f"changes: {len(report.changes)} ({tally})")
        for change in report.changes:
            marker = {"modify": "M", "create": "C", "delete": "D", "rename": "R"}.get(change.action, "?")
            head = f"  [{marker}] {change.path}"
            if change.destination:
                head += f" -> {change.destination}"
            head += f"  ({change.status}"
            if change.replacements:
                head += f", {change.replacements} replacement(s)"
            head += ")"
            lines.append(head)
            if change.before_hash or change.after_hash:
                lines.append(
                    f"      hash {str(change.before_hash or '-')[:12]} -> {str(change.after_hash or '-')[:12]}"
                )
            if change.message:
                lines.append(f"      {change.message}")
            if change.diff_artifact:
                lines.append(f"      full diff (read tool): \"{change.diff_artifact}\"")
            if change.diff:
                lines.append(_fence(change.diff))
    else:
        lines.append("no changes")
    if report.verify:
        lines.append("verification:")
        for result in report.verify:
            lines.extend("  " + line if line else line for line in _render_run_item(result))
    if report.rolled_back:
        lines.append(f"rolled back: {report.rollback_status}")
    inline = [c.diff_artifact for c in report.changes]
    inline += [a for r in report.verify for a in (r.stdout_artifact, r.stderr_artifact)]
    lines.extend(_footer(report.artifacts, inline))
    return _finish("\n".join(lines).rstrip() + "\n", None, max_bytes)


def render_report(report: Report, *, max_bytes: int = 64 * 1024) -> str:
    if report.tool == "batch_run":
        return render_run_report(report, max_bytes=max_bytes)
    if report.tool == "batch_edit":
        return render_edit_report(report.edit or EditReport(), max_bytes=max_bytes)
    if report.tool == "batch_read" and report.mode == "survey":
        return render_read_report(report, max_bytes=max_bytes)
    return render_read_report(report, max_bytes=max_bytes)


def _finish(text: str, report: Report | None, max_bytes: int) -> str:
    text, truncated, _ = truncate_text(text, max_bytes, style="head_tail")
    if truncated:
        text += f"\n[... report truncated at {format_bytes(max_bytes)}; narrow the request for full detail]"
    if report is not None:
        report.used_bytes = len(text.encode("utf-8", errors="replace"))
        report.budget_tokens = estimate_tokens(text)
    return text

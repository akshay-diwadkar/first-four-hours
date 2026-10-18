#!/usr/bin/env python3
"""Atomically seal the sole scope handoff artifact (ticket-scope.md)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from check_issue_plan import (
    HandoffContractError,
    _escape_untrusted_metadata,
    canonical_body,
    load_contract,
    parse_metadata,
    validate_plan,
)
from _skill_protocol_runtime import compatible_version_pattern
from github_common import TICKET_VERSION
import scope_workspace

RECEIPT_RE = re.compile(rf"^<!-- ticket-scope: {compatible_version_pattern(TICKET_VERSION)}; sha256: ([0-9a-f]{{64}}) -->$")
SKILL_ROOT = Path(__file__).resolve().parents[1]


def _receipt_free(text: str) -> str:
    head, separator, final = text.removesuffix("\n").rpartition("\n")
    match = RECEIPT_RE.fullmatch(final.strip())
    if match is None:
        body = text
    else:
        body = head + "\n"
        if not separator or hashlib.sha256(body.encode("utf-8")).hexdigest() != match.group(1):
            raise ValueError("ticket-scope receipt does not match content")
    untrusted = False
    for line in body.splitlines():
        if "<!-- ticket: untrusted-begin -->" in line:
            untrusted = True
        if not untrusted and line.startswith("<!-- ticket-scope: "):
            raise ValueError("ticket-scope receipt must appear once, as the final line")
        if "<!-- ticket: untrusted-end -->" in line:
            untrusted = False
    return body


def _fail(message: str, code: str = "ticket-scope.invalid") -> int:
    from _diagnostic_contract import Diagnostic

    diagnostic = Diagnostic(
        code=code, message=message, skill="ticket", phase="run", artifact="ticket-scope.md", path="."
    ).to_dict()
    print(json.dumps({"valid": False, "diagnostics": [diagnostic]}, sort_keys=True, separators=(",", ":")))
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--issue-json", type=Path, required=True)
    parser.add_argument("--scope-inputs", type=Path, required=True)
    parser.add_argument("--draft", type=Path, required=True)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    try:
        draft_text = _receipt_free(args.draft.read_text(encoding="utf-8"))
        snapshot_bytes = Path(args.issue_json).read_bytes()
        inputs_bytes = Path(args.scope_inputs).read_bytes()
        draft_bytes = draft_text.encode("utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        return _fail(str(exc), "handoff.invalid")
    try:
        trusted_draft = _escape_untrusted_metadata(draft_text, load_contract())
    except HandoffContractError as exc:
        return _fail(str(exc))
    try:
        payload = json.loads(snapshot_bytes.decode("utf-8"))
        inputs = json.loads(inputs_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        return _fail(str(exc))
    if not isinstance(inputs, dict) or inputs.get("backend") not in ("github", "local"):
        return _fail("scope_inputs.backend must be github or local")
    local = isinstance(inputs, dict) and inputs.get("backend") == "local"
    snapshot_meta = payload.get("metadata") if isinstance(payload, dict) else None
    if local != (isinstance(snapshot_meta, dict) and snapshot_meta.get("backend") == "local"):
        return _fail("snapshot backend does not match scope_inputs.backend")
    try:
        selected = parse_metadata(trusted_draft).get("work_item")
        selected = selected if (isinstance(selected, str) if local else isinstance(selected, int)) else None
    except ValueError:
        selected = None
    if local:
        try:
            import fetch_local_issues

            verify_result = fetch_local_issues.verify_local(repo_root, payload, inputs, selected)
        except Exception as exc:
            from github_common import ConfigError as _LocalConfigError

            if isinstance(exc, _LocalConfigError):
                return _fail(str(exc))
            return _fail(str(exc), "local.unavailable")
    else:
        try:
            import fetch_github_issues as fetch_mod
            import github_common

            client = github_common.GitHubClient()
            client.preflight()
            verify_result = fetch_mod.verify_readset(client, payload, inputs, selected)
        except Exception as exc:
            from github_common import ConfigError as _ConfigError

            if isinstance(exc, _ConfigError):
                return _fail(str(exc))
            return _fail(str(exc), "github.unavailable")
    if not verify_result.get("fresh"):
        return _fail(
            f"remote verification is stale: {json.dumps(verify_result.get('stale', []))[:800]}", "handoff.stale"
        )
    errors = validate_plan(args.draft, args.issue_json, args.repo_root, args.scope_inputs)
    if errors:
        from _diagnostic_contract import Diagnostic

        diagnostics = [
            Diagnostic(
                code="ticket-scope.invalid",
                message=item,
                skill="ticket",
                phase="run",
                artifact="ticket-scope.md",
                path=".",
            ).to_dict()
            for item in errors
        ]
        print(json.dumps({"valid": False, "diagnostics": diagnostics}, sort_keys=True, separators=(",", ":")))
        return 1
    try:
        metadata = parse_metadata(trusted_draft)
    except ValueError as exc:
        return _fail(str(exc))
    status = metadata.get("status")
    work_item = metadata.get("work_item")
    slug = scope_workspace.scope_slug(inputs, work_item) if work_item is not None else None
    if status != "plan-ready":
        removed = None
        if slug is not None:
            try:
                stale = scope_workspace.existing_handoff(repo_root, slug)
                if stale is not None:
                    stale.unlink()
                    removed = str(stale)
            except (scope_workspace.WorkspaceError, OSError, subprocess.SubprocessError) as exc:
                return _fail(str(exc), "output.unsafe")
        explanation = ""
        for field in ("blockers", "questions", "unknowns", "close_evidence", "decomposition_reason"):
            value = metadata.get(field)
            if value:
                explanation = json.dumps(value)[:500]
                break
        print(
            json.dumps(
                {"status": status, "work_item": work_item, "explanation": explanation, "path": None, "removed": removed},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    try:
        destination = scope_workspace.prepare_workspace(repo_root, slug)
    except (scope_workspace.WorkspaceError, OSError, subprocess.SubprocessError) as exc:
        return _fail(str(exc), "output.unsafe")
    for other in (args.draft.resolve(), args.issue_json.resolve(), args.scope_inputs.resolve()):
        if destination.resolve() == other:
            return _fail("output destination aliases an input file", "output.unsafe")
    # Derive reserved bindings from validated inputs/snapshot/checkout/evidence.
    try:
        inputs = json.loads(inputs_bytes.decode("utf-8"))
        payload = json.loads(snapshot_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        return _fail(str(exc))
    # Collect evidence paths from the draft's Current evidence section.
    evidence_paths: list[str] = []
    for line in draft_text.splitlines():
        m = re.match(r"^\s*[-*]\s*`([^`]+):(\d+)`\s*\|\s*anchor:\s*`[^`]+`\s*\|\s*observation:\s*.+$", line)
        if m:
            evidence_paths.append(m.group(1))
    try:
        from check_issue_plan import derive_reserved as _derive

        source, checkout = _derive(inputs, payload, repo_root, evidence_paths, metadata.get("work_item"))
    except Exception as exc:
        return _fail(str(exc))
    # Keep the authored metadata in place and write the reserved bindings as the trailing footer.
    from check_issue_plan import BINDINGS_RE, METADATA_RE

    canonical_meta = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
    m = METADATA_RE.search(trusted_draft)
    assert m is not None
    rendered = trusted_draft[: m.start("json")] + canonical_meta + trusted_draft[m.end("json") :]
    bindings = json.dumps({"checkout": checkout, "inputs": inputs, "source": source}, sort_keys=True, separators=(",", ":"))
    footer = f"<!-- ticket-scope-bindings -->\n```json\n{bindings}\n```"
    existing = BINDINGS_RE.search(rendered)
    if existing is not None:
        rendered = rendered[: existing.start()] + footer + rendered[existing.end() :]
    else:
        rendered = rendered.rstrip("\n") + "\n\n" + footer + "\n"
    body = canonical_body(rendered)
    # Verify bound bytes have not changed before atomic replacement.
    try:
        if Path(args.issue_json).read_bytes() != snapshot_bytes or Path(args.scope_inputs).read_bytes() != inputs_bytes:
            return _fail("inputs changed during sealing; reacquire and retry", "handoff.stale")
        current_draft = _receipt_free(args.draft.read_text(encoding="utf-8"))
        if current_draft.encode("utf-8") != draft_bytes:
            return _fail("draft changed during sealing; reacquire and retry", "handoff.stale")
    except (OSError, UnicodeError, ValueError) as exc:
        return _fail(str(exc))
    # Re-validate the rendered body (reserved bindings must verify).
    import tempfile as _tf

    with _tf.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as fh:
        fh.write(body)
        tmp_rendered = Path(fh.name)
    try:
        re_errors = validate_plan(tmp_rendered, args.issue_json, args.repo_root, args.scope_inputs)
    finally:
        tmp_rendered.unlink(missing_ok=True)
    if re_errors:
        from _diagnostic_contract import Diagnostic as _ReDiagnostic

        diagnostics = [
            _ReDiagnostic(
                code="ticket-scope.invalid",
                message=item,
                skill="ticket",
                phase="run",
                artifact="ticket-scope.md",
                path=".",
            ).to_dict()
            for item in re_errors
        ]
        print(json.dumps({"valid": False, "diagnostics": diagnostics}, sort_keys=True, separators=(",", ":")))
        return 1
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    sealed = body + f"<!-- ticket-scope: {TICKET_VERSION}; sha256: {digest} -->\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=destination.parent, delete=False) as tmp:
        tmp.write(sealed)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    try:
        os.replace(tmp_path, destination)
    finally:
        tmp_path.unlink(missing_ok=True)
    print(json.dumps({"ignored": True, "path": str(destination), "status": "sealed"}, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

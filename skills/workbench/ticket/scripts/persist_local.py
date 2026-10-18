#!/usr/bin/env python3
"""Plan and publish one local Markdown Ticket package under one explicit repository-local store.

``plan`` reads only the store's top-level managed records and classifies each planned record as
``create`` or ``existing`` without writing. ``publish`` requires confirmation, rechecks that
reviewed plan, creates each missing record without overwriting anything, and reads it back.
Existing records are never rewritten. Local mode never constructs a GitHub client.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from _diagnostic_contract import Diagnostic
from compile_persist import LOCAL_ID_RE, render_preview
from _skill_protocol_runtime import compatible_version
from github_common import TICKET_VERSION, contract_matches
from reconcile_github import _emit, _write_atomic, issue_content

PLAN_CONTRACT = {"skill": "ticket", "branch": "persist", "artifact": "local-reconciliation", "version": TICKET_VERSION}
RESULT_CONTRACT = {"skill": "ticket", "branch": "persist", "artifact": "local-publication", "version": TICKET_VERSION}
MARKER_PREFIX = "<!-- ticket-item: "
MARKER_SUFFIX = " -->"
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
DRIFT_ACTION = "Start a new run to plan against the current store."

CODE_RULES: dict[str, tuple[str, str]] = {
    "persist.local_confirmation_premature": (
        "contract_contradiction",
        "Do not supply publish_confirmation before publication review; start a new run without it.",
    ),
    "persist.local_input_unsupported": (
        "contract_contradiction",
        "`label` and `github_repo_url` apply only to backend=github; start a new run without them.",
    ),
    "persist.publish_unconfirmed": (
        "contract_contradiction",
        "Publish only from publication review with publish_confirmation=yes after reading reconciliation.json.",
    ),
    "persist.local_unreadable": (
        "missing_evidence",
        "Make the named run file readable, then run next again.",
    ),
    "persist.local_backend_mismatch": (
        "contract_contradiction",
        "Start a new run whose persist_input backend and protocol backend are both local.",
    ),
    "persist.local_preview_stale": (
        "stale_evidence",
        "preview.json is not the canonical compile output of persist_input; start a new run to recompile it.",
    ),
    "persist.local_store_unsafe": (
        "unsafe_state",
        "Name a local_store directory inside the repository, below its root, that is not a file.",
    ),
    "persist.local_store_malformed": (
        "malformed_input",
        "Repair the named record's ticket-item metadata line or remove the duplicate id, then start a new run.",
    ),
    "persist.local_record_conflict": (
        "unsafe_state",
        "Persisted records are durable truth: edit the named record directly or choose new ids in a new run; "
        "never re-persist an edited package over them.",
    ),
    "persist.local_plan_drift": ("stale_evidence", DRIFT_ACTION),
    "persist.local_write_failed": (
        "unsafe_state",
        "Records already created stay; repair the named cause, then run next again to resume.",
    ),
    "persist.local_output_unwritable": (
        "unavailable_prerequisite",
        "Records already created stay; make the run directory writable, then run next again to resume.",
    ),
}


class Rejection(Exception):
    def __init__(self, diagnostics: list[dict[str, Any]]) -> None:
        super().__init__("local persistence rejected")
        self.diagnostics = diagnostics


def _diag(
    code: str,
    message: str,
    *,
    phase: str,
    artifact: str,
    path: Path | str,
    field: str | None = None,
) -> dict[str, Any]:
    category, action = CODE_RULES[code]
    return Diagnostic(
        code=code,
        message=message,
        category=category,
        skill="ticket",
        phase=phase,
        artifact=artifact,
        field=field,
        path=str(path),
        required_action=action,
        valid_repairs=(action,),
        supporting_evidence=(message,),
    ).to_dict()


def _relative(path: Path, repo: Path) -> str:
    return Path(os.path.relpath(path, repo)).as_posix()


def _bind(args: argparse.Namespace, phase: str) -> tuple[dict[str, Any], str, str, Path, Path]:
    """Validate inputs, preview freshness, and store containment; returns preview, sha, store name, store, repo."""

    def reject(code: str, message: str, *, artifact: str, path: Path | str, field: str | None = None) -> Rejection:
        return Rejection([_diag(code, message, phase=phase, artifact=artifact, path=path, field=field)])

    if args.label or args.github_repo is not None:
        raise reject(
            "persist.local_input_unsupported",
            "label or github_repo_url was supplied for backend=local",
            artifact="reconciliation.json" if phase == "reconcile" else "publication-result.json",
            path=args.output,
        )
    if phase == "reconcile":
        if args.publish_confirmation is not None:
            raise reject(
                "persist.local_confirmation_premature",
                "publish_confirmation was supplied before publication review",
                artifact="reconciliation.json",
                path=args.output,
                field="publish_confirmation",
            )
    elif args.publish_confirmation != "yes":
        raise reject(
            "persist.publish_unconfirmed",
            "publish_confirmation=yes was not supplied",
            artifact="publication-result.json",
            path=args.output,
        )

    raw: dict[str, bytes] = {}
    for name, path in (("persist_input", args.persist_input), ("preview", args.preview)):
        try:
            raw[name] = Path(path).read_bytes()
        except OSError as exc:
            raise reject(
                "persist.local_unreadable", f"cannot read {Path(path).name}: {exc}", artifact=Path(path).name, path=path
            ) from exc
    try:
        preview = json.loads(raw["preview"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        preview = None
    if not isinstance(preview, dict) or preview.get("backend") != "local":
        raise reject(
            "persist.local_backend_mismatch",
            "preview.json is not a backend=local persist preview",
            artifact="preview.json",
            path=args.preview,
        )
    try:
        rendered, _ = render_preview(json.loads(raw["persist_input"].decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError):
        rendered = None
    if rendered is None or rendered.encode("utf-8") != raw["preview"]:
        raise reject(
            "persist.local_preview_stale",
            "preview.json does not equal the canonical compile output of persist_input",
            artifact="preview.json",
            path=args.preview,
        )

    repo = Path(args.repo_root).resolve(strict=True)
    local_store = preview["local_store"]
    store = (repo / local_store).resolve()
    if store == repo or not store.is_relative_to(repo) or (store.exists() and not store.is_dir()):
        raise reject(
            "persist.local_store_unsafe",
            f"local_store '{local_store}' does not resolve to a directory below the repository root",
            artifact="preview.json",
            path=args.preview,
            field="local_store",
        )
    return preview, hashlib.sha256(raw["preview"]).hexdigest(), local_store, store, repo


def _planned(preview: dict[str, Any], sha: str) -> list[dict[str, Any]]:
    """Every record this package persists, in write order: root first, dependencies before dependents."""

    content = issue_content(preview)
    epic_id = preview.get("epic_id") if preview["shape"] == "epic" else None
    entries: list[tuple[str, str, str | None, list[str], dict[str, str]]] = []
    if epic_id is not None:
        entries.append((epic_id, "epic", None, [], content["epic"]))
    remaining = list(preview["work_items"])
    placed: set[str] = set()
    while remaining:
        item = next(item for item in remaining if all(dep in placed for dep in item.get("dependencies", [])))
        remaining.remove(item)
        placed.add(item["id"])
        entries.append((item["id"], "issue", epic_id, list(item.get("dependencies", [])), content[f"item {item['id']}"]))

    planned: list[dict[str, Any]] = []
    for rid, kind, parent, depends_on, record in entries:
        payload = f"# {record['title']}\n\n{record['body']}"
        meta = {
            "version": TICKET_VERSION,
            "id": rid,
            "kind": kind,
            "state": "open",
            "parent": parent,
            "depends_on": depends_on,
            "package": sha,
            "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        }
        text = (
            MARKER_PREFIX
            + json.dumps(meta, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            + MARKER_SUFFIX
            + "\n"
            + payload
        )
        planned.append({"id": rid, "kind": kind, "parent": parent, "depends_on": depends_on, "meta": meta, "text": text})
    return planned


def _valid_meta(meta: Any) -> bool:
    return (
        isinstance(meta, dict)
        and compatible_version(meta.get("version"), TICKET_VERSION)
        and isinstance(meta.get("id"), str)
        and LOCAL_ID_RE.fullmatch(meta["id"]) is not None
        and meta.get("kind") in ("issue", "epic")
        and meta.get("state") in ("open", "closed")
        and (meta.get("parent") is None or isinstance(meta.get("parent"), str))
        and isinstance(meta.get("depends_on"), list)
        and all(isinstance(dep, str) for dep in meta["depends_on"])
        and isinstance(meta.get("package"), str)
        and HEX64_RE.fullmatch(meta["package"]) is not None
        and isinstance(meta.get("payload_sha256"), str)
        and HEX64_RE.fullmatch(meta["payload_sha256"]) is not None
    )


def _scan(store: Path, phase: str) -> tuple[dict[str, tuple[Path, dict[str, Any]]], set[str]]:
    """Read the store's top-level managed records; unmanaged files are only names for collision checks."""

    if not store.exists():
        return {}, set()
    names = {entry.name.lower() for entry in store.iterdir()}
    records: dict[str, tuple[Path, dict[str, Any]]] = {}
    diagnostics: list[dict[str, Any]] = []

    def malformed(path: Path, message: str) -> None:
        diagnostics.append(
            _diag("persist.local_store_malformed", message, phase=phase, artifact=path.name, path=path)
        )

    for path in sorted(store.iterdir()):
        if not path.name.endswith(".md") or path.name.startswith(".") or not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError as exc:
            malformed(path, f"cannot read {path.name}: {exc}")
            continue
        raw = raw.removeprefix(b"\xef\xbb\xbf")
        first = raw.split(b"\n", 1)[0].rstrip(b"\r")
        if not first.startswith(MARKER_PREFIX.encode("ascii")):
            continue
        try:
            line = first.decode("utf-8")
        except UnicodeDecodeError:
            malformed(path, f"{path.name} ticket-item metadata is not UTF-8")
            continue
        meta: Any = None
        if line.endswith(MARKER_SUFFIX):
            try:
                meta = json.loads(line[len(MARKER_PREFIX) : -len(MARKER_SUFFIX)])
            except json.JSONDecodeError:
                meta = None
        if not _valid_meta(meta):
            malformed(path, f"{path.name} has malformed ticket-item metadata")
            continue
        if meta["id"] in records:
            malformed(path, f"{path.name} repeats record id '{meta['id']}' from {records[meta['id']][0].name}")
            continue
        records[meta["id"]] = (path, meta)
    if diagnostics:
        raise Rejection(diagnostics)
    return records, names


def _classify(
    planned: list[dict[str, Any]],
    records: dict[str, tuple[Path, dict[str, Any]]],
    names: set[str],
    store: Path,
    repo: Path,
    phase: str,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for record in planned:
        rid = record["id"]
        if rid in records:
            path, meta = records[rid]
            planned_meta = record["meta"]
            if (
                meta["package"] != planned_meta["package"]
                or meta["kind"] != record["kind"]
                or meta["payload_sha256"] != planned_meta["payload_sha256"]
            ):
                conflicts.append(
                    _diag(
                        "persist.local_record_conflict",
                        f"record '{rid}' in {path.name} belongs to another package or differs from this one",
                        phase=phase,
                        artifact=path.name,
                        path=path,
                    )
                )
                continue
            action = "existing"
            relations_changed = meta["parent"] != record["parent"] or meta["depends_on"] != record["depends_on"]
        elif f"{rid}.md".lower() in names:
            path = store / f"{rid}.md"
            conflicts.append(
                _diag(
                    "persist.local_record_conflict",
                    f"{rid}.md already exists in the store and is not record '{rid}' of this package",
                    phase=phase,
                    artifact=f"{rid}.md",
                    path=path,
                )
            )
            continue
        else:
            path = store / f"{rid}.md"
            adopted = sorted(
                other.name
                for other, other_meta in records.values()
                if other_meta["package"] != record["meta"]["package"]
                and (other_meta["parent"] == rid or rid in other_meta["depends_on"])
            )
            if adopted:
                conflicts.append(
                    _diag(
                        "persist.local_record_conflict",
                        f"new record '{rid}' would become the parent or dependency of {', '.join(adopted)} "
                        "from another package",
                        phase=phase,
                        artifact=f"{rid}.md",
                        path=path,
                    )
                )
                continue
            action = "create"
            relations_changed = False
        entries.append(
            {
                "id": rid,
                "kind": record["kind"],
                "action": action,
                "path": _relative(path, repo),
                "parent": record["parent"],
                "depends_on": record["depends_on"],
                "relations_changed": relations_changed,
            }
        )
    if conflicts:
        raise Rejection(conflicts)
    return entries


def plan(args: argparse.Namespace) -> int:
    preview, sha, local_store, store, repo = _bind(args, "reconcile")
    records, names = _scan(store, "reconcile")
    entries = _classify(_planned(preview, sha), records, names, store, repo, "reconcile")
    artifact = {
        "contract": PLAN_CONTRACT,
        "backend": "local",
        "local_store": local_store,
        "preview_sha256": sha,
        "status": "ready",
        "records": entries,
    }
    _write_atomic(Path(args.output), json.dumps(artifact, sort_keys=True, indent=2) + "\n")
    _emit(artifact)
    return 0


def _create(store: Path, rid: str, text: str, created: list[str]) -> None:
    """Create one record without overwriting anything, then prove its bytes by readback."""

    def failed(message: str) -> Rejection:
        done = ", ".join(created) or "none"
        return Rejection(
            [
                _diag(
                    "persist.local_write_failed",
                    f"{message}; records created in this attempt: {done}",
                    phase="publish",
                    artifact=f"{rid}.md",
                    path=store / f"{rid}.md",
                )
            ]
        )

    destination = store / f"{rid}.md"
    temporary: str | None = None
    try:
        handle, temporary = tempfile.mkstemp(prefix=f".{rid}.md.", suffix=".tmp", dir=store)
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        created.append(rid)
    except FileExistsError as exc:
        raise failed(f"{destination.name} appeared before it could be created") from exc
    except OSError as exc:
        raise failed(f"cannot create {destination.name} without overwriting: {exc}") from exc
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
    try:
        written = destination.read_bytes()
    except OSError as exc:
        raise failed(f"cannot read back {destination.name}: {exc}") from exc
    if written != text.encode("utf-8"):
        raise failed(f"{destination.name} did not read back as written")


def publish(args: argparse.Namespace) -> int:
    preview, sha, local_store, store, repo = _bind(args, "publish")
    output = Path(args.output)

    def drift(message: str) -> Rejection:
        return Rejection(
            [
                _diag(
                    "persist.local_plan_drift",
                    message,
                    phase="publish",
                    artifact="reconciliation.json",
                    path=args.reconciliation,
                )
            ]
        )

    try:
        reviewed = json.loads(Path(args.reconciliation).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise drift(f"cannot read the reviewed reconciliation.json: {exc}") from exc
    if (
        not isinstance(reviewed, dict)
        or not contract_matches(reviewed.get("contract"), PLAN_CONTRACT)
        or reviewed.get("preview_sha256") != sha
        or reviewed.get("local_store") != local_store
        or not isinstance(reviewed.get("records"), list)
    ):
        raise drift("reconciliation.json was not reviewed for this preview and store")

    planned = _planned(preview, sha)
    records, names = _scan(store, "publish")
    entries = _classify(planned, records, names, store, repo, "publish")
    reviewed_actions = [
        (entry.get("id"), entry.get("action")) for entry in reviewed["records"] if isinstance(entry, dict)
    ]
    if [rid for rid, _ in reviewed_actions] != [entry["id"] for entry in entries]:
        raise drift("the reviewed record list no longer matches this package")
    for (rid, was), entry in zip(reviewed_actions, entries):
        if not (was == "create" or (was == "existing" and entry["action"] == "existing")):
            raise drift(f"record '{rid}' was reviewed as {was!r} but is now {entry['action']!r}")

    try:
        store.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise Rejection(
            [
                _diag(
                    "persist.local_write_failed",
                    f"cannot create the store directory: {exc}; records created in this attempt: none",
                    phase="publish",
                    artifact="preview.json",
                    path=store,
                )
            ]
        ) from exc
    resolved = store.resolve()
    if resolved == repo or not resolved.is_relative_to(repo) or not resolved.is_dir():
        raise Rejection(
            [
                _diag(
                    "persist.local_store_unsafe",
                    f"local_store '{local_store}' no longer resolves to a directory below the repository root",
                    phase="publish",
                    artifact="preview.json",
                    path=store,
                    field="local_store",
                )
            ]
        )

    texts = {record["id"]: record["text"] for record in planned}
    created: list[str] = []
    outcomes: list[dict[str, Any]] = []
    for entry in entries:
        if entry["action"] == "create":
            _create(store, entry["id"], texts[entry["id"]], created)
            outcome = "created"
        else:
            outcome = "existing"
        outcomes.append(
            {
                "id": entry["id"],
                "kind": entry["kind"],
                "path": entry["path"],
                "outcome": outcome,
                "relations_changed": entry["relations_changed"],
            }
        )

    anchor = preview["epic_id"] if preview["shape"] == "epic" else preview["work_items"][0]["id"]
    result = {
        "contract": RESULT_CONTRACT,
        "backend": "local",
        "local_store": local_store,
        "preview_sha256": sha,
        "shape": preview["shape"],
        "anchor": anchor,
        "status": "complete",
        "records": outcomes,
    }
    try:
        _write_atomic(output, json.dumps(result, sort_keys=True, indent=2) + "\n")
    except OSError as exc:
        raise Rejection(
            [
                _diag(
                    "persist.local_output_unwritable",
                    f"cannot write {output.name}: {exc}",
                    phase="publish",
                    artifact="publication-result.json",
                    path=output,
                )
            ]
        ) from exc
    _emit(result)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "publish"):
        command = commands.add_parser(name)
        command.add_argument("--repo-root", required=True)
        command.add_argument("--persist-input", required=True)
        command.add_argument("--preview", required=True)
        command.add_argument("--output", required=True)
        command.add_argument("--publish-confirmation")
        command.add_argument("--label", action="append", default=[])
        command.add_argument("--github-repo")
        if name == "publish":
            command.add_argument("--reconciliation", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return plan(args) if args.command == "plan" else publish(args)
    except Rejection as exc:
        _emit({"valid": False, "diagnostics": exc.diagnostics})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

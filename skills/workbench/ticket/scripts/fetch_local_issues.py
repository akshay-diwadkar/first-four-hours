#!/usr/bin/env python3
"""Read a bounded local Markdown ticket graph for select and verify its freshness without GitHub."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from compile_persist import _is_local_id, is_local_store
from fetch_github_issues import INVERSE, _readset_numbers, write_json_atomic
from _skill_protocol_runtime import compatible_version
from github_common import TICKET_VERSION, ConfigError, ensure_external_output, graph_receipt, snapshot_digest
from persist_local import MARKER_PREFIX, MARKER_SUFFIX, Rejection, _scan

SKILL_ROOT = Path(__file__).resolve().parents[1]


def _relative(path: Path, repo: Path) -> str:
    return path.resolve().relative_to(repo).as_posix()


def _node(path: Path, rid: str, meta: dict[str, Any], repo: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ConfigError(f"cannot read {path.name}: {exc}") from exc
    try:
        text = raw.removeprefix(b"\xef\xbb\xbf").decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{path.name} is not UTF-8") from exc
    first, _, rest = text.partition("\n")
    first = first.removesuffix("\r")
    current: Any = None
    if first.startswith(MARKER_PREFIX) and first.endswith(MARKER_SUFFIX):
        try:
            current = json.loads(first[len(MARKER_PREFIX) : -len(MARKER_SUFFIX)])
        except json.JSONDecodeError:
            current = None
    if current != meta:
        raise ConfigError(f"{path.name} changed while it was read; fetch again")
    heading = rest.split("\n", 1)[0].removesuffix("\r")
    return {
        "number": rid,
        "kind": meta["kind"],
        "state": meta["state"],
        "state_reason": "completed" if meta["state"] == "closed" else None,
        "title": heading[2:] if heading.startswith("# ") else "",
        "body": rest,
        "url": _relative(path, repo),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def build_snapshot(repo_root: Path, local_store: str, mode: str, root: str) -> dict[str, Any]:
    if not is_local_store(local_store):
        raise ConfigError(
            "local_store must be a relative repository path of plain segments "
            "outside the .first-four-hours/ artifact folder"
        )
    if not _is_local_id(root):
        raise ConfigError("local record id must be a lowercase slug")
    repo = repo_root.resolve(strict=True)
    store = (repo / local_store).resolve()
    if store == repo or not store.is_relative_to(repo) or not store.is_dir():
        raise ConfigError(f"local_store '{local_store}' is not a directory below the repository root")
    for entry in store.iterdir():
        if (
            entry.name.endswith(".md")
            and not entry.name.startswith(".")
            and entry.is_file()
            and not entry.resolve().is_relative_to(store)
        ):
            raise ConfigError(f"{entry.name} does not resolve inside {local_store}")
    try:
        scanned, _ = _scan(store, "select")
    except Rejection as exc:
        raise ConfigError("; ".join(str(d["message"]) for d in exc.diagnostics)) from exc
    records = {rid: entry for rid, entry in scanned.items() if entry[0].name.lower() != "ticket-scope.md"}

    if root not in records:
        raise ConfigError(f"'{root}' is not a managed record in {local_store}")
    kind = records[root][1]["kind"]
    required = "issue" if mode == "single" else "epic"
    if kind != required:
        raise ConfigError(f"'{root}' is a {kind} record; {mode} select needs {required}")

    children = (
        sorted(rid for rid, (_, meta) in records.items() if meta["parent"] == root and rid != root)
        if mode == "index"
        else []
    )
    nodes: set[str] = {root, *children}
    unresolved: list[dict[str, Any]] = []
    pending = sorted(nodes)
    while pending:
        current = pending.pop(0)
        for dep in sorted(records[current][1]["depends_on"]):
            if dep in records:
                if dep not in nodes:
                    nodes.add(dep)
                    pending.append(dep)
                continue
            item = {
                "reason": "not_found",
                "source": current,
                "type": "depends_on",
                "target_kind": "issue",
                "target": dep,
                "selection_relevant": True,
            }
            if item not in unresolved:
                unresolved.append(item)

    issues = sorted((_node(records[rid][0], rid, records[rid][1], repo) for rid in nodes), key=lambda i: i["number"])
    urls = {issue["number"]: issue["url"] for issue in issues}

    def authored(source: str, relation: str, target: str) -> dict[str, Any]:
        return {
            "source": source,
            "type": relation,
            "target_kind": "issue",
            "target": target,
            "selection_relevant": True,
            "provenance": [
                {
                    "evidence": "local-ticket-item",
                    "source_issue": source,
                    "locator": f"{urls[source]}:1",
                    "confidence": "explicit",
                }
            ],
        }

    edges = [authored(child, "parent", root) for child in children]
    for rid in sorted(nodes):
        edges.extend(authored(rid, "depends_on", dep) for dep in sorted(records[rid][1]["depends_on"]))
    authored_keys = {(e["source"], e["type"], e["target"]) for e in edges}
    derived = []
    for edge in edges:
        inverse = INVERSE.get(edge["type"])
        if not inverse or (edge["target"], inverse, edge["source"]) in authored_keys:
            continue
        derived.append(
            {
                "source": edge["target"],
                "type": inverse,
                "target_kind": "issue",
                "target": edge["source"],
                "selection_relevant": True,
                "derived_from": {"source": edge["source"], "type": edge["type"], "target": edge["target"]},
            }
        )
    all_edges = sorted(edges + derived, key=lambda e: (e["source"], e["type"], e["target"], "derived_from" in e))

    snapshot: dict[str, Any] = {
        "graph_snapshot_version": TICKET_VERSION,
        "root": {"issue_number": root, "url": urls[root]},
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(issues),
        "metadata": {
            "backend": "local",
            "local_store": local_store,
            "mode": mode,
            "content_trust": "untrusted-local-data",
        },
        "membership": (
            {
                "candidate_completeness": "verified",
                "children_of": {root: children},
                "provenance": {"mechanism": "local-ticket-item-v1", "derived_at": None},
            }
            if mode == "index"
            else {
                "candidate_completeness": "unverified",
                "children_of": {},
                "provenance": {"mechanism": None, "derived_at": None},
            }
        ),
        "candidate_tickets": children if mode == "index" else [root],
        "issues": issues,
        "pull_requests": [],
        "edges": all_edges,
        "unresolved": sorted(unresolved, key=lambda u: (u["source"], u["target"])),
        "coverage": {"complete": not unresolved, "state": "complete" if not unresolved else "partial"},
        "budgets": {"limits": {}, "usage": {"nodes": len(issues), "edges": len(edges)}, "exhausted": []},
    }
    snapshot["graph_receipt"] = graph_receipt(snapshot)
    snapshot["digest"] = snapshot_digest(snapshot)
    return snapshot


def _decision_view(snap: dict[str, Any], ids: set[Any], root: str) -> tuple[Any, ...]:
    """The snapshot facts selection decides on for the read-set: nodes, touching edges, unresolved, candidates, children."""

    issues = {i["number"]: i for i in snap.get("issues") or [] if isinstance(i, dict)}
    edges = sorted(
        json.dumps(e, sort_keys=True)
        for e in snap.get("edges") or []
        if isinstance(e, dict) and (e.get("source") in ids or e.get("target") in ids)
    )
    unresolved = sorted(
        json.dumps(u, sort_keys=True)
        for u in snap.get("unresolved") or []
        if isinstance(u, dict) and u.get("source") in ids
    )
    membership = snap.get("membership") or {}
    return issues, edges, unresolved, snap.get("candidate_tickets"), (membership.get("children_of") or {}).get(root)


def verify_local(
    repo_root: Path, snapshot: dict[str, Any], scope_inputs: dict[str, Any], selected: str | None
) -> dict[str, Any]:
    if (
        not compatible_version(snapshot.get("graph_snapshot_version"), TICKET_VERSION)
        or snapshot.get("graph_receipt") != graph_receipt(snapshot)
        or snapshot.get("digest") != snapshot_digest(snapshot)
    ):
        raise ConfigError("snapshot receipt or digest is invalid; fetch again")
    meta = snapshot.get("metadata") or {}
    if meta.get("backend") != "local" or scope_inputs.get("backend") != "local":
        raise ConfigError("local verification requires backend=local in both the snapshot and scope_inputs")
    if scope_inputs.get("local_store") != meta.get("local_store"):
        raise ConfigError("scope_inputs.local_store does not match the snapshot")
    mode = meta["mode"]
    if scope_inputs.get("mode") != mode:
        raise ConfigError("scope_inputs.mode does not match the snapshot mode")
    root = snapshot["root"]["issue_number"]
    if ((scope_inputs.get("ticket") if mode == "single" else scope_inputs.get("epic")) or {}).get("number") != root:
        raise ConfigError("snapshot root does not match the requested ticket/epic")

    checked = sorted(_readset_numbers(snapshot, scope_inputs, selected))
    over = (scope_inputs.get("override") or {}).get("issue")
    if selected is not None and ((mode == "single" and selected != root) or (over is not None and selected != over)):
        return {
            "fresh": False,
            "stale": [{"kind": "selection", "number": selected, "reason": "mismatch"}],
            "graph_receipt": snapshot["graph_receipt"],
            "next_action": None,
            "checked": checked,
        }

    current = build_snapshot(repo_root, meta["local_store"], mode, root)
    ids = set(checked)
    stored_by, stored_edges, stored_unresolved, stored_candidates, stored_children = _decision_view(snapshot, ids, root)
    current_by, current_edges, current_unresolved, current_candidates, current_children = _decision_view(
        current, ids, root
    )
    stale: list[dict[str, Any]] = []
    for rid in checked:
        stored, live = stored_by.get(rid), current_by.get(rid)
        if stored is None and live is None:
            continue
        if stored is None:
            stale.append({"kind": "issue", "number": rid, "reason": "new"})
        elif live is None:
            stale.append({"kind": "issue", "number": rid, "reason": "missing"})
        elif stored != live:
            stale.append({"kind": "issue", "number": rid, "reason": "changed", "field": "node"})
    for field, before, after in (
        ("edges", stored_edges, current_edges),
        ("unresolved", stored_unresolved, current_unresolved),
        ("candidates", stored_candidates, current_candidates),
    ):
        if before != after:
            stale.append({"kind": "graph", "number": root, "reason": "changed", "field": field})
    if stored_children != current_children:
        stale.append({"kind": "membership", "number": root, "reason": "changed", "field": "children"})
    stale.sort(key=lambda item: (item["kind"], str(item["number"]), item.get("field", "")))
    return {
        "fresh": not stale,
        "stale": stale,
        "graph_receipt": snapshot["graph_receipt"],
        "next_action": ("narrow_selected" if selected is not None else "proceed") if not stale else None,
        "checked": checked,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch", help="Read one explicit local record or epic into a graph snapshot.")
    fetch.add_argument("--repo-root", required=True)
    fetch.add_argument("--local-store", required=True)
    fetch.add_argument("--mode", choices=("single", "epic"), required=True)
    fetch.add_argument("--issue-id")
    fetch.add_argument("--epic-id")
    fetch.add_argument("--output", required=True)
    verify = commands.add_parser("verify", help="Verify a local snapshot's decision records are still current.")
    verify.add_argument("--repo-root", required=True)
    verify.add_argument("--snapshot", required=True)
    verify.add_argument("--scope-inputs", required=True)
    verify.add_argument("--selected-issue-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        repo_root = Path(args.repo_root).resolve(strict=True)
        if args.command == "fetch":
            if (args.issue_id is None) == (args.epic_id is None):
                raise ConfigError("pass exactly one of --issue-id or --epic-id")
            if args.mode == "single" and args.issue_id is None:
                raise ConfigError("single mode requires --issue-id")
            if args.mode == "epic" and args.epic_id is None:
                raise ConfigError("epic mode requires --epic-id")
            output = ensure_external_output(Path(args.output), repo_root=repo_root, skill_root=SKILL_ROOT)
            mode = "index" if args.mode == "epic" else "single"
            snapshot = build_snapshot(repo_root, args.local_store, mode, args.issue_id or args.epic_id)
            write_json_atomic(output, snapshot)
            print(
                json.dumps(
                    {"count": snapshot["count"], "graph_receipt": snapshot["graph_receipt"], "path": str(output)},
                    sort_keys=True,
                )
            )
            return 0
        snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
        scope_inputs = json.loads(Path(args.scope_inputs).read_text(encoding="utf-8"))
        result = verify_local(repo_root, snapshot, scope_inputs, args.selected_issue_id)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["fresh"] else 3
    except (ConfigError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

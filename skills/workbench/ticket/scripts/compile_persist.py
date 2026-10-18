#!/usr/bin/env python3
"""Deterministic compiler/validator for Ticket persist meaning.

Reads agent-authored backend-neutral persist-meaning JSON, validates only
mechanical invariants, and produces a preview.json artifact. Never performs
semantic judgment, prose scoring, actionability assessment, or ticket splitting.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from collections import deque
from pathlib import Path
from typing import Any

from _diagnostic_contract import Diagnostic

GITHUB_REPO_RE = re.compile(r"^[^/]+/[^/]+$")
LOCAL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
LOCAL_STORE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")
RESERVED_LOCAL_IDS = frozenset(
    {"ticket-scope", "con", "prn", "aux", "nul"}
    | {f"com{number}" for number in range(1, 10)}
    | {f"lpt{number}" for number in range(10)}
)


def _is_local_id(value: Any) -> bool:
    return isinstance(value, str) and LOCAL_ID_RE.fullmatch(value) is not None and value not in RESERVED_LOCAL_IDS


def is_local_store(value: Any) -> bool:
    """Plain relative store path; its segment rule keeps it outside the .first-four-hours/ artifact root, whose skill folders Git ignores."""
    if not isinstance(value, str) or not value:
        return False
    return all(LOCAL_STORE_SEGMENT_RE.fullmatch(segment) for segment in value.split("/"))


def _fail(diagnostics: list[dict[str, Any]]) -> None:
    print(
        json.dumps(
            {"valid": False, "diagnostics": diagnostics},
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _diag(
    code: str,
    message: str,
    *,
    field: str | None = None,
    record: str | None = None,
    path: str = "persist-input.json",
) -> dict[str, Any]:
    return Diagnostic(
        code=code,
        message=message,
        skill="ticket",
        phase="start",
        artifact="persist-input.json",
        record=record,
        field=field,
        path=path,
    ).to_dict()


def _validate(data: Any) -> tuple[bool, list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []

    if not isinstance(data, dict):
        return False, [_diag("persist.invalid_input", "root must be a JSON object")]

    # Rule 1: backend
    backend = data.get("backend")
    if backend is None:
        diagnostics.append(_diag("persist.missing_backend", "backend is required", field="backend"))
    elif backend not in ("github", "local"):
        diagnostics.append(
            _diag(
                "persist.invalid_backend",
                f"backend must be 'github' or 'local', got '{backend}'",
                field="backend",
            )
        )

    # Rule 2: shape
    shape = data.get("shape")
    if shape is None:
        diagnostics.append(_diag("persist.missing_shape", "shape is required", field="shape"))
    elif shape not in ("single", "epic"):
        diagnostics.append(
            _diag(
                "persist.invalid_shape",
                f"shape must be 'single' or 'epic', got '{shape}'",
                field="shape",
            )
        )

    # Rule 3: task.text
    task = data.get("task")
    if not isinstance(task, dict):
        diagnostics.append(_diag("persist.missing_task", "task is required", field="task"))
        task_text = None
    else:
        task_text = task.get("text")
        if not isinstance(task_text, str) or not task_text.strip():
            diagnostics.append(
                _diag("persist.missing_task_text", "task.text must be a non-empty string", field="task.text")
            )

    # Rule 4: work_items
    work_items = data.get("work_items")
    if not isinstance(work_items, list):
        diagnostics.append(_diag("persist.missing_work_items", "work_items must be an array", field="work_items"))
        work_items = []
    elif len(work_items) == 0:
        diagnostics.append(
            _diag("persist.empty_work_items", "work_items must not be empty", field="work_items")
        )

    # Rule 5: each work item structure
    item_ids: list[str] = []
    for idx, item in enumerate(work_items):
        prefix = f"work_items[{idx}]"
        if not isinstance(item, dict):
            diagnostics.append(
                _diag("persist.invalid_work_item", f"{prefix} must be a JSON object", field=prefix)
            )
            continue

        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            diagnostics.append(
                _diag("persist.missing_item_id", f"{prefix}.id must be a non-empty string", field=f"{prefix}.id")
            )
        else:
            item_ids.append(item_id)

        outcome = item.get("outcome")
        if not isinstance(outcome, str) or not outcome.strip():
            diagnostics.append(
                _diag(
                    "persist.missing_outcome",
                    f"{prefix}.outcome must be a non-empty string",
                    field=f"{prefix}.outcome",
                )
            )

    # Rule 6: unique IDs
    seen_ids: set[str] = set()
    for item_id in item_ids:
        if item_id in seen_ids:
            diagnostics.append(
                _diag(
                    "persist.duplicate_id",
                    f"duplicate work item id: '{item_id}'",
                    field="work_items.id",
                )
            )
        seen_ids.add(item_id)

    # If we have structural errors, skip graph validation
    if diagnostics:
        return False, diagnostics

    # Rule 7: shape-specific count
    if shape == "single" and len(work_items) != 1:
        diagnostics.append(
            _diag(
                "persist.single_count",
                f"single shape requires exactly 1 work item, got {len(work_items)}",
                field="work_items",
            )
        )
    elif shape == "epic" and len(work_items) < 2:
        diagnostics.append(
            _diag(
                "persist.epic_count",
                f"epic shape requires 2+ work items, got {len(work_items)}",
                field="work_items",
            )
        )

    # Rule 8: dependencies
    id_set = set(item_ids)
    edges: list[tuple[str, str]] = []
    for idx, item in enumerate(work_items):
        prefix = f"work_items[{idx}]"
        deps = item.get("dependencies", [])
        if not isinstance(deps, list):
            diagnostics.append(
                _diag("persist.invalid_dependencies", f"{prefix}.dependencies must be an array", field=f"{prefix}.dependencies")
            )
            continue
        for dep in deps:
            if not isinstance(dep, str):
                diagnostics.append(
                    _diag(
                        "persist.invalid_dependency",
                        f"{prefix}.dependencies entries must be strings",
                        field=f"{prefix}.dependencies",
                    )
                )
            elif dep == item["id"]:
                diagnostics.append(
                    _diag(
                        "persist.self_dependency",
                        f"{prefix} depends on itself",
                        field=f"{prefix}.dependencies",
                    )
                )
            elif dep not in id_set:
                diagnostics.append(
                    _diag(
                        "persist.unknown_dependency",
                        f"{prefix} depends on unknown item '{dep}'",
                        field=f"{prefix}.dependencies",
                    )
                )
            else:
                edges.append((item["id"], dep))

    # Rule 9: dependency cycles (Kahn's algorithm)
    if not diagnostics and edges:
        in_degree: dict[str, int] = {iid: 0 for iid in item_ids}
        adj: dict[str, list[str]] = {iid: [] for iid in item_ids}
        for src, dst in edges:
            adj[dst].append(src)
            in_degree[src] += 1
        queue = deque(iid for iid, deg in in_degree.items() if deg == 0)
        visited = 0
        while queue:
            node = queue.popleft()
            visited += 1
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        if visited < len(item_ids):
            diagnostics.append(
                _diag(
                    "persist.dependency_cycle",
                    "dependency cycle detected among work items",
                    field="work_items.dependencies",
                )
            )

    # Rule 10: github_repo_url
    if backend == "github":
        github_repo_url = data.get("github_repo_url")
        if not isinstance(github_repo_url, str) or not github_repo_url.strip():
            diagnostics.append(
                _diag(
                    "persist.missing_github_repo",
                    "github_repo_url is required when backend is 'github'",
                    field="github_repo_url",
                )
            )
        elif not GITHUB_REPO_RE.fullmatch(github_repo_url):
            diagnostics.append(
                _diag(
                    "persist.bad_github_repo",
                    f"github_repo_url must match 'owner/repo' pattern, got '{github_repo_url}'",
                    field="github_repo_url",
                )
            )

    # Rule 12: local store destination and slug identities
    if backend == "local":
        local_store = data.get("local_store")
        if not isinstance(local_store, str) or not local_store:
            diagnostics.append(
                _diag(
                    "persist.missing_local_store",
                    "local_store is required when backend is 'local'",
                    field="local_store",
                )
            )
        elif not is_local_store(local_store):
            diagnostics.append(
                _diag(
                    "persist.bad_local_store",
                    f"local_store must be a relative repository path of plain segments outside .first-four-hours/, got '{local_store}'",
                    field="local_store",
                )
            )
        for idx, item in enumerate(work_items):
            if not _is_local_id(item["id"]):
                diagnostics.append(
                    _diag(
                        "persist.bad_local_id",
                        f"work_items[{idx}].id must be a lowercase slug that is not reserved, got '{item['id']}'",
                        field=f"work_items[{idx}].id",
                    )
                )
        if shape == "epic":
            epic_id = data.get("epic_id")
            if not isinstance(epic_id, str) or not epic_id:
                diagnostics.append(
                    _diag("persist.missing_epic_id", "epic_id is required for a local epic", field="epic_id")
                )
            elif not _is_local_id(epic_id):
                diagnostics.append(
                    _diag(
                        "persist.bad_local_id",
                        f"epic_id must be a lowercase slug that is not reserved, got '{epic_id}'",
                        field="epic_id",
                    )
                )
            elif epic_id in id_set:
                diagnostics.append(
                    _diag(
                        "persist.duplicate_id",
                        f"epic_id '{epic_id}' duplicates a work item id",
                        field="epic_id",
                    )
                )

    # Rule 11: authority_source (optional)
    authority_source = data.get("authority_source")
    if authority_source is not None:
        if not isinstance(authority_source, dict):
            diagnostics.append(
                _diag(
                    "persist.invalid_authority_source",
                    "authority_source must be a JSON object",
                    field="authority_source",
                )
            )
        else:
            source_type = authority_source.get("type")
            if source_type not in ("request", "artifact"):
                diagnostics.append(
                    _diag(
                        "persist.invalid_authority_source_type",
                        f"authority_source.type must be 'request' or 'artifact', got '{source_type}'",
                        field="authority_source.type",
                    )
                )
            elif source_type == "artifact":
                reference = authority_source.get("reference")
                if not isinstance(reference, str) or not reference.strip():
                    diagnostics.append(
                        _diag(
                            "persist.missing_authority_reference",
                            "authority_source.reference is required when type is 'artifact'",
                            field="authority_source.reference",
                        )
                    )

    if diagnostics:
        return False, diagnostics

    return True, []


def _build_preview(data: dict[str, Any]) -> dict[str, Any]:
    work_items = data["work_items"]
    item_ids = [item["id"] for item in work_items]
    edges = [
        {"from": item["id"], "to": dep}
        for item in work_items
        for dep in item.get("dependencies", [])
    ]

    preview: dict[str, Any] = {
        "backend": data["backend"],
        "shape": data["shape"],
        "task": data["task"],
        "work_items": work_items,
        "graph": {
            "single": data["shape"] == "single",
            "children": item_ids,
            "dependencies": edges,
        },
        "publication_intent": {
            "backend": data["backend"],
            "shape": data["shape"],
            "work_item_count": len(work_items),
        },
    }

    if data["backend"] == "github":
        preview["github_repo_url"] = data["github_repo_url"]
        preview["publication_intent"]["github_repo_url"] = data["github_repo_url"]

    if data["backend"] == "local":
        preview["local_store"] = data["local_store"]
        preview["publication_intent"]["local_store"] = data["local_store"]
        if data["shape"] == "epic":
            preview["epic_id"] = data["epic_id"]

    if "authority_source" in data:
        preview["authority_source"] = data["authority_source"]

    return preview


def render_preview(data: Any) -> tuple[str | None, list[dict[str, Any]]]:
    """Return canonical preview.json text for valid persist meaning, else diagnostics."""
    valid, diagnostics = _validate(data)
    if not valid:
        return None, diagnostics
    preview = _build_preview(data)
    return json.dumps(preview, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n", []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persist-input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    try:
        raw = args.persist_input.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        _fail([_diag("persist.unreadable", f"cannot read input: {exc}")])
        return 1

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        _fail([_diag("persist.invalid_json", f"invalid JSON: {exc}")])
        return 1

    preview_json, diagnostics = render_preview(data)
    if preview_json is None:
        _fail(diagnostics)
        return 1

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "preview.json"

    handle, temporary = tempfile.mkstemp(prefix=".preview.json.", suffix=".tmp", dir=output_dir)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(preview_json)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise

    print(preview_json.rstrip("\n"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

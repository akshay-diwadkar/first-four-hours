#!/usr/bin/env python3
"""Read-only GitHub reconciliation for Ticket persist previews over the gh CLI.

Binds the exact compiler-derived preview, the explicit destination and labels,
and the agent-authored reconciliation input, then performs only the bounded
GitHub reads the current shape needs through ``GitHubClient`` (``gh auth
status`` and ``gh api`` GETs). The agent owns every semantic classification;
this module verifies only mechanically knowable identity, hierarchy,
dependency, capability, and freshness facts. It never mutates GitHub.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Protocol

from _diagnostic_contract import Diagnostic
from _skill_protocol_runtime import compatible_version
from compile_persist import render_preview
from github_common import (
    TICKET_VERSION,
    ConfigError,
    GitHubClient,
    GitHubError,
    ResponseBudgetExceeded,
    contract_matches,
    normalize_github_repo_target,
)

CONTRACT = {"skill": "ticket", "branch": "persist", "artifact": "github-reconciliation", "version": TICKET_VERSION}
MAX_SEARCH_LIMIT = 30
BODY_EVIDENCE_CHARS = 4000
CLASSIFICATIONS = ("same", "related", "different", "conflict")
ACTIONS = ("create", "reuse", "block")
CAPABILITY_ORDER = ("issues", "write", "sub_issues", "dependencies")
CANDIDATE_KEY_RE = re.compile(r"^[1-9][0-9]*$")
REPOSITORY_URL_RE = re.compile(r"/repos/([^/]+/[^/]+)$")
HTML_URL_RE = re.compile(r"^https://github\.com/([^/]+/[^/]+)/(?:issues|pull)/\d+$")
GONE_STATUSES = (301, 404, 410)
TITLE_LIMIT = 256
BODY_LIMIT = 65536
TRANSPORT_CODES = ("persist.github_unavailable", "persist.github_read_failed", "persist.github_budget")

CODE_RULES: dict[str, tuple[str, str]] = {
    "persist.reconcile_backend_unsupported": (
        "contract_contradiction",
        "GitHub reconciliation applies only to backend=github; the flow reconciles backend=local through "
        "persist_local.py. Rerun the flow with one explicit backend; never fall back to GitHub.",
    ),
    "persist.reconcile_backend_mismatch": (
        "contract_contradiction",
        "Start a new run whose persist_input backend and protocol backend are both github.",
    ),
    "persist.reconcile_unreadable": (
        "missing_evidence",
        "Author the named file as UTF-8 JSON in the run directory, then run reconcile again.",
    ),
    "persist.reconcile_preview_stale": (
        "stale_evidence",
        "preview.json is not the canonical compile output of persist_input; start a new run to recompile it.",
    ),
    "persist.reconcile_destination_missing": (
        "missing_evidence",
        "Pass --input github_repo_url=<owner/repo> matching persist_input, then run reconcile again.",
    ),
    "persist.reconcile_destination_mismatch": (
        "contract_contradiction",
        "Make github_repo_url and persist_input name the same repository in a new run.",
    ),
    "persist.reconcile_label_invalid": (
        "malformed_input",
        "Pass each label as a non-empty name in a new run.",
    ),
    "persist.reconcile_content_invalid": (
        "malformed_input",
        "Shorten the named target's outcome (or task.text for an epic root) to a title of at most 256 "
        "characters, or its rendered meaning to a body of at most 65536 characters, in persist_input, then "
        "start a new run.",
    ),
    "persist.reconcile_input_invalid": (
        "malformed_input",
        "Correct the named field in reconciliation-input.json per references/persist-github.md, then run reconcile again.",
    ),
    "persist.reconcile_input_stale": (
        "stale_evidence",
        "Set preview_sha256 to the SHA-256 of the current preview.json after reviewing it, then run reconcile again.",
    ),
    "persist.reconcile_confirmation_premature": (
        "unsafe_state",
        "publish_confirmation is accepted only from publication review after reading reconciliation.json; it "
        "cannot be removed from this run, so start a new run and confirm only at publication-ready.",
    ),
    "persist.reconcile_output_unwritable": (
        "unavailable_prerequisite",
        "Make the run directory writable, then run reconcile again.",
    ),
    "persist.github_unavailable": ("unavailable_prerequisite", ""),
    "persist.github_read_failed": (
        "unavailable_prerequisite",
        "Restore access to the named GitHub read, then run reconcile again.",
    ),
    "persist.github_budget": (
        "unsafe_state",
        "Narrow the search terms or lower the limit, then run reconcile again.",
    ),
    "persist.destination_mismatch": (
        "contract_contradiction",
        "Use the repository's current owner/repo in persist_input and github_repo_url in a new run.",
    ),
    "persist.issues_unavailable": (
        "unavailable_prerequisite",
        "Enable issues on an unarchived repository or choose another explicit destination in a new run.",
    ),
    "persist.write_permission_missing": (
        "unavailable_prerequisite",
        "Obtain write access to the destination, or drop the label, hierarchy, or dependency mutations in a new run.",
    ),
    "persist.missing_label": (
        "missing_evidence",
        "Create the label in GitHub yourself or remove it from the label input in a new run; "
        "reconcile never creates labels.",
    ),
    "persist.reuse_missing": (
        "contract_contradiction",
        "Correct the target's issue number or choose create, then run reconcile again.",
    ),
    "persist.reuse_pull_request": (
        "contract_contradiction",
        "Correct the target's issue number or choose create, then run reconcile again.",
    ),
    "persist.reuse_not_open": (
        "unsafe_state",
        "Choose create or block for this target, or reopen the issue yourself outside Ticket, "
        "then run reconcile again.",
    ),
    "persist.wrong_parent": (
        "unsafe_state",
        "Ticket never re-parents: choose create or block for this target, or change the hierarchy yourself "
        "outside Ticket, then run reconcile again.",
    ),
    "persist.dependency_conflict": (
        "contract_contradiction",
        "Resolve the opposing GitHub dependency or choose create for one side, then run reconcile again.",
    ),
    "persist.candidate_conflict": (
        "unsafe_state",
        "Resolve the conflicting existing issue, or reclassify it with new evidence, then run reconcile again.",
    ),
    "persist.agent_block": (
        "unsafe_state",
        "Resolve the recorded block basis, then change the target's action and run reconcile again.",
    ),
    "persist.unclassified_candidate": (
        "missing_evidence",
        "Add a candidates entry for this issue under the named target in reconciliation-input.json from the "
        "untrusted evidence in reconciliation.json, then run reconcile again.",
    ),
    "persist.search_truncated": (
        "missing_evidence",
        "Narrow the search terms or raise the limit (maximum 30) so every match is returned, "
        "then run reconcile again.",
    ),
    "persist.reconciliation_invalid": (
        "malformed_input",
        "Rebuild reconciliation.json with reconcile; never edit it by hand.",
    ),
    "persist.reconciliation_not_ready": (
        "contract_contradiction",
        "Only a ready reconciliation can be verified for publication; repair it and run reconcile again.",
    ),
    "persist.reconciliation_stale": (
        "stale_evidence",
        "Material GitHub or input facts changed since reconciliation; start a new run and reconcile again.",
    ),
}


class ReadClient(Protocol):
    def preflight(self) -> None: ...

    def request(self, method: str, path: str) -> Any: ...

    def paginated_get(self, path: str, *, item_limit: int | None = None) -> list[dict[str, Any]]: ...


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _receipt(artifact: dict[str, Any]) -> str:
    return _sha256(_canonical({key: value for key, value in artifact.items() if key != "receipt"}))


def _diag(
    code: str,
    message: str,
    *,
    phase: str,
    artifact: str,
    path: Path | str,
    field: str | None = None,
    required_action: str | None = None,
) -> dict[str, Any]:
    category, action = CODE_RULES[code]
    action = required_action or action
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


class LocalRejection(Exception):
    def __init__(self, diagnostics: list[dict[str, Any]]) -> None:
        super().__init__("local reconciliation binding failed")
        self.diagnostics = diagnostics


@dataclasses.dataclass(frozen=True)
class Target:
    ref: dict[str, Any]
    action: str
    issue: int | None
    basis: str
    search: dict[str, Any] | None
    candidates: dict[int, dict[str, str]]


@dataclasses.dataclass(frozen=True)
class Bound:
    repository: str
    labels: list[str]
    shape: str
    targets: list[Target]
    edges: list[tuple[str, str]]
    binding: dict[str, Any]
    content: dict[str, dict[str, str]]


def _ref_label(ref: dict[str, Any]) -> str:
    return "epic" if ref["kind"] == "epic" else f"item {ref['id']}"


def _is_blank(value: Any) -> bool:
    return value is None or value in ([], {}) or (isinstance(value, str) and not value.strip())


def _render_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list) and all(isinstance(entry, str) for entry in value):
        return "\n".join(f"- {entry.strip()}" for entry in value)
    return "```json\n" + json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n```"


def _heading(key: str) -> str:
    return key.replace("_", " ").strip().capitalize()


def _render_body(sections: list[tuple[str, Any]]) -> str:
    return "\n\n".join(f"## {heading}\n\n{_render_value(value)}" for heading, value in sections if not _is_blank(value)) + "\n"


def issue_content(preview: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Derive each created issue's exact title and body from the compiled preview, keyed by target label."""

    task = preview["task"]
    shared: list[tuple[str, Any]] = [("Task", task["text"])]
    shared += [(_heading(key), task[key]) for key in sorted(task) if key != "text"]
    if "authority_source" in preview:
        shared.append(("Authority source", preview["authority_source"]))
    content: dict[str, dict[str, str]] = {}
    if preview["shape"] == "epic":
        content["epic"] = {"title": " ".join(task["text"].split()), "body": _render_body(shared)}
    for item in preview["work_items"]:
        sections: list[tuple[str, Any]] = [("Outcome", item["outcome"])]
        sections += [(_heading(key), item[key]) for key in sorted(item) if key not in ("id", "outcome", "dependencies")]
        if preview["shape"] == "single":
            sections += shared
        content[_ref_label({"kind": "item", "id": item["id"]})] = {
            "title": " ".join(item["outcome"].split()),
            "body": _render_body(sections),
        }
    return content


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_decision(
    raw: Any, field: str, errors: list[tuple[str, str]]
) -> tuple[str, int | None, str, dict[str, Any] | None, dict[int, dict[str, str]]] | None:
    if not isinstance(raw, dict):
        errors.append((field, f"{field} must be an object"))
        return None
    unknown = sorted(set(raw) - {"action", "issue", "basis", "search", "candidates"})
    if unknown:
        errors.append((field, f"{field} has unknown keys: {', '.join(unknown)}"))
    action = raw.get("action")
    if action not in ACTIONS:
        errors.append((f"{field}.action", f"{field}.action must be one of {', '.join(ACTIONS)}"))
    basis = raw.get("basis")
    if not isinstance(basis, str) or not basis.strip():
        errors.append((f"{field}.basis", f"{field}.basis must be a non-empty string"))
    issue = raw.get("issue")
    if action == "reuse":
        if not isinstance(issue, int) or isinstance(issue, bool) or issue <= 0:
            errors.append((f"{field}.issue", f"{field}.issue must be a positive integer for reuse"))
    elif "issue" in raw:
        errors.append((f"{field}.issue", f"{field}.issue is allowed only for reuse"))
    search: dict[str, Any] | None = None
    if "search" in raw:
        raw_search = raw["search"]
        if action == "reuse":
            errors.append((f"{field}.search", f"{field}.search is forbidden for reuse; a known identity is exact"))
        elif not isinstance(raw_search, dict) or set(raw_search) != {"terms", "limit"}:
            errors.append((f"{field}.search", f"{field}.search must have exactly terms and limit"))
        else:
            terms = raw_search["terms"]
            limit = raw_search["limit"]
            if (
                not isinstance(terms, list)
                or not 1 <= len(terms) <= 8
                or not all(isinstance(term, str) and term.strip() and '"' not in term for term in terms)
            ):
                errors.append(
                    (f"{field}.search.terms", f"{field}.search.terms must be 1-8 non-empty strings without quotes")
                )
            elif not _is_int(limit) or not 1 <= limit <= MAX_SEARCH_LIMIT:
                errors.append(
                    (f"{field}.search.limit", f"{field}.search.limit must be an integer from 1 to {MAX_SEARCH_LIMIT}")
                )
            else:
                search = {"terms": [term.strip() for term in terms], "limit": limit}
    candidates: dict[int, dict[str, str]] = {}
    raw_candidates = raw.get("candidates", {})
    if not isinstance(raw_candidates, dict):
        errors.append((f"{field}.candidates", f"{field}.candidates must be an object"))
    else:
        for key, value in raw_candidates.items():
            cfield = f"{field}.candidates.{key}"
            if not CANDIDATE_KEY_RE.fullmatch(key):
                errors.append((cfield, f"{cfield} key must be a positive issue number"))
                continue
            if (
                not isinstance(value, dict)
                or set(value) != {"classification", "basis"}
                or value.get("classification") not in CLASSIFICATIONS
                or not isinstance(value.get("basis"), str)
                or not value["basis"].strip()
            ):
                errors.append(
                    (cfield, f"{cfield} must have a classification in {', '.join(CLASSIFICATIONS)} and a basis")
                )
                continue
            number = int(key)
            if value["classification"] == "same" and (action != "reuse" or number != issue):
                errors.append((cfield, f"{cfield} is same, which is allowed only for a reuse target's own issue"))
                continue
            candidates[number] = {"classification": value["classification"], "basis": value["basis"]}
    if action not in ACTIONS or not isinstance(basis, str):
        return None
    return action, issue if action == "reuse" else None, basis, search, candidates


def bind_local(args: argparse.Namespace) -> Bound:
    """Validate every local binding; never touches GitHub and never writes."""

    phase = "reconcile" if args.command == "build" else "verify"

    def reject(code: str, message: str, *, artifact: str, path: Path | str, field: str | None = None) -> LocalRejection:
        return LocalRejection([_diag(code, message, phase=phase, artifact=artifact, path=path, field=field)])

    if args.backend != "github":
        raise reject(
            "persist.reconcile_backend_unsupported",
            f"backend is {args.backend!r}; GitHub reconciliation applies only to backend=github",
            artifact="preview.json",
            path=args.preview,
        )
    if getattr(args, "publish_confirmation", None) is not None:
        raise reject(
            "persist.reconcile_confirmation_premature",
            "publish_confirmation was supplied before publication review",
            artifact="reconciliation.json",
            path=args.reconciliation_input,
            field="publish_confirmation",
        )
    raw: dict[str, bytes] = {}
    for name, path in (
        ("persist_input", args.persist_input),
        ("preview", args.preview),
        ("reconciliation_input", args.reconciliation_input),
    ):
        try:
            raw[name] = Path(path).read_bytes()
        except OSError as exc:
            raise reject(
                "persist.reconcile_unreadable",
                f"cannot read {Path(path).name}: {exc}",
                artifact=Path(path).name,
                path=path,
            ) from exc
    try:
        preview = json.loads(raw["preview"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        preview = None
    if not isinstance(preview, dict) or preview.get("backend") != "github":
        raise reject(
            "persist.reconcile_backend_mismatch",
            "preview.json is not a backend=github persist preview",
            artifact="preview.json",
            path=args.preview,
        )
    try:
        rendered, _ = render_preview(json.loads(raw["persist_input"].decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError):
        rendered = None
    if rendered is None or rendered.encode("utf-8") != raw["preview"]:
        raise reject(
            "persist.reconcile_preview_stale",
            "preview.json does not equal the canonical compile output of persist_input",
            artifact="preview.json",
            path=args.preview,
        )
    if not isinstance(args.github_repo, str) or not args.github_repo.strip():
        raise reject(
            "persist.reconcile_destination_missing",
            "the explicit github_repo_url destination is missing",
            artifact="preview.json",
            path=args.preview,
            field="github_repo_url",
        )
    try:
        repository = normalize_github_repo_target(args.github_repo)
        preview_repository = normalize_github_repo_target(preview.get("github_repo_url"))
    except ConfigError as exc:
        raise reject(
            "persist.reconcile_destination_mismatch",
            f"destination is not a GitHub repository: {exc}",
            artifact="preview.json",
            path=args.preview,
            field="github_repo_url",
        ) from exc
    if repository != preview_repository:
        raise reject(
            "persist.reconcile_destination_mismatch",
            f"github_repo_url {repository!r} does not match the preview destination {preview_repository!r}",
            artifact="preview.json",
            path=args.preview,
            field="github_repo_url",
        )
    labels: list[str] = []
    seen_labels: set[str] = set()
    for label in args.label or []:
        name = label.strip()
        if not name:
            raise reject(
                "persist.reconcile_label_invalid",
                "a label is empty",
                artifact="preview.json",
                path=args.preview,
                field="label",
            )
        if name.casefold() not in seen_labels:
            seen_labels.add(name.casefold())
            labels.append(name)

    input_path = args.reconciliation_input
    try:
        data = json.loads(raw["reconciliation_input"].decode("utf-8"), object_pairs_hook=_reject_duplicates)
    except (UnicodeDecodeError, ValueError) as exc:
        raise reject(
            "persist.reconcile_input_invalid",
            f"reconciliation-input.json is not valid JSON: {exc}",
            artifact="reconciliation-input.json",
            path=input_path,
        ) from exc
    shape = preview["shape"]
    work_item_ids = [item["id"] for item in preview["work_items"]]
    errors: list[tuple[str, str]] = []
    targets: list[Target] = []
    if not isinstance(data, dict):
        errors.append(("$", "the root must be an object"))
    else:
        unknown = sorted(set(data) - {"version", "preview_sha256", "items", "epic"})
        if unknown:
            errors.append(("$", f"unknown keys: {', '.join(unknown)}"))
        if not compatible_version(data.get("version"), TICKET_VERSION):
            errors.append(("version", f"version must share major version {TICKET_VERSION.split('.')[0]} with {TICKET_VERSION!r}"))
        if not isinstance(data.get("preview_sha256"), str):
            errors.append(("preview_sha256", "preview_sha256 must be a string"))
        if shape == "epic" and "epic" not in data:
            errors.append(("epic", "epic is required for an epic preview"))
        if shape == "single" and "epic" in data:
            errors.append(("epic", "epic is forbidden for a single preview"))
        items = data.get("items")
        if not isinstance(items, dict):
            errors.append(("items", "items must be an object"))
            items = {}
        elif set(items) != set(work_item_ids):
            errors.append(("items", f"items keys must be exactly the work item ids: {', '.join(work_item_ids)}"))
        ordered: list[tuple[dict[str, Any], str, Any]] = []
        if shape == "epic" and "epic" in data:
            ordered.append(({"kind": "epic"}, "epic", data["epic"]))
        for item_id in work_item_ids:
            if item_id in items:
                ordered.append(({"kind": "item", "id": item_id}, f"items.{item_id}", items[item_id]))
        for ref, field, decision in ordered:
            parsed = _parse_decision(decision, field, errors)
            if parsed is not None:
                action, issue, basis, search, candidates = parsed
                targets.append(Target(ref, action, issue, basis, search, candidates))
        reused: dict[int, str] = {}
        for target in targets:
            if target.issue is None:
                continue
            if target.issue in reused:
                errors.append(
                    (
                        "issue",
                        f"issue {target.issue} is reused by both {reused[target.issue]} and {_ref_label(target.ref)}",
                    )
                )
            reused[target.issue] = _ref_label(target.ref)
    if errors:
        raise LocalRejection(
            [
                _diag(
                    "persist.reconcile_input_invalid",
                    message,
                    phase=phase,
                    artifact="reconciliation-input.json",
                    path=input_path,
                    field=field,
                )
                for field, message in errors
            ]
        )
    assert isinstance(data, dict)
    preview_sha256 = _sha256(raw["preview"])
    if data["preview_sha256"] != preview_sha256:
        raise reject(
            "persist.reconcile_input_stale",
            "reconciliation-input.json preview_sha256 does not match the current preview.json",
            artifact="reconciliation-input.json",
            path=input_path,
            field="preview_sha256",
        )
    content = issue_content(preview)
    for target in targets:
        created = content[_ref_label(target.ref)]
        if target.action == "create" and (len(created["title"]) > TITLE_LIMIT or len(created["body"]) > BODY_LIMIT):
            raise reject(
                "persist.reconcile_content_invalid",
                f"{_ref_label(target.ref)} would create an issue with a {len(created['title'])}-character title "
                f"and a {len(created['body'])}-character body; GitHub allows at most {TITLE_LIMIT} and {BODY_LIMIT}",
                artifact="persist-input.json",
                path=args.persist_input,
            )
    edges = [(edge["from"], edge["to"]) for edge in preview["graph"]["dependencies"]]
    binding = {
        "backend": "github",
        "repository": repository,
        "labels": labels,
        "source_sha256": _sha256(raw["persist_input"]),
        "preview_sha256": preview_sha256,
        "input_sha256": _sha256(raw["reconciliation_input"]),
    }
    return Bound(repository, labels, shape, targets, edges, binding, content)


def _unexpected(path: str) -> GitHubError:
    return GitHubError(f"GitHub API returned unexpected data for {path}")


def _issue_repository(raw: dict[str, Any]) -> str | None:
    for value, pattern in ((raw.get("repository_url"), REPOSITORY_URL_RE), (raw.get("html_url"), HTML_URL_RE)):
        if isinstance(value, str):
            match = pattern.search(value)
            if match:
                return match.group(1).casefold()
    return None


def _issue_fact(raw: Any, path: str, *, labels_of_interest: set[str] | None) -> dict[str, Any]:
    if not isinstance(raw, dict) or not _is_int(raw.get("number")) or not _is_int(raw.get("id")):
        raise _unexpected(path)
    body = raw.get("body") or ""
    if not isinstance(body, str):
        raise _unexpected(path)
    fact: dict[str, Any] = {
        "number": raw["number"],
        "id": raw["id"],
        "repository": _issue_repository(raw),
        "node_id": raw.get("node_id"),
        "html_url": raw.get("html_url"),
        "title": raw.get("title") or "",
        "state": raw.get("state"),
        "state_reason": raw.get("state_reason"),
        "pull_request": raw.get("pull_request") is not None,
        "body_excerpt": body[:BODY_EVIDENCE_CHARS],
        "body_sha256": _sha256(body.encode("utf-8")),
    }
    if labels_of_interest is not None:
        fact["labels"] = sorted(
            label["name"]
            for label in raw.get("labels") or []
            if isinstance(label, dict)
            and isinstance(label.get("name"), str)
            and label["name"].casefold() in labels_of_interest
        )
    return fact


def _ref(fact: dict[str, Any]) -> dict[str, Any]:
    return {"repository": fact["repository"], "number": fact["number"]}


def _ref_key(ref: dict[str, Any]) -> tuple[str, int]:
    return (ref["repository"] or "", ref["number"])


def _is_404(exc: GitHubError) -> bool:
    return exc.status == 404 and not isinstance(exc, ResponseBudgetExceeded)


def _is_gone(exc: GitHubError) -> bool:
    return exc.status in GONE_STATUSES and not isinstance(exc, ResponseBudgetExceeded)


def _problem(code: str, message: str, target: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "target": target}


def collect(bound: Bound, client: ReadClient) -> dict[str, Any]:
    """Perform the bounded read-only GitHub reads and derive the reconciliation artifact."""

    repo = bound.repository
    repository: dict[str, Any] | None = None
    labels: dict[str, bool] = {}
    issues: dict[str, dict[str, Any]] = {}
    missing: list[int] = []
    moved: list[dict[str, Any]] = []
    wanted = {name.casefold() for name in bound.labels}
    searches: list[dict[str, Any]] = []
    root_children: list[dict[str, Any]] | None = None
    parents: dict[str, dict[str, Any] | None] = {}
    dependencies: dict[str, list[dict[str, Any]]] = {}
    epic = next((target for target in bound.targets if target.ref["kind"] == "epic"), None)
    reused_items = [target for target in bound.targets if target.ref["kind"] == "item" and target.action == "reuse"]

    def found(number: int | None) -> bool:
        return (
            number is not None
            and number not in missing
            and str(number) in issues
            and not issues[str(number)]["pull_request"]
        )

    transport: dict[str, Any] | None = None
    try:
        try:
            client.preflight()
        except GitHubError as exc:
            transport = _problem("persist.github_unavailable", str(exc))
            raise
        path = f"/repos/{repo}"
        raw = client.request("GET", path)
        if not isinstance(raw, dict):
            raise _unexpected(path)
        permissions: dict[str, Any] = raw["permissions"] if isinstance(raw.get("permissions"), dict) else {}
        repository = {
            "id": raw.get("id"),
            "full_name": raw.get("full_name"),
            "has_issues": raw.get("has_issues"),
            "archived": raw.get("archived"),
            "disabled": raw.get("disabled"),
            "push": bool(permissions.get("push")),
        }
        for name in bound.labels:
            try:
                client.request("GET", f"/repos/{repo}/labels/{urllib.parse.quote(name, safe='')}")
                labels[name] = True
            except GitHubError as exc:
                if not _is_404(exc):
                    raise
                labels[name] = False
        for target in bound.targets:
            if target.action != "reuse" or target.issue is None:
                continue
            path = f"/repos/{repo}/issues/{target.issue}"
            try:
                fact = _issue_fact(client.request("GET", path), path, labels_of_interest=wanted)
            except GitHubError as exc:
                if not _is_gone(exc):
                    raise
                missing.append(target.issue)
                continue
            if fact["number"] != target.issue or fact["repository"] != repo:
                missing.append(target.issue)
                moved.append(
                    {
                        "requested": target.issue,
                        "repository": fact["repository"],
                        "number": fact["number"],
                        "html_url": fact["html_url"],
                    }
                )
            else:
                issues[str(target.issue)] = fact
        for target in bound.targets:
            if target.search is None:
                continue
            query = " ".join(f'"{term}"' for term in target.search["terms"]) + f" repo:{repo} is:issue"
            limit = target.search["limit"]
            path = "/search/issues?" + urllib.parse.urlencode({"q": query, "per_page": str(limit)})
            raw = client.request("GET", path)
            if (
                not isinstance(raw, dict)
                or not _is_int(raw.get("total_count"))
                or not isinstance(raw.get("incomplete_results"), bool)
                or not isinstance(raw.get("items"), list)
            ):
                raise _unexpected(path)
            numbers: list[int] = []
            for item in raw["items"]:
                fact = _issue_fact(item, path, labels_of_interest=None)
                if fact["repository"] != repo:
                    continue
                numbers.append(fact["number"])
                issues.setdefault(str(fact["number"]), fact)
            searches.append(
                {
                    "target": target.ref,
                    "query": query,
                    "limit": limit,
                    "total_count": raw["total_count"],
                    "incomplete_results": raw["incomplete_results"],
                    "results": sorted(numbers),
                }
            )
        if bound.shape == "epic":
            if epic is not None and epic.action == "reuse" and found(epic.issue):
                path = f"/repos/{repo}/issues/{epic.issue}/sub_issues"
                refs = []
                for item in client.paginated_get(path):
                    fact = _issue_fact(item, path, labels_of_interest=None)
                    refs.append(_ref(fact))
                    if fact["repository"] == repo:
                        issues.setdefault(str(fact["number"]), fact)
                root_children = sorted(refs, key=_ref_key)
            for target in reused_items:
                if not found(target.issue):
                    continue
                path = f"/repos/{repo}/issues/{target.issue}/parent"
                try:
                    parent_fact = _issue_fact(client.request("GET", path), path, labels_of_interest=None)
                    parents[str(target.issue)] = _ref(parent_fact)
                except GitHubError as exc:
                    if not _is_404(exc):
                        raise
                    parents[str(target.issue)] = None
        if bound.edges:
            issue_of = {target.ref["id"]: target.issue for target in reused_items}
            endpoints: set[int] = set()
            for source, destination in bound.edges:
                first, second = issue_of.get(source), issue_of.get(destination)
                if first is not None and second is not None:
                    endpoints.update(number for number in (first, second) if found(number))
            for target in reused_items:
                if target.issue in endpoints and str(target.issue) not in dependencies:
                    path = f"/repos/{repo}/issues/{target.issue}/dependencies/blocked_by"
                    dependencies[str(target.issue)] = sorted(
                        (
                            _ref(_issue_fact(item, path, labels_of_interest=None))
                            for item in client.paginated_get(path)
                        ),
                        key=_ref_key,
                    )
    except ResponseBudgetExceeded as exc:
        transport = _problem("persist.github_budget", str(exc))
    except GitHubError as exc:
        if transport is None:
            transport = _problem("persist.github_read_failed", str(exc))

    problems: list[dict[str, Any]] = []
    needs: list[dict[str, Any]] = []
    capabilities: list[str] = []
    plan: dict[str, Any] | None = None
    def blocked_by(number: int | None) -> set[int]:
        return {ref["number"] for ref in dependencies.get(str(number), []) if ref["repository"] == repo}

    if transport is not None:
        problems = [transport]
    else:
        assert repository is not None
        if (repository.get("full_name") or "").casefold() != repo:
            problems.append(
                _problem(
                    "persist.destination_mismatch",
                    f"GitHub reports repository {repository.get('full_name')!r}, not {repo!r}",
                )
            )
        for name, exists in labels.items():
            if not exists:
                problems.append(_problem("persist.missing_label", f"label {name!r} does not exist in {repo}"))
        for target in bound.targets:
            label = _ref_label(target.ref)
            if target.action == "block":
                problems.append(_problem("persist.agent_block", f"{label} is blocked: {target.basis}", target.ref))
            if target.action == "reuse" and target.issue is not None:
                reused_fact = issues.get(str(target.issue))
                if target.issue in missing or reused_fact is None:
                    relocation = next((entry for entry in moved if entry["requested"] == target.issue), None)
                    message = (
                        f"{label} reuses #{target.issue}, which GitHub resolves to "
                        f"{relocation['repository']}#{relocation['number']} (moved or transferred)"
                        if relocation is not None
                        else f"{label} reuses missing issue #{target.issue}"
                    )
                    problems.append(_problem("persist.reuse_missing", message, target.ref))
                elif reused_fact["pull_request"]:
                    problems.append(
                        _problem(
                            "persist.reuse_pull_request",
                            f"{label} reuses #{target.issue}, which is a pull request",
                            target.ref,
                        )
                    )
                elif reused_fact["state"] != "open":
                    problems.append(
                        _problem(
                            "persist.reuse_not_open",
                            f"{label} reuses #{target.issue}, whose state is {reused_fact['state']!r}; reopening is never planned",
                            target.ref,
                        )
                    )
            for number, candidate in sorted(target.candidates.items()):
                if candidate["classification"] == "conflict":
                    problems.append(
                        _problem(
                            "persist.candidate_conflict",
                            f"{label} has conflicting existing issue #{number}: {candidate['basis']}",
                            target.ref,
                        )
                    )
        root_issue = epic.issue if epic is not None and epic.action == "reuse" else None
        if bound.shape == "epic":
            for target in reused_items:
                if not found(target.issue):
                    continue
                parent = parents.get(str(target.issue))
                if parent is not None and (parent["repository"] != repo or parent["number"] != root_issue):
                    problems.append(
                        _problem(
                            "persist.wrong_parent",
                            f"{_ref_label(target.ref)} reuses #{target.issue}, which is already a sub-issue of "
                            f"{parent['repository']}#{parent['number']}; Ticket never re-parents",
                            target.ref,
                        )
                    )
        issue_of = {target.ref["id"]: target.issue for target in reused_items}
        for source, destination in bound.edges:
            first, second = issue_of.get(source), issue_of.get(destination)
            if found(first) and found(second) and first in blocked_by(second):
                problems.append(
                    _problem(
                        "persist.dependency_conflict",
                        f"item {source} depends on {destination}, but #{second} is already blocked by #{first}",
                    )
                )
        if not problems:
            for target, search in (
                (target, search)
                for search in searches
                for target in bound.targets
                if target.ref == search["target"]
            ):
                label = _ref_label(target.ref)
                for number in search["results"]:
                    if number not in target.candidates:
                        needs.append(
                            _problem(
                                "persist.unclassified_candidate",
                                f"{label} search returned #{number} without a candidates entry",
                                target.ref,
                            )
                        )
                if search["incomplete_results"] or search["total_count"] > len(search["results"]):
                    needs.append(
                        _problem(
                            "persist.search_truncated",
                            f"{label} search returned {len(search['results'])} of {search['total_count']} matches",
                            target.ref,
                        )
                    )
            if epic is not None and root_children is not None:
                reused_numbers = {target.issue for target in reused_items}
                for number in (ref["number"] for ref in root_children if ref["repository"] == repo):
                    if number not in reused_numbers and number not in epic.candidates:
                        needs.append(
                            _problem(
                                "persist.unclassified_candidate",
                                f"epic root #{root_issue} has existing child #{number} without a candidates entry",
                                epic.ref,
                            )
                        )
            actions: list[dict[str, Any]] = []
            for target in bound.targets:
                if target.action == "block":
                    continue
                if target.action == "create":
                    to_apply = list(bound.labels)
                else:
                    existing = {name.casefold() for name in issues[str(target.issue)]["labels"]}
                    to_apply = [name for name in bound.labels if name.casefold() not in existing]
                entry: dict[str, Any] = {
                    "target": target.ref,
                    "action": target.action,
                    "issue": target.issue if target.action == "reuse" else None,
                    "labels_to_apply": to_apply,
                }
                if target.action == "create":
                    entry.update(bound.content[_ref_label(target.ref)])
                actions.append(entry)
            sub_issue_links: list[dict[str, Any]] = []
            if bound.shape == "epic":
                for target in bound.targets:
                    if target.ref["kind"] != "item":
                        continue
                    if target.action == "create":
                        sub_issue_links.append({"child": target.ref["id"], "child_issue": None})
                    elif target.action == "reuse" and found(target.issue) and parents.get(str(target.issue)) is None:
                        sub_issue_links.append({"child": target.ref["id"], "child_issue": target.issue})
            dependency_links: list[dict[str, Any]] = []
            for source, destination in bound.edges:
                first, second = issue_of.get(source), issue_of.get(destination)
                present = (
                    first is not None
                    and second is not None
                    and second in blocked_by(first)
                )
                if not present:
                    dependency_links.append(
                        {"from": source, "to": destination, "from_issue": first, "to_issue": second}
                    )
            needed = set()
            if any(action["action"] == "create" or action["labels_to_apply"] for action in actions) or (
                sub_issue_links or dependency_links
            ):
                needed.add("issues")
            if any(action["labels_to_apply"] for action in actions) or sub_issue_links or dependency_links:
                needed.add("write")
            if sub_issue_links:
                needed.add("sub_issues")
            if dependency_links:
                needed.add("dependencies")
            capabilities = [name for name in CAPABILITY_ORDER if name in needed]
            if "issues" in capabilities and (
                not repository.get("has_issues") or repository.get("archived") or repository.get("disabled")
            ):
                problems.append(
                    _problem("persist.issues_unavailable", f"{repo} has issues disabled or is archived or disabled")
                )
            if "write" in capabilities and not repository.get("push"):
                problems.append(
                    _problem("persist.write_permission_missing", f"the authenticated gh user cannot write to {repo}")
                )
            if not problems and not needs:
                plan = {
                    "actions": actions,
                    "sub_issue_links": sub_issue_links,
                    "dependency_links": dependency_links,
                }

    status = "blocked" if problems else "needs-classification" if needs else "ready"
    artifact: dict[str, Any] = {
        "contract": CONTRACT,
        "status": status,
        "binding": bound.binding,
        "shape": bound.shape,
        "repository": repository,
        "labels": labels,
        "issues_content_trust": "untrusted-github-data",
        "issues": issues,
        "missing_issues": sorted(missing),
        "moved_issues": sorted(moved, key=lambda entry: entry["requested"]),
        "searches": searches,
        "hierarchy": None if bound.shape == "single" else {"root_children": root_children, "parents": parents},
        "dependencies": dependencies,
        "decisions": [
            {
                "target": target.ref,
                "action": target.action,
                "issue": target.issue,
                "basis": target.basis,
                "search": target.search,
                "candidates": {str(number): value for number, value in sorted(target.candidates.items())},
            }
            for target in bound.targets
        ],
        "problems": problems + needs,
        "required_capabilities": capabilities,
        "preflighted_capabilities": [name for name in capabilities if name in ("issues", "write")],
        "plan": plan,
    }
    artifact["receipt"] = _receipt(artifact)
    return artifact


def _write_atomic(destination: Path, text: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _problem_diagnostics(artifact: dict[str, Any], *, phase: str, path: Path) -> list[dict[str, Any]]:
    diagnostics = []
    for problem in artifact["problems"]:
        required_action = problem["message"] if problem["code"] == "persist.github_unavailable" else None
        diagnostics.append(
            _diag(
                problem["code"],
                problem["message"],
                phase=phase,
                artifact="reconciliation.json",
                path=path,
                required_action=required_action,
            )
        )
    return diagnostics


def build(args: argparse.Namespace, client_factory: Callable[[], ReadClient]) -> int:
    try:
        bound = bind_local(args)
    except LocalRejection as exc:
        _emit({"valid": False, "diagnostics": exc.diagnostics})
        return 1
    artifact = collect(bound, client_factory())
    output = Path(args.output)
    try:
        _write_atomic(output, _canonical(artifact).decode("ascii") + "\n")
    except OSError as exc:
        _emit(
            {
                "valid": False,
                "diagnostics": [
                    _diag(
                        "persist.reconcile_output_unwritable",
                        f"cannot write {output.name}: {exc}",
                        phase="reconcile",
                        artifact="reconciliation.json",
                        path=output,
                    )
                ],
            }
        )
        return 1
    if artifact["status"] == "ready":
        _emit({"valid": True, "status": "ready", "receipt": artifact["receipt"], "reconciliation": str(output)})
        return 0
    _emit({"valid": False, "diagnostics": _problem_diagnostics(artifact, phase="reconcile", path=output)})
    return 1


def stored_ready(args: argparse.Namespace) -> tuple[Bound, dict[str, Any]]:
    """Return the local binding and the stored ready reconciliation it still binds, without reading GitHub.

    Raises ``LocalRejection`` for every other outcome.
    """

    bound = bind_local(args)
    path = Path(args.reconciliation)

    def fail(code: str, message: str) -> LocalRejection:
        return LocalRejection([_diag(code, message, phase="verify", artifact="reconciliation.json", path=path)])

    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise fail("persist.reconciliation_invalid", f"cannot read reconciliation.json: {exc}") from exc
    if (
        not isinstance(stored, dict)
        or stored.get("receipt") != _receipt(stored)
        or not contract_matches(stored.get("contract"), CONTRACT)
    ):
        raise fail("persist.reconciliation_invalid", "reconciliation.json receipt or contract does not verify")
    if stored.get("status") != "ready":
        raise fail("persist.reconciliation_not_ready", f"reconciliation status is {stored.get('status')!r}")
    if stored.get("binding") != bound.binding:
        raise fail("persist.reconciliation_stale", "persist input, preview, reconciliation input, or labels changed")
    return bound, stored


def verified(args: argparse.Namespace, client_factory: Callable[[], ReadClient]) -> dict[str, Any]:
    """Return the stored ready reconciliation only when it still binds and replays unchanged.

    Raises ``LocalRejection`` for every other outcome; GitHub is read only after the local binding holds.
    """

    bound, stored = stored_ready(args)
    path = Path(args.reconciliation)
    current = collect(bound, client_factory())
    transport = [problem for problem in current["problems"] if problem["code"] in TRANSPORT_CODES]
    if transport:
        raise LocalRejection(_problem_diagnostics({"problems": transport}, phase="verify", path=path))
    if current["receipt"] != stored["receipt"]:
        differing = sorted(key for key in current if key != "receipt" and current.get(key) != stored.get(key))
        raise LocalRejection(
            [
                _diag(
                    "persist.reconciliation_stale",
                    f"material facts changed: {', '.join(differing)}",
                    phase="verify",
                    artifact="reconciliation.json",
                    path=path,
                )
            ]
        )
    return stored


def verify(args: argparse.Namespace, client_factory: Callable[[], ReadClient]) -> int:
    try:
        stored = verified(args, client_factory)
    except LocalRejection as exc:
        _emit({"valid": False, "fresh": False, "diagnostics": exc.diagnostics})
        return 1
    _emit({"valid": True, "fresh": True, "receipt": stored["receipt"]})
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--backend", required=True)
        command.add_argument("--github-repo")
        command.add_argument("--label", action="append", default=[])
        command.add_argument("--persist-input", type=Path, required=True)
        command.add_argument("--preview", type=Path, required=True)
        command.add_argument("--reconciliation-input", type=Path, required=True)
        if name == "build":
            command.add_argument("--output", type=Path, required=True)
            command.add_argument("--publish-confirmation", default=None)
        else:
            command.add_argument("--reconciliation", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None, *, client_factory: Callable[[], ReadClient] = GitHubClient) -> int:
    args = _parser().parse_args(argv)
    if args.command == "build":
        return build(args, client_factory)
    return verify(args, client_factory)


if __name__ == "__main__":
    raise SystemExit(main())

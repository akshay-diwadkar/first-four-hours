#!/usr/bin/env python3
"""Validate one proportional ticket-scope draft (single or epic)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from compile_persist import _is_local_id, is_local_store
from scope_workspace import WORKSPACE_DIR as SCOPE_NAMESPACE, WORKSPACE_PARTS as SCOPE_PARTS
from _skill_protocol_runtime import compatible_version, compatible_version_pattern
from github_common import TICKET_VERSION, ConfigError, normalize_github_repo_target, snapshot_digest

SKILL_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = SKILL_ROOT / "references" / "issue-plan-contract.json"
METADATA_RE = re.compile(r"<!-- ticket-scope-metadata -->\s*```json\s*(?P<json>\{.*?\})\s*```", re.DOTALL)
BINDINGS_RE = re.compile(r"<!-- ticket-scope-bindings -->\s*```json\s*(?P<json>\{.*?\})\s*```", re.DOTALL)
RESERVED_BINDINGS = frozenset({"inputs", "source", "checkout"})


class HandoffContractError(ValueError):
    pass


def load_contract() -> dict[str, Any]:
    try:
        value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HandoffContractError(f"unable to read contract: {exc}") from exc
    if not isinstance(value, dict):
        raise HandoffContractError("contract must contain a JSON object")
    return value


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HandoffContractError(f"unable to read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise HandoffContractError(f"{label} must contain a JSON object")
    return value


def _nested(data: dict[str, Any], dotted: str) -> Any:
    current: Any = data
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _git(repo_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise HandoffContractError(f"unable to inspect git checkout: {' '.join(args)}") from exc
    return result.stdout.strip()


def _git_bytes(repo_root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise HandoffContractError(f"unable to inspect git checkout: {' '.join(args)}") from exc
    return result.stdout


def parse_metadata(text: str) -> dict[str, Any]:
    match = METADATA_RE.search(text)
    if match is None:
        raise HandoffContractError("missing ticket-scope metadata JSON block")
    value = json.loads(match.group("json"))
    if not isinstance(value, dict):
        raise HandoffContractError("ticket-scope metadata must be an object")
    return value


def canonicalize_metadata(text: str) -> str:
    match = METADATA_RE.search(text)
    if match is None:
        return text
    value = json.loads(match.group("json"))
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return text[: match.start("json")] + canonical + text[match.end("json") :]


def _escape_untrusted_metadata(text: str, contract: dict[str, Any]) -> str:
    fence = contract.get("untrusted_fence", {})
    begin, end = fence.get("begin", ""), fence.get("end", "")
    if not begin or not end or begin not in text or end not in text:
        return text
    begin_index = text.find(begin)
    end_index = text.find(end, begin_index + len(begin))
    if end_index < 0:
        return text
    head, span, tail = text[:begin_index], text[begin_index : end_index + len(end)], text[end_index + len(end) :]
    span = re.sub(
        r"<!--(\s*ticket-scope-(?:metadata|bindings)\s*)-->",
        lambda match: "&lt;!--" + match.group(1) + "--&gt;",
        span,
        flags=re.IGNORECASE,
    )
    return head + span + tail


def canonical_body(text: str) -> str:
    try:
        contract = load_contract()
    except HandoffContractError:
        contract = {}
    canonical = canonicalize_metadata(text.replace("\r\n", "\n").replace("\r", "\n"))
    if contract:
        canonical = _escape_untrusted_metadata(canonical, contract)
    if canonical == "":
        return canonical
    return canonical.rstrip("\n") + "\n"


def _strip_untrusted_fence(text: str, contract: dict[str, Any]) -> tuple[str, list[str]]:
    errors: list[str] = []
    fence = contract.get("untrusted_fence", {})
    begin, end = fence.get("begin", ""), fence.get("end", "")
    if not begin or not end:
        return text, ["contract is missing the untrusted fence"]
    begin_count = text.count(begin)
    end_count = text.count(end)
    if begin_count == 0 and end_count == 0:
        return text, []
    if begin_count != 1 or end_count != 1:
        return text, ["untrusted fence requires exactly one begin and one end marker"]
    begin_index = text.find(begin)
    end_index = text.find(end)
    if end_index < begin_index:
        return text, ["untrusted fence begin marker must precede the end marker"]
    section = contract.get("untrusted_section", "Issue Claims (Untrusted)")
    heading_re = re.compile(r"(?m)^## " + re.escape(section) + r"\s*$")
    heading_match = heading_re.search(text[:begin_index])
    if heading_match is None:
        return text, ["untrusted fence must appear inside the Issue Claims (Untrusted) section"]
    if text[heading_match.end() : begin_index].strip():
        errors.append("content between the untrusted section heading and the begin marker is not allowed")
    tail = text[end_index + len(end) :]
    next_heading = re.search(r"(?m)^## ", tail)
    gap = tail if next_heading is None else tail[: next_heading.start()]
    if BINDINGS_RE.sub("", gap).strip():
        errors.append("content between the untrusted end marker and the next section is not allowed")
    stripped = text[:begin_index] + text[end_index + len(end) :]
    return stripped, errors


def _section_bodies(text: str) -> list[tuple[str, str]]:
    headings = list(re.finditer(r"(?m)^## (?P<name>.+?)\s*$", text))
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        sections.append((match.group("name"), text[match.end() : end]))
    return sections


def _valid_issue_url(url: Any, repo: str, number: int) -> bool:
    if not isinstance(url, str):
        return False
    m = re.fullmatch(r"https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/issues/(\d+)", url.strip())
    if not m:
        return False
    return m.group(1).casefold() == repo.casefold() and int(m.group(2)) == number


def _is_local(inputs: Any) -> bool:
    return isinstance(inputs, dict) and inputs.get("backend") == "local"


def _ref_ok(value: Any, local: bool) -> bool:
    if local:
        return _is_local_id(value)
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_local_scope_inputs(inputs: dict[str, Any], mode: str) -> list[str]:
    errors: list[str] = []
    local_store = inputs.get("local_store")
    if not is_local_store(local_store):
        errors.append("scope_inputs.local_store must be a relative repository path of plain segments outside .first-four-hours/")
    if mode == "single":
        unknown = set(inputs) - {"task", "backend", "local_store", "mode", "ticket"}
        if unknown:
            errors.append(f"single-issue mode forbids fields: {sorted(unknown)}")
        ticket = inputs.get("ticket")
        if not isinstance(ticket, dict) or set(ticket) != {"number"} or not _ref_ok(ticket["number"], True):
            errors.append("scope_inputs.ticket must carry a local record id")
        return errors
    unknown = set(inputs) - {"task", "backend", "local_store", "mode", "epic", "override", "exclusions"}
    if unknown:
        errors.append(f"index mode forbids fields: {sorted(unknown)}")
    epic = inputs.get("epic")
    if not isinstance(epic, dict) or set(epic) != {"number"} or not _ref_ok(epic["number"], True):
        errors.append("scope_inputs.epic must carry a local record id")
    override = inputs.get("override", None)
    if override is not None and (
        not isinstance(override, dict) or set(override) != {"issue"} or not _ref_ok(override["issue"], True)
    ):
        errors.append("scope_inputs.override must be null or an object with a local record id")
    exclusions = inputs.get("exclusions", [])
    if not isinstance(exclusions, list) or not all(_ref_ok(x, True) for x in exclusions):
        errors.append("scope_inputs.exclusions must be an array of local record ids")
    elif len(set(exclusions)) != len(exclusions):
        errors.append("scope_inputs.exclusions must not contain duplicates")
    return errors


def _validate_scope_inputs(inputs: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(inputs, dict):
        return ["scope inputs must be an object"]
    task = inputs.get("task")
    if not isinstance(task, dict) or not isinstance(task.get("text"), str) or not task["text"].strip():
        errors.append("scope_inputs.task.text must be a non-empty string")
    elif set(task) - {"text", "constraints"}:
        errors.append("scope_inputs.task carries unknown fields")
    elif not isinstance(task.get("constraints", []), list) or not all(
        isinstance(x, str) for x in task.get("constraints", [])
    ):
        errors.append("scope_inputs.task.constraints must be an array of strings")
    if inputs.get("backend") not in ("github", "local"):
        errors.append("scope_inputs.backend must be github or local")
    local = _is_local(inputs)
    mode = inputs.get("mode")
    if local:
        if mode not in ("single", "index"):
            errors.append("scope_inputs.mode must be one of: single, index")
            return errors
        return errors + _validate_local_scope_inputs(inputs, mode)
    try:
        normalized = normalize_github_repo_target(str(inputs.get("repository")))
        if normalized != inputs.get("repository"):
            errors.append("scope_inputs.repository must normalize to owner/repo")
        repo = normalized
    except (ConfigError, TypeError, AttributeError):
        errors.append("scope_inputs.repository must be a GitHub owner/repo target")
        repo = ""
    if mode not in ("single", "index"):
        errors.append("scope_inputs.mode must be one of: single, index")
        return errors
    if mode == "single":
        allowed = {"task", "backend", "repository", "mode", "ticket"}
        unknown = set(inputs) - allowed
        if unknown:
            errors.append(f"single-issue mode forbids fields: {sorted(unknown)}")
        ticket = inputs.get("ticket")
        if not isinstance(ticket, dict) or not isinstance(ticket.get("number"), int) or ticket["number"] <= 0:
            errors.append("scope_inputs.ticket must carry a positive issue number")
        else:
            if set(ticket) - {"number", "url"}:
                errors.append("scope_inputs.ticket carries unknown fields")
            if repo and not _valid_issue_url(ticket.get("url"), repo, ticket["number"]):
                errors.append("scope_inputs.ticket.url must identify the declared issue in the declared repository")
    else:
        allowed = {"task", "backend", "repository", "mode", "epic", "override", "exclusions"}
        unknown = set(inputs) - allowed
        if unknown:
            errors.append(f"index mode forbids fields: {sorted(unknown)}")
        epic = inputs.get("epic")
        if not isinstance(epic, dict) or not isinstance(epic.get("number"), int) or epic["number"] <= 0:
            errors.append("scope_inputs.epic must carry a positive issue number")
        else:
            if set(epic) - {"number", "url"}:
                errors.append("scope_inputs.epic carries unknown fields")
            if repo and not _valid_issue_url(epic.get("url"), repo, epic["number"]):
                errors.append("scope_inputs.epic.url must identify the declared epic in the declared repository")
        override = inputs.get("override", None)
        if override is not None:
            if not isinstance(override, dict) or not isinstance(override.get("issue"), int) or override["issue"] <= 0:
                errors.append("scope_inputs.override must be null or an object with a positive issue number")
            elif set(override) - {"issue"}:
                errors.append("scope_inputs.override carries unknown fields")
        exclusions = inputs.get("exclusions", [])
        if not isinstance(exclusions, list) or not all(isinstance(x, int) and x > 0 for x in exclusions):
            errors.append("scope_inputs.exclusions must be an array of positive issue numbers")
        elif len(set(exclusions)) != len(exclusions):
            errors.append("scope_inputs.exclusions must not contain duplicates")
    return errors


def _snapshot_issues(payload: dict[str, Any]) -> list[dict[str, Any]]:
    issues = payload.get("issues")
    return [x for x in (issues or []) if isinstance(x, dict)]


def _dependency_graph(payload: dict[str, Any]) -> dict[Any, set[Any]]:
    deps: dict[Any, set[Any]] = {}
    for e in payload.get("edges") or []:
        if not isinstance(e, dict):
            continue
        s, t, rel = e.get("source"), e.get("target"), e.get("type")
        if e.get("target_kind", "issue") != "issue" or not isinstance(s, (int, str)) or not isinstance(t, (int, str)):
            continue
        if rel in {"depends_on", "blocked_by"}:
            deps.setdefault(s, set()).add(t)
        elif rel == "blocks":
            deps.setdefault(t, set()).add(s)
    return deps


def _reachable(start: int, deps: dict[int, set[int]]) -> set[int]:
    seen: set[int] = set()
    pending = list(deps.get(start, set()))
    while pending:
        cur = pending.pop()
        if cur in seen:
            continue
        seen.add(cur)
        pending.extend(deps.get(cur, set()) - seen)
    return seen


def _has_cycle(start: int, deps: dict[int, set[int]]) -> bool:
    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(node: int) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(c) for c in deps.get(node, set())):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return visit(start)


def _selection_uncertainty(
    payload: dict[str, Any], root: Any, affected: set[Any], accounted_unknown: set[Any] | None = None
) -> tuple[bool, bool]:
    coverage = payload.get("coverage")
    incomplete = isinstance(coverage, dict) and coverage.get("state") == "partial"
    unresolved = payload.get("unresolved") or []
    budgets = payload.get("budgets")
    exhausted = budgets.get("exhausted") if isinstance(budgets, dict) else []
    if not isinstance(exhausted, list):
        exhausted = []
    if not incomplete and not unresolved and not exhausted:
        return False, False
    if incomplete and not unresolved and not exhausted:
        return True, False
    global_u = False
    local_u = False
    linked: dict[Any, set[Any]] = {}
    for e in payload.get("edges") or []:
        if isinstance(e, dict) and e.get("type") == "linked_pr" and e.get("target_kind") == "pull_request":
            if isinstance(e.get("target"), (int, str)) and isinstance(e.get("source"), (int, str)):
                linked.setdefault(e["target"], set()).add(e["source"])
    root_targets = {
        e.get("target") for e in payload.get("edges") or [] if isinstance(e, dict) and e.get("source") == root
    }
    accounted = accounted_unknown or set()
    for item in [*unresolved, *exhausted]:
        if not isinstance(item, dict):
            global_u = True
            continue
        if item.get("type") == "related" and item.get("selection_relevant") is not True:
            continue
        # Uncertainty already accounted for by an explicitly declared unknown
        # candidate never poisons another subject's eligibility on its own.
        if isinstance(item.get("target"), (int, str)) and item["target"] in accounted:
            continue
        if isinstance(item.get("source"), (int, str)) and item["source"] in accounted and item.get("target") == root:
            continue
        source, target = item.get("source"), item.get("target")
        affected_endpoint = target if item.get("type") in {"blocks", "supersedes"} else source
        src_set = {affected_endpoint} if isinstance(affected_endpoint, (int, str)) else set()
        if source is None and item.get("target_kind") == "pull_request" and isinstance(target, (int, str)):
            src_set.update(linked.get(target, set()))
        if root in src_set or (not src_set and (target is None or target in root_targets)):
            global_u = True
        elif src_set.intersection(affected) or (item.get("target_kind") != "pull_request" and target in affected):
            local_u = True
    return global_u, local_u


def _positive_membership(payload: dict[str, Any], root: int, child: int) -> bool:
    for e in payload.get("edges") or []:
        if not isinstance(e, dict):
            continue
        prov = e.get("provenance")
        if not prov:
            continue
        if e.get("source") == root and e.get("type") == "child" and e.get("target") == child:
            return True
        if e.get("source") == child and e.get("type") == "parent" and e.get("target") == root:
            return True
    return False


EVIDENCE_RE = re.compile(
    r"^\s*[-*]\s*`(?P<path>[^`]+):(?P<line>\d+)`\s*\|\s*anchor:\s*`(?P<anchor>[^`]+)`\s*\|\s*observation:\s*(?P<body>.+)$"
)
LEGACY_RECORD_RE = re.compile(r"^\s*[-*]\s*(CAND|SEL|SC|F|D|C|CH|T)-\S*")
FORBIDDEN_SECTIONS = {
    "Selection Stage",
    "Outcome and Scope",
    "Local Evidence Ledger",
    "Issue-Level Decisions",
    "Constraints and Protected Behavior",
    "Risks and Open Questions",
    "Blueprint Handoff",
    "Implementation Plan",
    "Test Plan",
    "Verification Plan",
    "Rollout",
    "Edit List",
}


def derive_reserved(
    inputs: dict[str, Any],
    payload: dict[str, Any],
    repo_root: Path,
    evidence_paths: list[str],
    work_item: int | str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    local = _is_local(inputs)
    issues_by = {i.get("number"): i for i in _snapshot_issues(payload)}
    root_number = (inputs.get("ticket") or inputs.get("epic") or {}).get("number")
    root_issue = issues_by.get(root_number, {})
    work_node = issues_by.get(work_item, {}) if _ref_ok(work_item, local) else {}
    source: dict[str, Any]
    if local:
        source = {
            "backend": "local",
            "local_store": inputs.get("local_store"),
            "mode": inputs.get("mode"),
            "root": {"number": root_number, "url": root_issue.get("url"), "sha256": root_issue.get("sha256")},
            "work_item": None,
            "snapshot_digest": payload.get("digest"),
            "fetched_at": payload.get("fetched_at"),
        }
        if _ref_ok(work_item, local):
            source["work_item"] = {
                "number": work_item,
                "url": work_node.get("url"),
                "sha256": work_node.get("sha256"),
                "state": work_node.get("state"),
            }
    else:
        source = {
            "repo": inputs.get("repository"),
            "mode": inputs.get("mode"),
            "root": {"number": root_number, "url": root_issue.get("url"), "updated_at": root_issue.get("updated_at")},
            "work_item": None,
            "snapshot_digest": payload.get("digest"),
            "fetched_at": payload.get("fetched_at"),
        }
        if _ref_ok(work_item, local):
            source["work_item"] = {
                "number": work_item,
                "url": work_node.get("url"),
                "updated_at": work_node.get("updated_at"),
                "state": work_node.get("state"),
                "state_reason": work_node.get("state_reason"),
            }
    actual_root = Path(_git(repo_root, "rev-parse", "--show-toplevel")).resolve()
    try:
        remote_repo = normalize_github_repo_target(_git(actual_root, "remote", "get-url", "origin"))
    except (ConfigError, HandoffContractError):
        remote_repo = ""
    porcelain = _git_bytes(actual_root, "status", "--porcelain")
    evidence_files = []
    for rel in sorted(set(evidence_paths)):
        p = repo_root.resolve() / rel
        try:
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            digest = ""
        evidence_files.append({"path": rel, "sha256": digest})
    checkout = {
        "root": str(actual_root),
        "remote_repo": remote_repo,
        "commit": _git(actual_root, "rev-parse", "HEAD"),
        "dirty": bool(porcelain),
        "dirty_fingerprint": hashlib.sha256(porcelain).hexdigest(),
        "evidence_files": evidence_files,
    }
    return source, checkout


def validate_plan(plan_path: Path, issue_json: Path, repo_root: Path, scope_inputs: Path) -> list[str]:
    contract = load_contract()
    errors: list[str] = []
    try:
        raw_text = Path(plan_path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [str(exc)]
    # receipt-free body for drafts that are already sealed (re-validation path uses draft file too)
    head, sep, final = raw_text.removesuffix("\n").rpartition("\n")
    if sep and re.fullmatch(rf"<!-- ticket-scope: {compatible_version_pattern(TICKET_VERSION)}; sha256: [0-9a-f]{{64}} -->", final.strip()):
        raw_text = head + "\n"
    trusted_text, fence_errors = _strip_untrusted_fence(raw_text, contract)
    errors.extend(fence_errors)
    matches = list(METADATA_RE.finditer(trusted_text))
    if len(matches) != 1:
        errors.append("exactly one trusted ticket-scope metadata block is required")
        return errors
    # the authored metadata opens the scope; the sealer's reserved bindings close it
    first_heading = re.search(r"(?m)^## ", trusted_text)
    if first_heading is not None and matches[0].start() > first_heading.start():
        errors.append("ticket-scope metadata must precede any content section")
    bindings: dict[str, Any] = {}
    binding_matches = list(BINDINGS_RE.finditer(trusted_text))
    if len(binding_matches) > 1:
        errors.append("at most one ticket-scope bindings block is allowed")
    elif binding_matches:
        if trusted_text[binding_matches[0].end() :].strip():
            errors.append("ticket-scope bindings must follow every content section")
        try:
            parsed = json.loads(binding_matches[0].group("json"))
        except json.JSONDecodeError:
            return errors + ["ticket-scope bindings are malformed"]
        if not isinstance(parsed, dict) or set(parsed) != RESERVED_BINDINGS:
            return errors + ["ticket-scope bindings must hold exactly inputs, source, and checkout"]
        bindings = parsed
    try:
        metadata = json.loads(matches[0].group("json"))
    except json.JSONDecodeError:
        return errors + ["ticket-scope metadata is malformed"]
    if not isinstance(metadata, dict):
        return errors + ["ticket-scope metadata must be an object"]
    if not compatible_version(metadata.get("contract_version"), TICKET_VERSION):
        errors.append(f"metadata contract_version must share major version {TICKET_VERSION.split('.')[0]} with {TICKET_VERSION!r}")
    allowed_agent = {
        "contract_version",
        "mode",
        "status",
        "task",
        "work_item",
        "selection",
        "questions",
        "blockers",
        "unknowns",
        "close_evidence",
        "decomposition_reason",
    }
    for key in metadata:
        if key in RESERVED_BINDINGS:
            errors.append(f"reserved {key} belongs in the ticket-scope-bindings footer")
        elif key not in allowed_agent:
            errors.append(f"metadata carries unknown field: {key}")
    metadata = {**metadata, **bindings}
    status = metadata.get("status")
    if status not in contract.get("statuses", []):
        errors.append(f"status must be one of: {', '.join(contract.get('statuses', []))}")
    mode = metadata.get("mode")
    if mode not in ("single", "index"):
        errors.append("metadata.mode must be one of: single, index")
    task = metadata.get("task")
    if not isinstance(task, dict) or not isinstance(task.get("text"), str) or not task["text"].strip():
        errors.append("metadata task.text must be a non-empty string")
    elif not isinstance(task.get("constraints", []), list):
        errors.append("metadata task.constraints must be an array")
    work_item = metadata.get("work_item")
    # conditional optional fields
    questions = metadata.get("questions", None)
    if questions is not None:
        if (
            not isinstance(questions, list)
            or not questions
            or not all(
                isinstance(q, dict)
                and isinstance(q.get("question"), str)
                and q["question"].strip()
                and q.get("reason") in contract.get("question_reason_codes", [])
                for q in questions
            )
        ):
            errors.append("metadata questions must be a non-empty array of {question, reason} objects")
    blockers = metadata.get("blockers", None)
    if blockers is not None:
        if (
            not isinstance(blockers, list)
            or not blockers
            or not all(isinstance(b, str) and b.strip() for b in blockers)
        ):
            errors.append("metadata blockers must be a non-empty array of strings")
    unknowns = metadata.get("unknowns", None)
    if unknowns is not None:
        if (
            not isinstance(unknowns, list)
            or not unknowns
            or not all(isinstance(b, str) and b.strip() for b in unknowns)
        ):
            errors.append("metadata unknowns must be a non-empty array of strings")
    close_evidence = metadata.get("close_evidence", None)
    if close_evidence is not None:
        if (
            not isinstance(close_evidence, list)
            or not close_evidence
            or not all(isinstance(b, str) and b.strip() for b in close_evidence)
        ):
            errors.append("metadata close_evidence must be a non-empty array of strings")
    decomposition_reason = metadata.get("decomposition_reason", None)
    if decomposition_reason is not None:
        if not isinstance(decomposition_reason, str) or not decomposition_reason.strip():
            errors.append("metadata decomposition_reason must be a non-empty string")
    selection = metadata.get("selection", None)
    if selection is not None and not isinstance(selection, dict):
        errors.append("metadata selection must be an object")
    # placeholder tokens in trusted body without metadata
    body_wo_meta = BINDINGS_RE.sub("", METADATA_RE.sub("", trusted_text))
    for token in contract.get("placeholder_tokens", []):
        if re.search(rf"\b{re.escape(token)}\b", body_wo_meta, re.IGNORECASE):
            errors.append(f"unresolved placeholder token: {token}")
    # sections
    sections = _section_bodies(body_wo_meta)
    names = [n for n, _ in sections]
    allowed = contract.get("allowed_sections", [])
    order = contract.get("section_order", allowed)
    for n in names:
        if n in FORBIDDEN_SECTIONS or n not in allowed:
            errors.append(f"section not part of the contract: {n}")
    if len(set(names)) != len(names):
        errors.append("sections must not repeat")
    order_index = {n: i for i, n in enumerate(order)}
    if [order_index.get(n, -1) for n in names] != sorted(order_index.get(n, -1) for n in names):
        errors.append("sections must appear in contract order")
    for n in FORBIDDEN_SECTIONS:
        if n in names:
            errors.append(f"retired section is not allowed: {n}")
    # legacy record syntax in trusted body
    for i, line in enumerate(body_wo_meta.splitlines(), 1):
        if LEGACY_RECORD_RE.match(line):
            errors.append(f"line {i}: retired record notation is not allowed")
            break
    # inputs
    try:
        inputs = _load_object(Path(scope_inputs), "scope inputs JSON")
    except HandoffContractError as exc:
        return errors + [str(exc)]
    errors.extend(_validate_scope_inputs(inputs))
    local = _is_local(inputs)
    has_work_item = _ref_ok(work_item, local)
    if work_item is not None and not has_work_item:
        errors.append(
            "metadata work_item must be null or a local record id"
            if local
            else "metadata work_item must be null or a positive issue number"
        )
    if isinstance(task, dict) and task != inputs.get("task"):
        errors.append("metadata.task does not match scope_inputs.json")
    if mode != inputs.get("mode"):
        errors.append("metadata.mode does not match scope_inputs.mode")
    # snapshot
    try:
        payload = _load_object(Path(issue_json), "issue JSON")
    except HandoffContractError as exc:
        return errors + [str(exc)]
    expected_trust = contract["snapshot_requirements"]["local_content_trust" if local else "content_trust"]
    if _nested(payload, "metadata.content_trust") != expected_trust:
        errors.append(f"issue JSON must declare metadata.content_trust={expected_trust}")
    if (_nested(payload, "metadata.backend") == "local") != local:
        errors.append("snapshot backend does not match scope_inputs.backend")
    snap_mode = _nested(payload, "metadata.mode")
    if snap_mode not in ("single", "index"):
        errors.append("snapshot metadata.mode must be one of: single, index")
    if snap_mode != mode:
        errors.append("metadata.mode does not match the snapshot mode")
    if not local:
        try:
            in_repo = normalize_github_repo_target(str(inputs.get("repository")))
            snap_repo = normalize_github_repo_target(str(payload.get("repo")))
            if in_repo != snap_repo:
                errors.append("snapshot repo does not match scope_inputs.repository")
        except ConfigError as exc:
            errors.append(str(exc))
    elif _nested(payload, "metadata.local_store") != inputs.get("local_store"):
        errors.append("snapshot local_store does not match scope_inputs.local_store")
    if not compatible_version(payload.get("graph_snapshot_version"), TICKET_VERSION):
        errors.append(f"snapshot graph_snapshot_version must share major version {TICKET_VERSION.split('.')[0]} with {TICKET_VERSION!r}")
    # digest + receipt
    try:
        computed = snapshot_digest(payload)
    except Exception:
        computed = ""
    if payload.get("digest") != computed:
        errors.append("snapshot digest does not match its content")
    # root binding
    root_declared = inputs.get("ticket") or inputs.get("epic") or {}
    root_number = root_declared.get("number")
    has_root = _ref_ok(root_number, local)
    snap_root = payload.get("root") or {}
    if snap_root.get("issue_number") != root_number:
        errors.append("snapshot root must be the requested ticket/epic")
    if not local and has_root and inputs.get("repository"):
        expected_url = f"https://github.com/{inputs['repository']}/issues/{root_number}"
        if str(snap_root.get("url", "")).casefold() != expected_url.casefold():
            errors.append("snapshot root url does not match the requested issue")
    issues_by = {x.get("number"): x for x in _snapshot_issues(payload)}
    if has_root and root_number not in issues_by:
        errors.append("snapshot must contain the requested root issue")
    if mode == "single" and payload.get("candidate_tickets") != [root_number]:
        errors.append("single snapshot candidate_tickets must be exactly the requested ticket")
    # freshness for fetched candidates (checked after selection parsing)
    # selection + membership
    candidates: list[dict[str, Any]] = []
    if mode == "single":
        if selection is not None:
            errors.append("single-issue mode forbids a selection payload")
        if has_work_item and work_item != root_number:
            errors.append("single work_item must be the requested ticket")
    else:
        override = inputs.get("override")
        exclusions: list[int] = inputs.get("exclusions", []) or []
        known = [c for c in (payload.get("candidate_tickets") or []) if c not in exclusions]
        if override is not None:
            if selection is not None:
                errors.append("explicit override mode carries no selection payload")
            over_issue = override.get("issue") if isinstance(override, dict) else None
            if _ref_ok(over_issue, local):
                terminal_without_subject = work_item is None and status != "plan-ready"
                if not terminal_without_subject and over_issue not in (payload.get("candidate_tickets") or []):
                    errors.append("explicit override issue must be a known candidate")
                if not terminal_without_subject and over_issue in exclusions:
                    errors.append("explicit override issue must not be excluded")
                if not terminal_without_subject and not _positive_membership(payload, root_number, over_issue):
                    errors.append("explicit override issue lacks positive root-child membership evidence")
                if has_work_item and work_item != over_issue:
                    errors.append("work_item must match the explicit override")
                if work_item is None and status == "plan-ready":
                    errors.append("plan-ready override requires the override work_item")
        else:
            if not isinstance(selection, dict):
                errors.append("index best-next mode requires a selection payload")
            else:
                raw_cands = selection.get("candidates")
                known = [c for c in (payload.get("candidate_tickets") or []) if c not in exclusions]
                if not isinstance(raw_cands, list):
                    errors.append("selection.candidates must be an array")
                elif not raw_cands and known:
                    errors.append("selection.candidates cannot be empty when known candidates exist")
                else:
                    seen = set()
                    for c in raw_cands:
                        if not isinstance(c, dict) or not _ref_ok(c.get("issue"), local):
                            errors.append("selection candidates must carry positive issue numbers")
                            continue
                        if c["issue"] in seen:
                            errors.append("selection candidate issues must be unique")
                        seen.add(c["issue"])
                        if c.get("readiness") not in contract.get("readiness_states", []):
                            errors.append(f"candidate #{c['issue']} readiness is not allowed")
                        basis = c.get("basis")
                        if not isinstance(basis, str) or not basis.strip():
                            errors.append(f"candidate #{c['issue']} basis must be a non-empty string")
                        candidates.append({"issue": c["issue"], "readiness": c.get("readiness"), "basis": basis or ""})
                    if set(seen) != set(known):
                        errors.append(
                            f"selection candidates must equal known candidates minus exclusions ({sorted(known)})"
                        )
                if selection.get("rationale") is not None and (
                    not isinstance(selection.get("rationale"), str) or not selection["rationale"].strip()
                ):
                    errors.append("selection.rationale must be a non-empty string when present")
                alts = selection.get("alternatives", None)
                if alts is not None:
                    if not isinstance(alts, list) or not all(
                        isinstance(a, dict)
                        and _ref_ok(a.get("issue"), local)
                        and isinstance(a.get("reason"), str)
                        and a["reason"].strip()
                        for a in alts
                    ):
                        errors.append("selection.alternatives must be an array of {issue, reason}")
                for key in selection:
                    if key not in {"candidates", "rationale", "alternatives"}:
                        errors.append(f"selection carries unknown field: {key}")
    # evidence + sections semantics
    bodies = dict(sections)
    has_outcome = "Observable outcome" in bodies
    has_evidence = "Current evidence" in bodies
    has_settled = "Settled decisions" in bodies
    has_protected = "Protected constraints" in bodies
    if work_item is None:
        if has_outcome or has_evidence or has_settled or has_protected:
            errors.append("a result with no work_item cannot carry narrowing evidence")
    if status == "plan-ready":
        if not has_outcome:
            errors.append("plan-ready requires ## Observable outcome")
        if not has_evidence:
            errors.append("plan-ready requires ## Current evidence")
        if has_work_item and work_item not in issues_by and mode == "single":
            errors.append("plan-ready work_item must resolve to a fetched issue")
    else:
        if has_outcome:
            errors.append(f"status {status} cannot carry ## Observable outcome")
    if has_outcome and not bodies.get("Observable outcome", "").strip():
        errors.append("## Observable outcome must not be empty")
    # evidence bullets
    evidence_paths: list[str] = []
    if has_evidence:
        lines = [ln for ln in bodies["Current evidence"].splitlines() if ln.strip()]
        bullets = [ln for ln in lines if re.match(r"^\s*[-*]\s+", ln)]
        if not bullets:
            errors.append("## Current evidence must carry at least one evidence bullet")
        for ln in bullets:
            m = EVIDENCE_RE.match(ln)
            if not m:
                errors.append(f"evidence bullet must use `path:line` | anchor | observation form: {ln.strip()[:60]}")
                break
            rel = m.group("path")
            try:
                target = (Path(repo_root).resolve() / rel).resolve()
                target.relative_to(Path(repo_root).resolve())
            except ValueError:
                errors.append(f"evidence path escapes the repository: {rel}")
                continue
            relative_parts = target.relative_to(Path(repo_root).resolve()).parts
            if tuple(part.casefold() for part in relative_parts[:2]) == SCOPE_PARTS:
                errors.append(f"evidence must not cite the {SCOPE_NAMESPACE}/ handoff namespace: {rel}")
                continue
            if ".scratch" in target.parts or target == Path(issue_json).resolve() or not target.is_file():
                errors.append(f"evidence must cite an existing repository file: {rel}")
                continue
            try:
                file_lines = target.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError):
                errors.append(f"evidence file cannot be read: {rel}")
                continue
            no = int(m.group("line"))
            if no < 1 or no > len(file_lines) or m.group("anchor") not in file_lines[no - 1]:
                errors.append(f"evidence anchor is absent from {rel}:{no}")
            else:
                evidence_paths.append(rel)
    # citations: #refs in trusted body (without metadata) must resolve
    snap_numbers = {x.get("number") for x in _snapshot_issues(payload)}
    if not local:
        for num in re.findall(r"#(\d+)", body_wo_meta):
            if int(num) not in snap_numbers and int(num) != (root_number or -1):
                # allow task text refs? be strict: must resolve
                errors.append(f"citation #{num} does not resolve to a snapshot issue")
                break
        for field in ("blockers", "unknowns", "close_evidence"):
            for entry in metadata.get(field) or []:
                for num in re.findall(r"#(\d+)", str(entry)):
                    if int(num) not in snap_numbers:
                        errors.append(f"{field} citation #{num} does not resolve to a snapshot issue")
                        break
    # status obligations
    if status == "plan-ready":
        for f in ("questions", "blockers", "unknowns", "close_evidence", "decomposition_reason"):
            if metadata.get(f):
                errors.append(f"status plan-ready cannot carry {f}")
        if work_item is None:
            errors.append("plan-ready requires a work_item")
    elif status == "needs-info":
        if not metadata.get("questions") and not metadata.get("unknowns"):
            errors.append("status needs-info requires questions or unknowns")
        for f in ("blockers", "close_evidence", "decomposition_reason"):
            if metadata.get(f):
                errors.append(f"status needs-info cannot carry {f}")
    elif status == "blocked":
        if not metadata.get("blockers"):
            errors.append("status blocked requires blockers")
        for f in ("close_evidence", "decomposition_reason"):
            if metadata.get(f):
                errors.append(f"status blocked cannot carry {f}")
    elif status == "close-candidate":
        if not metadata.get("close_evidence"):
            errors.append("status close-candidate requires close_evidence")
        for f in ("questions", "blockers", "unknowns", "decomposition_reason"):
            if metadata.get(f):
                errors.append(f"status close-candidate cannot carry {f}")
    elif status == "needs-decomposition":
        if not metadata.get("decomposition_reason"):
            errors.append("status needs-decomposition requires decomposition_reason")
        for f in ("questions", "blockers", "close_evidence"):
            if metadata.get(f):
                errors.append(f"status needs-decomposition cannot carry {f}")
    # selection-tie reason needs >=2 ready
    ready_count = sum(1 for c in candidates if c.get("readiness") == "ready")
    if isinstance(metadata.get("questions"), list) and any(
        isinstance(q, dict) and q.get("reason") == "selection-tie" for q in metadata["questions"]
    ):
        if ready_count < 2 and not (mode == "index" and inputs.get("override") is None and status == "needs-info"):
            # needs-info tie without winner still needs 2 ready candidates in selection
            pass
        if ready_count < 2:
            errors.append("a selection-tie question requires at least 2 ready candidates")
    # rationale/alternatives for best-next winner
    if mode == "index" and inputs.get("override") is None and isinstance(selection, dict):
        if status == "plan-ready" and has_work_item:
            selected = [c for c in candidates if c.get("issue") == work_item]
            if len(selected) != 1 or selected[0].get("readiness") != "ready":
                errors.append("best-next plan-ready work_item must be declared exactly once as ready")
        others_ready = [c for c in candidates if c.get("readiness") == "ready" and c.get("issue") != work_item]
        if has_work_item and status == "plan-ready":
            if not selection.get("rationale"):
                errors.append("best-next plan-ready requires selection.rationale")
            alts = selection.get("alternatives") or []
            alt_issues = sorted(a.get("issue") for a in alts if isinstance(a, dict))
            if sorted(c.get("issue") for c in others_ready) != alt_issues:
                errors.append("selection.alternatives must name every other ready candidate exactly once")
            if not others_ready and alts:
                errors.append("selection.alternatives must be absent when no other ready candidate exists")
        if work_item is None and selection.get("rationale"):
            errors.append("selection.rationale requires a selected work_item")
    # graph contradictions for ready declarations
    deps = _dependency_graph(payload)
    edges = [e for e in payload.get("edges") or [] if isinstance(e, dict)]
    issues_map = issues_by
    budgets = payload.get("budgets")
    if budgets is not None and not isinstance(budgets, dict):
        errors.append("snapshot.budgets must be an object")
    # validate each ready candidate + work_item eligibility for plan-ready
    to_check_ready = [(c["issue"], f"candidate #{c['issue']}") for c in candidates if c.get("readiness") == "ready"]
    # work_item in single/override mode has no candidate entry; check it as ready-claim when plan-ready
    if status == "plan-ready" and has_work_item:
        if mode == "single" or (mode == "index" and inputs.get("override") is not None):
            to_check_ready.append((work_item, f"work_item #{work_item}"))
        elif (
            mode == "index" and inputs.get("override") is None and work_item not in {c.get("issue") for c in candidates}
        ):
            errors.append("best-next plan-ready work_item must be a declared candidate")
    for num, label in to_check_ready:
        node = issues_map.get(num)
        if node is None:
            errors.append(f"{label} ready has no fetched issue node")
            continue
        if node.get("state") == "closed":
            errors.append(f"{label} ready contradicts terminal issue #{num}")
        affected = {num} | _reachable(num, deps)
        if _has_cycle(num, deps):
            errors.append(f"{label} ready contradicts a dependency cycle")
        for pre in sorted(affected - {num}):
            pre_node = issues_map.get(pre)
            if pre_node is None:
                errors.append(f"{label} ready contradicts unresolved prerequisite #{pre}")
            elif not (pre_node.get("state") == "closed" and pre_node.get("state_reason") == "completed"):
                errors.append(f"{label} ready contradicts unresolved prerequisite #{pre}")
        superseded = any(
            (e.get("source") == num and e.get("type") in {"duplicate_of", "superseded_by"})
            or (e.get("target") == num and e.get("type") == "supersedes")
            for e in edges
            if e.get("target_kind", "issue") == "issue"
        )
        if superseded:
            errors.append(f"{label} ready contradicts explicit supersession evidence")
        accounted_unknown = {c["issue"] for c in candidates if c.get("readiness") == "unknown"}
        g_u, l_u = _selection_uncertainty(
            payload, root_number if has_root else -1, affected, accounted_unknown
        )
        is_best_next = mode == "index" and inputs.get("override") is None
        if is_best_next:
            if g_u:
                errors.append(f"{label} ready is not trustworthy under global incomplete coverage")
            elif l_u:
                errors.append(f"{label} ready is affected by incomplete eligibility evidence")
        else:
            if l_u:
                errors.append(f"{label} ready is affected by incomplete eligibility evidence")
    # unfetched unknown candidates: only unknown allowed, needs acquisition cause + membership
    for c in candidates:
        if c["issue"] not in issues_map:
            if c.get("readiness") != "unknown":
                errors.append(f"candidate #{c['issue']} is unfetched and must be unknown")
            else:
                basis = (c.get("basis") or "").lower()
                if not any(
                    k in basis
                    for k in ("unresolved", "exhaust", "missing", "budget", "not_found", "not found", "unfetched")
                ):
                    errors.append(f"candidate #{c['issue']} unknown must cite its acquisition cause")
                if has_root and not _positive_membership(payload, root_number, c["issue"]):
                    errors.append(f"candidate #{c['issue']} unknown lacks positive root-child membership evidence")
    # unknown basis must not pretend freshness: skip timestamp check for absent nodes
    fetched_at = payload.get("fetched_at")
    for c in candidates:
        node = issues_map.get(c["issue"])
        if node is None:
            continue
        upd = node.get("updated_at")
        if isinstance(fetched_at, str) and isinstance(upd, str) and upd > fetched_at:
            errors.append(f"candidate #{c['issue']} is stale: updated_at postdates fetched_at")
    # reserved bindings: verify when supplied (sealed re-validation), forbid forgery
    has_reserved = any(k in metadata for k in ("inputs", "source", "checkout"))
    if has_reserved:
        try:
            exp_source, exp_checkout = derive_reserved(
                inputs, payload, Path(repo_root).resolve(), evidence_paths, work_item
            )
        except HandoffContractError as exc:
            errors.append(str(exc))
        else:
            if metadata.get("inputs") != inputs:
                errors.append("reserved inputs do not match scope_inputs.json")
            got_source = metadata.get("source")
            if got_source != exp_source:
                errors.append("reserved source does not match the fetched snapshot")
            got_checkout = metadata.get("checkout")
            if not isinstance(got_checkout, dict):
                errors.append("reserved checkout is malformed")
            else:
                for k in ("root", "remote_repo", "commit", "dirty", "dirty_fingerprint", "evidence_files"):
                    if got_checkout.get(k) != exp_checkout.get(k):
                        errors.append(f"reserved checkout.{k} does not match the live checkout")
                        break
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handoff")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--issue-json", required=True)
    parser.add_argument("--scope-inputs", required=True)
    args = parser.parse_args(argv)
    try:
        errors = validate_plan(Path(args.handoff), Path(args.issue_json), Path(args.repo_root), Path(args.scope_inputs))
    except (HandoffContractError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors = [str(exc)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Ticket-scope validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

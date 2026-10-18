#!/usr/bin/env python3
"""Fetch and verify a bounded, read-only GitHub epic graph."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from _skill_protocol_runtime import compatible_version
from github_common import (
    ConfigError,
    GitHubClient,
    GitHubError,
    ResponseBudgetExceeded,
    TICKET_VERSION,
    ensure_external_output,
    graph_receipt,
    normalize_github_repo_target,
    positive_int,
    snapshot_digest,
)

DEFAULT_MAX_NODES = 100
DEFAULT_MAX_EDGES = 400
DEFAULT_MAX_DEPTH = 6
DEFAULT_MAX_COMMENTS = 100
DEFAULT_MAX_COMMENTS_PER_ISSUE = 20
DEFAULT_MAX_RESPONSE_BYTES = 8 * 1024 * 1024

SKILL_ROOT = Path(__file__).resolve().parents[1]
TASK_RE = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s+(.+?)\s*$")
LINE_RELATION_RE = re.compile(
    r"^\s*(Parent(?:\s+epic)?|Child(?:ren)?|Depends\s+on|Blocked\s+by|Blocks|Related|"
    r"Duplicate\s+of|Supersedes|Superseded\s+by)\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)
PR_URL_RE = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/pull/(\d+)\b")
ISSUE_URL_RE = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/issues/(\d+)\b")
CROSS_REF_RE = re.compile(r"(?<![A-Za-z0-9_.-])([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)\b")
SHORT_REF_RE = re.compile(r"(?<![\w/])#(\d+)\b")

RELATION_NAMES = {
    "parent": "parent",
    "parent epic": "parent",
    "child": "child",
    "children": "child",
    "depends on": "depends_on",
    "blocked by": "blocked_by",
    "blocks": "blocks",
    "related": "related",
    "duplicate of": "duplicate_of",
    "supersedes": "supersedes",
    "superseded by": "superseded_by",
}
INVERSE = {
    "parent": "child",
    "child": "parent",
    "depends_on": "blocks",
    "blocked_by": "blocks",
    "blocks": "blocked_by",
    "supersedes": "superseded_by",
    "superseded_by": "supersedes",
}
TRAVERSED_RELATIONS = {"child", "depends_on", "blocked_by", "parent"}


@dataclass(frozen=True)
class Limits:
    max_nodes: int
    max_edges: int
    max_depth: int
    max_comments: int
    max_comments_per_issue: int
    max_response_bytes: int


def normalize_user(raw: dict[str, Any] | None) -> str | None:
    login = raw.get("login") if raw else None
    return str(login) if login else None


def normalize_labels(raw_labels: Iterable[dict[str, Any]]) -> list[str]:
    return sorted({str(label["name"]) for label in raw_labels if label.get("name")})


def normalize_comment(raw: dict[str, Any], issue_number: int) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "node_id": raw.get("node_id"),
        "issue_number": issue_number,
        "author": normalize_user(raw.get("user")),
        "body": raw.get("body") or "",
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "url": raw.get("html_url"),
    }


def normalize_issue(raw: dict[str, Any], comments: list[dict[str, Any]]) -> dict[str, Any]:
    if "pull_request" in raw:
        raise ConfigError(f"#{raw.get('number')} is a pull request, not a GitHub issue")
    return {
        "number": raw.get("number"),
        "node_id": raw.get("node_id"),
        "title": raw.get("title") or "",
        "body": raw.get("body") or "",
        "state": raw.get("state"),
        "state_reason": raw.get("state_reason"),
        "labels": normalize_labels(raw.get("labels") or []),
        "assignees": sorted(login for login in (normalize_user(user) for user in raw.get("assignees") or []) if login),
        "author": normalize_user(raw.get("user")),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "closed_at": raw.get("closed_at"),
        "url": raw.get("html_url"),
        "comments": comments,
    }


def normalize_pr(raw: dict[str, Any]) -> dict[str, Any]:
    def branch(value: dict[str, Any] | None) -> dict[str, Any]:
        value = value or {}
        repo = value.get("repo") or {}
        return {"ref": value.get("ref"), "repo": repo.get("full_name")}

    return {
        "number": raw.get("number"),
        "node_id": raw.get("node_id"),
        "state": raw.get("state"),
        "draft": bool(raw.get("draft")),
        "merged_at": raw.get("merged_at"),
        "merge_commit_sha": raw.get("merge_commit_sha"),
        "head": branch(raw.get("head")),
        "base": branch(raw.get("base")),
        "updated_at": raw.get("updated_at"),
        "url": raw.get("html_url"),
    }


def _source(
    kind: str, issue: int, *, updated_at: str | None, locator: str, comment_id: int | None = None
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "evidence": kind,
        "source_issue": issue,
        "locator": locator,
        "observed_updated_at": updated_at,
        "confidence": "explicit",
    }
    if comment_id is not None:
        result["comment_id"] = comment_id
    return result


def _refs(text: str, repo: str) -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    spans: list[tuple[int, int]] = []
    for pattern, kind in ((ISSUE_URL_RE, "url"), (CROSS_REF_RE, "cross-repository")):
        for match in pattern.finditer(text):
            target_repo, raw_number = match.groups()
            found.append((target_repo, int(raw_number), kind))
            spans.append(match.span())
    for match in SHORT_REF_RE.finditer(text):
        if any(start <= match.start() < end for start, end in spans):
            continue
        found.append((repo, int(match.group(1)), "short"))
    return found


def _relationship_text(text: str) -> str:
    """Remove quoted and fenced Markdown while preserving line locators."""

    kept: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        stripped = line.lstrip()
        marker = "```" if stripped.startswith("```") else "~~~" if stripped.startswith("~~~") else None
        if marker:
            fence = None if fence == marker else marker if fence is None else fence
            kept.append("")
            continue
        if fence is not None or stripped.startswith(">"):
            kept.append("")
        else:
            kept.append(line)
    return "\n".join(kept)


def parse_relations(
    text: str,
    *,
    repo: str,
    issue_number: int,
    source_updated_at: str | None,
    source_kind: str,
    comment_id: int | None = None,
    task_lists_are_children: bool = False,
) -> list[dict[str, Any]]:
    relations: list[dict[str, Any]] = []
    relationship_text = _relationship_text(text)
    for line_number, line in enumerate(relationship_text.splitlines(), 1):
        task = TASK_RE.match(line) if task_lists_are_children else None
        relation_match = LINE_RELATION_RE.match(line)
        if task:
            for target_repo, target, _ in _refs(task.group(1), repo):
                relations.append(
                    {
                        "source": issue_number,
                        "type": "child",
                        "target_kind": "issue",
                        "target": target,
                        "target_repo": target_repo,
                        "selection_relevant": True,
                        "provenance": _source(
                            "task-list",
                            issue_number,
                            updated_at=source_updated_at,
                            locator=f"line:{line_number}",
                            comment_id=comment_id,
                        ),
                    }
                )
        if relation_match:
            relation = RELATION_NAMES[relation_match.group(1).lower()]
            for target_repo, target, _ in _refs(relation_match.group(2), repo):
                relations.append(
                    {
                        "source": issue_number,
                        "type": relation,
                        "target_kind": "issue",
                        "target": target,
                        "target_repo": target_repo,
                        "selection_relevant": relation != "related",
                        "provenance": _source(
                            source_kind,
                            issue_number,
                            updated_at=source_updated_at,
                            locator=f"line:{line_number}",
                            comment_id=comment_id,
                        ),
                    }
                )

    for pr_repo, raw_number in PR_URL_RE.findall(relationship_text):
        relations.append(
            {
                "source": issue_number,
                "type": "linked_pr",
                "target_kind": "pull_request",
                "target": int(raw_number),
                "target_repo": pr_repo,
                "selection_relevant": True,
                "provenance": _source(
                    source_kind,
                    issue_number,
                    updated_at=source_updated_at,
                    locator="explicit-pr-url",
                    comment_id=comment_id,
                ),
            }
        )
    return relations


class GraphBuilder:
    def __init__(self, client: GitHubClient, repo: str, root: int, limits: Limits, comment_policy: str) -> None:
        self.client = client
        self.repo = repo
        self.root = root
        self.limits = limits
        self.comment_policy = comment_policy
        self.issues: dict[int, dict[str, Any]] = {}
        self.pull_requests: dict[int, dict[str, Any]] = {}
        self.edges: dict[tuple[int, str, str, int], dict[str, Any]] = {}
        self.candidates: list[int] = []
        self.unresolved: list[dict[str, Any]] = []
        self.exhausted: list[dict[str, Any]] = []
        self.comments_used = 0

    def _exhaust(self, kind: str, *, source: int | None = None, target: int | None = None) -> None:
        item: dict[str, Any] = {"kind": kind}
        if source is not None:
            item["source"] = source
        if target is not None:
            item["target"] = target
        if item not in self.exhausted:
            self.exhausted.append(item)

    def _unresolved(self, reason: str, relation: dict[str, Any]) -> None:
        item = {
            "reason": reason,
            "source": relation.get("source"),
            "type": relation.get("type"),
            "selection_relevant": relation.get("selection_relevant", True),
            "target_kind": relation.get("target_kind", "issue"),
            "target": relation.get("target"),
            "target_repo": relation.get("target_repo", self.repo),
        }
        if relation.get("provenance"):
            item["provenance"] = relation["provenance"]
        if item not in self.unresolved:
            self.unresolved.append(item)

    def add_edge(self, relation: dict[str, Any]) -> bool:
        target = relation.get("target")
        if not isinstance(target, int) or target <= 0:
            self._unresolved("invalid_reference", relation)
            return False
        target_repo = relation.get("target_repo")
        if not isinstance(target_repo, str) or target_repo.casefold() != self.repo.casefold():
            self._unresolved("unsupported_external", relation)
            return False
        key = (relation["source"], relation["type"], relation["target_kind"], target)
        existing = self.edges.get(key)
        if existing:
            provenance = relation["provenance"]
            if provenance not in existing["provenance"]:
                existing["provenance"].append(provenance)
            existing["selection_relevant"] = existing["selection_relevant"] or relation["selection_relevant"]
            return True
        if len(self.edges) >= self.limits.max_edges:
            self._exhaust("edges", source=relation["source"], target=target)
            self._unresolved("budget_exhausted", relation)
            return False
        self.edges[key] = {
            "source": relation["source"],
            "type": relation["type"],
            "target_kind": relation["target_kind"],
            "target": target,
            "selection_relevant": relation["selection_relevant"],
            "provenance": [relation["provenance"]],
        }
        if relation["source"] == self.root and relation["type"] == "child" and target not in self.candidates:
            self.candidates.append(target)
        return True

    def _fetch_comments(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        number = int(raw["number"])
        if self.comment_policy == "none" or int(raw.get("comments") or 0) <= 0:
            return []
        remaining = self.limits.max_comments - self.comments_used
        if remaining <= 0:
            self._exhaust("comments", source=number)
            return []
        limit = min(self.limits.max_comments_per_issue, remaining)
        raw_comments = self.client.paginated_get(f"/repos/{self.repo}/issues/{number}/comments", item_limit=limit)
        comments = [normalize_comment(comment, number) for comment in raw_comments]
        self.comments_used += len(comments)
        if len(comments) >= limit and int(raw.get("comments") or 0) > len(comments):
            self._exhaust("comments", source=number)
        return comments

    def _native_children(self, number: int, updated_at: str | None) -> list[dict[str, Any]]:
        raw_children = self.client.paginated_get(f"/repos/{self.repo}/issues/{number}/sub_issues")
        result = []
        for index, child in enumerate(raw_children, 1):
            child_number = child.get("number")
            if isinstance(child_number, int) and child_number > 0:
                result.append(
                    {
                        "source": number,
                        "type": "child",
                        "target_kind": "issue",
                        "target": child_number,
                        "target_repo": self.repo,
                        "selection_relevant": True,
                        "provenance": _source(
                            "github-native-sub-issue",
                            number,
                            updated_at=updated_at,
                            locator=f"sub-issue:{index}",
                        ),
                    }
                )
        return result

    def _fetch_issue(self, number: int, depth: int) -> list[dict[str, Any]]:
        if number in self.issues:
            return []
        if len(self.issues) + len(self.pull_requests) >= self.limits.max_nodes:
            self._exhaust("nodes", target=number)
            return []
        try:
            raw = self.client.request("GET", f"/repos/{self.repo}/issues/{number}")
        except GitHubError as exc:
            if number != self.root and exc.status == 404:
                self.unresolved.append({"reason": "not_found", "target_kind": "issue", "target": number})
                return []
            raise
        if not isinstance(raw, dict):
            raise GitHubError(f"GitHub API returned unexpected issue payload for #{number}")
        if "pull_request" in raw:
            raise ConfigError(f"#{number} is a pull request, not a GitHub issue")

        body_relations = parse_relations(
            raw.get("body") or "",
            repo=self.repo,
            issue_number=number,
            source_updated_at=raw.get("updated_at"),
            source_kind="issue-body",
            task_lists_are_children=number == self.root,
        )
        self.issues[number] = normalize_issue(raw, [])
        native_relations = self._native_children(number, raw.get("updated_at"))
        comments = self._fetch_comments(raw)
        comment_relations: list[dict[str, Any]] = []
        for comment in comments:
            comment_relations.extend(
                parse_relations(
                    comment["body"],
                    repo=self.repo,
                    issue_number=number,
                    source_updated_at=comment.get("updated_at"),
                    source_kind="issue-comment",
                    comment_id=comment.get("id"),
                    task_lists_are_children=number == self.root,
                )
            )
        self.issues[number]["comments"] = comments
        return body_relations + native_relations + comment_relations

    def _fetch_pr(self, number: int) -> None:
        if number in self.pull_requests:
            return
        if len(self.issues) + len(self.pull_requests) >= self.limits.max_nodes:
            self._exhaust("nodes", target=number)
            return
        try:
            raw = self.client.request("GET", f"/repos/{self.repo}/pulls/{number}")
        except GitHubError as exc:
            if exc.status == 404:
                self.unresolved.append({"reason": "not_found", "target_kind": "pull_request", "target": number})
                return
            raise
        if not isinstance(raw, dict):
            raise GitHubError(f"GitHub API returned unexpected pull request payload for #{number}")
        self.pull_requests[number] = normalize_pr(raw)

    def _timeline_prs(self, issue_numbers: list[int]) -> None:
        for issue_number in issue_numbers:
            if issue_number not in self.issues:
                continue
            try:
                events = self.client.paginated_get(f"/repos/{self.repo}/issues/{issue_number}/timeline")
            except ResponseBudgetExceeded:
                self._exhaust("response_bytes", source=issue_number)
                return
            for event in events:
                if event.get("event") != "cross-referenced":
                    continue
                source_issue = (event.get("source") or {}).get("issue") or {}
                if "pull_request" not in source_issue:
                    continue
                pr_number = source_issue.get("number")
                repo_url = source_issue.get("repository_url") or ""
                if not isinstance(pr_number, int) or not repo_url.casefold().endswith(f"/{self.repo.casefold()}"):
                    continue
                relation = {
                    "source": issue_number,
                    "type": "linked_pr",
                    "target_kind": "pull_request",
                    "target": pr_number,
                    "target_repo": self.repo,
                    "selection_relevant": True,
                    "provenance": _source(
                        "github-timeline-cross-reference",
                        issue_number,
                        updated_at=self.issues[issue_number].get("updated_at"),
                        locator=f"event:{event.get('id', pr_number)}",
                    ),
                }
                self.add_edge(relation)

    def _decision_issue_numbers(self, mode: str) -> list[int]:
        """Return the fetched issue subjects whose facts can affect selection."""
        dependencies: dict[int, set[int]] = {}
        for relation in self.edges.values():
            source, target, relation_type = relation["source"], relation["target"], relation["type"]
            if relation_type in {"depends_on", "blocked_by"}:
                dependencies.setdefault(source, set()).add(target)
            elif relation_type == "blocks":
                dependencies.setdefault(target, set()).add(source)
        starts = {self.root}
        if mode == "index":
            starts.update(self.candidates)
        seen: set[int] = set()
        pending = list(starts)
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            pending.extend(dependencies.get(current, set()) - seen)
        return sorted(number for number in seen if number in self.issues)

    def build(self, mode: str) -> dict[str, Any]:
        queue: deque[tuple[int, int]] = deque([(self.root, 0)])
        scheduled = {self.root}
        try:
            while queue:
                number, depth = queue.popleft()
                relations = self._fetch_issue(number, depth)
                for relation in relations:
                    accepted = self.add_edge(relation)
                    if not accepted or relation.get("target_kind") != "issue":
                        continue
                    should_traverse = relation["type"] in TRAVERSED_RELATIONS or (
                        relation["selection_relevant"]
                        and relation["type"] in {"duplicate_of", "supersedes", "superseded_by"}
                    )
                    target = relation["target"]
                    if mode == "single":
                        if relation["type"] not in {
                            "depends_on",
                            "blocked_by",
                            "duplicate_of",
                            "supersedes",
                            "superseded_by",
                        }:
                            continue
                        if relation["type"] in {"duplicate_of", "supersedes", "superseded_by"} and not relation.get(
                            "selection_relevant"
                        ):
                            continue
                        if target in scheduled:
                            continue
                    elif not should_traverse or target in scheduled:
                        continue
                    if depth + 1 > self.limits.max_depth:
                        self._exhaust("depth", source=number, target=target)
                        self._unresolved("budget_exhausted", relation)
                        continue
                    scheduled.add(target)
                    queue.append((target, depth + 1))
            self._timeline_prs(self._decision_issue_numbers(mode))
            for edge in list(self.edges.values()):
                if edge["target_kind"] == "pull_request":
                    self._fetch_pr(edge["target"])
        except ResponseBudgetExceeded:
            if self.root not in self.issues:
                raise
            self._exhaust("response_bytes")

        return self.snapshot(mode)

    def _canonical_edges(self) -> list[dict[str, Any]]:
        authored = []
        keys = set(self.edges)
        for key in sorted(keys):
            edge = dict(self.edges[key])
            edge["provenance"] = sorted(
                edge["provenance"], key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"))
            )
            authored.append(edge)
        derived = []
        for edge in authored:
            inverse = INVERSE.get(edge["type"])
            if not inverse or edge["target_kind"] != "issue":
                continue
            inverse_key = (edge["target"], inverse, "issue", edge["source"])
            if inverse_key in keys:
                continue
            derived.append(
                {
                    "source": edge["target"],
                    "type": inverse,
                    "target_kind": "issue",
                    "target": edge["source"],
                    "selection_relevant": edge["selection_relevant"],
                    "derived_from": {
                        "source": edge["source"],
                        "type": edge["type"],
                        "target": edge["target"],
                    },
                }
            )
        return sorted(
            authored + derived,
            key=lambda item: (
                item["source"],
                item["type"],
                item["target_kind"],
                item["target"],
                "derived_from" in item,
            ),
        )

    def snapshot(self, mode: str) -> dict[str, Any]:
        fetched_at = datetime.now(timezone.utc).isoformat()
        incomplete = bool(self.exhausted or self.unresolved)
        issue_list = [self.issues[number] for number in sorted(self.issues)]
        pr_list = [self.pull_requests[number] for number in sorted(self.pull_requests)]
        remote_times = [
            updated_at for item in issue_list + pr_list if isinstance((updated_at := item.get("updated_at")), str)
        ]
        membership = (
            {
                "candidate_completeness": "verified",
                "children_of": {str(self.root): list(self.candidates)},
                "provenance": {
                    "mechanism": "bounded-epic-graph-v1",
                    "derived_at": max(remote_times) if remote_times else fetched_at,
                },
            }
            if mode == "index" and not incomplete
            else {
                "candidate_completeness": "unverified",
                "children_of": {},
                "provenance": {"mechanism": None, "derived_at": None},
            }
        )
        snapshot: dict[str, Any] = {
            "graph_snapshot_version": TICKET_VERSION,
            "repo": self.repo,
            "root": {"issue_number": self.root, "url": f"https://github.com/{self.repo}/issues/{self.root}"},
            "fetched_at": fetched_at,
            "count": len(issue_list),
            "metadata": {
                "repo": self.repo,
                "mode": mode,
                "content_trust": "untrusted-github-data",
                "comment_policy": self.comment_policy,
            },
            "membership": membership,
            "candidate_tickets": list(self.candidates) if mode == "index" else [self.root],
            "issues": issue_list,
            "pull_requests": pr_list,
            "edges": self._canonical_edges(),
            "unresolved": sorted(
                self.unresolved,
                key=lambda item: (str(item.get("reason")), int(item.get("source") or 0), int(item.get("target") or 0)),
            ),
            "coverage": {
                "complete": not incomplete,
                "state": "complete" if not incomplete else "partial",
            },
            "budgets": {
                "limits": {
                    "nodes": self.limits.max_nodes,
                    "edges": self.limits.max_edges,
                    "depth": self.limits.max_depth,
                    "comments": self.limits.max_comments,
                    "comments_per_issue": self.limits.max_comments_per_issue,
                    "response_bytes": self.limits.max_response_bytes,
                },
                "usage": {
                    "nodes": len(issue_list) + len(pr_list),
                    "edges": len(self.edges),
                    "comments": self.comments_used,
                    "response_bytes": self.client.response_bytes,
                },
                "exhausted": sorted(
                    self.exhausted,
                    key=lambda item: (item["kind"], int(item.get("source") or 0), int(item.get("target") or 0)),
                ),
            },
        }
        snapshot["graph_receipt"] = graph_receipt(snapshot)
        snapshot["digest"] = snapshot_digest(snapshot)
        return snapshot


def write_json_atomic(output_path: Path, data: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f".{output_path.name}.tmp")
    try:
        temp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temp_path.replace(output_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def verify_snapshot(client: GitHubClient, snapshot: dict[str, Any]) -> dict[str, Any]:
    if not compatible_version(snapshot.get("graph_snapshot_version"), TICKET_VERSION):
        raise ConfigError("legacy flat/index snapshot; refetch with ticket and --epic-issue-number")
    if snapshot.get("graph_receipt") != graph_receipt(snapshot):
        raise ConfigError("graph receipt is invalid; refetch before verification")
    if snapshot.get("digest") != snapshot_digest(snapshot):
        raise ConfigError("snapshot digest is invalid; refetch before verification")
    repo = normalize_github_repo_target(snapshot.get("repo"))
    stale: list[dict[str, Any]] = []
    for issue in snapshot.get("issues") or []:
        number = issue.get("number")
        try:
            current = client.request("GET", f"/repos/{repo}/issues/{number}")
        except GitHubError as exc:
            if exc.status == 404:
                stale.append({"kind": "issue", "number": number, "reason": "missing"})
                continue
            raise
        if not isinstance(current, dict) or "pull_request" in current:
            raise GitHubError(f"GitHub API returned unexpected issue payload for #{number}")
        for field in ("updated_at", "state", "state_reason"):
            if current.get(field) != issue.get(field):
                stale.append({"kind": "issue", "number": number, "reason": "changed", "field": field})
        stored_comments = issue.get("comments") or []
        if stored_comments:
            current_comments = {
                item.get("id"): item for item in client.paginated_get(f"/repos/{repo}/issues/{number}/comments")
            }
            for comment in stored_comments:
                current_comment = current_comments.get(comment.get("id"))
                if current_comment is None:
                    stale.append({"kind": "comment", "number": comment.get("id"), "reason": "missing"})
                elif current_comment.get("updated_at") != comment.get("updated_at"):
                    stale.append(
                        {"kind": "comment", "number": comment.get("id"), "reason": "changed", "field": "updated_at"}
                    )
    for pr in snapshot.get("pull_requests") or []:
        number = pr.get("number")
        try:
            raw_current = client.request("GET", f"/repos/{repo}/pulls/{number}")
        except GitHubError as exc:
            if exc.status == 404:
                stale.append({"kind": "pull_request", "number": number, "reason": "missing"})
                continue
            raise
        if not isinstance(raw_current, dict):
            raise GitHubError(f"GitHub API returned unexpected pull request payload for #{number}")
        current = normalize_pr(raw_current)
        for field in ("updated_at", "state", "draft", "merged_at", "merge_commit_sha", "head", "base"):
            if current.get(field) != pr.get(field):
                stale.append({"kind": "pull_request", "number": number, "reason": "changed", "field": field})
    stale.sort(key=lambda item: (item["kind"], int(item.get("number") or 0), str(item.get("field", ""))))
    return {"fresh": not stale, "stale": stale, "graph_receipt": snapshot["graph_receipt"]}


def _eligibility_deps(payload: dict[str, Any]) -> dict[Any, set[Any]]:
    deps: dict[Any, set[Any]] = {}
    for item in payload.get("edges") or []:
        if not isinstance(item, dict):
            continue
        source, target, relation = item.get("source"), item.get("target"), item.get("type")
        if (
            item.get("target_kind", "issue") != "issue"
            or not isinstance(source, (int, str))
            or not isinstance(target, (int, str))
        ):
            continue
        if relation in {"depends_on", "blocked_by"}:
            deps.setdefault(source, set()).add(target)
        elif relation == "blocks":
            deps.setdefault(target, set()).add(source)
    return deps


def _closure(starts: set[int], deps: dict[int, set[int]]) -> set[int]:
    seen: set[int] = set()
    pending = list(starts)
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        pending.extend(deps.get(current, set()) - seen)
    return seen


def _readset_numbers(
    snapshot: dict[str, Any], scope_inputs: dict[str, Any], selected: int | str | None
) -> set[Any]:
    mode = (snapshot.get("metadata") or {}).get("mode")
    root = (snapshot.get("root") or {}).get("issue_number")
    candidates = [c for c in (snapshot.get("candidate_tickets") or []) if isinstance(c, (int, str))]
    deps = _eligibility_deps(snapshot)
    readset: set[Any] = set()
    if mode == "single":
        if isinstance(root, (int, str)):
            readset |= _closure({root}, deps)
    else:
        override = scope_inputs.get("override") if isinstance(scope_inputs, dict) else None
        over_issue = override.get("issue") if isinstance(override, dict) else None
        if isinstance(over_issue, (int, str)):
            if isinstance(root, (int, str)):
                readset.add(root)
            # A terminal rejection with no subject does not claim the rejected
            # issue is part of the fetched graph. Verify only the root and its
            # recorded membership evidence; actionable overrides still read
            # the selected issue and prerequisite closure below.
            if isinstance(selected, (int, str)) or over_issue in issues_by_numbers(snapshot):
                readset |= _closure({over_issue}, deps)
        else:
            if isinstance(root, (int, str)):
                readset.add(root)
            for cand in candidates:
                readset |= _closure({cand}, deps)
    if isinstance(selected, (int, str)):
        readset |= _closure({selected}, deps)
    return {n for n in readset if (isinstance(n, int) and n > 0) or (isinstance(n, str) and n != "")}


def issues_by_numbers(snapshot: dict[str, Any]) -> set[Any]:
    return {
        item.get("number")
        for item in (snapshot.get("issues") or [])
        if isinstance(item, dict) and isinstance(item.get("number"), (int, str))
    }


def _live_relations(
    text: str, *, repo: str, issue_number: int, updated_at: str | None, kind: str, comment_id: int | None = None
) -> list[dict[str, Any]]:
    return parse_relations(
        text or "",
        repo=repo,
        issue_number=issue_number,
        source_updated_at=updated_at,
        source_kind=kind,
        comment_id=comment_id,
        task_lists_are_children=False,
    )


def verify_readset(
    client: Any, snapshot: dict[str, Any], scope_inputs: dict[str, Any] | None, selected_issue_number: int | None = None
) -> dict[str, Any]:
    """Revalidate the decision-scoped read-set without opening local source files."""
    if not compatible_version(snapshot.get("graph_snapshot_version"), TICKET_VERSION):
        raise ConfigError("legacy flat/index snapshot; refetch with ticket")
    if snapshot.get("graph_receipt") != graph_receipt(snapshot):
        raise ConfigError("graph receipt is invalid; refetch before verification")
    if snapshot.get("digest") != snapshot_digest(snapshot):
        raise ConfigError("snapshot digest is invalid; refetch before verification")
    repo = normalize_github_repo_target(snapshot.get("repo"))
    inputs = scope_inputs or {}
    if inputs and inputs.get("backend") != "github":
        raise ConfigError("GitHub verification requires backend=github in scope_inputs")
    snap_mode = (snapshot.get("metadata") or {}).get("mode")
    if inputs and inputs.get("mode") != snap_mode:
        raise ConfigError("scope_inputs.mode does not match the snapshot mode")
    root = (snapshot.get("root") or {}).get("issue_number")
    if inputs:
        expected_root = ((inputs.get("ticket") or {}) if snap_mode == "single" else (inputs.get("epic") or {})).get(
            "number"
        )
        if expected_root != root:
            raise ConfigError("snapshot root does not match the requested ticket/epic")
        override = inputs.get("override") if isinstance(inputs, dict) else None
        over_issue = override.get("issue") if isinstance(override, dict) else None
        if snap_mode == "single" and isinstance(selected_issue_number, int) and selected_issue_number != root:
            return {
                "fresh": False,
                "stale": [{"kind": "selection", "number": selected_issue_number, "reason": "mismatch"}],
                "graph_receipt": snapshot["graph_receipt"],
                "next_action": None,
                "checked": sorted(_readset_numbers(snapshot, inputs, selected_issue_number)),
            }
        if (
            isinstance(over_issue, int)
            and isinstance(selected_issue_number, int)
            and selected_issue_number != over_issue
        ):
            return {
                "fresh": False,
                "stale": [{"kind": "selection", "number": selected_issue_number, "reason": "mismatch"}],
                "graph_receipt": snapshot["graph_receipt"],
                "next_action": None,
                "checked": sorted(_readset_numbers(snapshot, inputs, selected_issue_number)),
            }
    stale: list[dict[str, Any]] = []
    readset = _readset_numbers(snapshot, inputs, selected_issue_number)
    issues_by = {i.get("number"): i for i in (snapshot.get("issues") or []) if isinstance(i, dict)}
    # Live issue state + body for the read-set only.
    live_bodies: dict[int, str] = {}
    live_comments: dict[int, list[dict[str, Any]]] = {}
    for number in sorted(readset):
        stored = issues_by.get(number)
        try:
            current = client.request("GET", f"/repos/{repo}/issues/{number}")
        except GitHubError as exc:
            if exc.status == 404:
                recorded_missing = any(
                    isinstance(item, dict)
                    and item.get("reason") == "not_found"
                    and item.get("target_kind", "issue") == "issue"
                    and item.get("target") == number
                    for item in (snapshot.get("unresolved") or [])
                )
                protected = {root} if isinstance(root, int) else set()
                if isinstance(selected_issue_number, int):
                    protected |= _closure({selected_issue_number}, _eligibility_deps(snapshot))
                if not (recorded_missing and number not in protected):
                    stale.append({"kind": "issue", "number": number, "reason": "missing"})
                continue
            raise
        if not isinstance(current, dict) or "pull_request" in current:
            raise GitHubError(f"GitHub API returned unexpected issue payload for #{number}")
        if stored is None:
            stale.append({"kind": "issue", "number": number, "reason": "new"})
            live_bodies[number] = str(current.get("body") or "")
            live_comments[number] = client.paginated_get(f"/repos/{repo}/issues/{number}/comments")
            continue
        for field in ("updated_at", "state", "state_reason", "body"):
            if current.get(field) != stored.get(field):
                stale.append({"kind": "issue", "number": number, "reason": "changed", "field": field})
                break
        live_bodies[number] = str(current.get("body") or "")
        # Comment content is part of the decision read-set. An unavailable
        # endpoint must fail closed instead of becoming an empty comment list.
        live_comments[number] = client.paginated_get(f"/repos/{repo}/issues/{number}/comments")
        stored_comments = {c.get("id"): c for c in (stored.get("comments") or []) if isinstance(c, dict)}
        live_by_id = {c.get("id"): c for c in live_comments[number] if isinstance(c, dict)}
        for cid, comment in stored_comments.items():
            live_comment = live_by_id.get(cid)
            if live_comment is None:
                stale.append({"kind": "comment", "number": cid, "reason": "missing"})
            elif live_comment.get("updated_at") != comment.get("updated_at") or live_comment.get("body") != comment.get(
                "body"
            ):
                stale.append({"kind": "comment", "number": cid, "reason": "changed", "field": "body"})
        for cid, comment in live_by_id.items():
            if cid not in stored_comments:
                relations = _live_relations(
                    str(comment.get("body") or ""),
                    repo=repo,
                    issue_number=number,
                    updated_at=comment.get("updated_at"),
                    kind="issue-comment",
                    comment_id=cid,
                )
                if relations:
                    stale.append({"kind": "comment", "number": cid, "reason": "new"})
    # Compare the native subset separately because the candidate frontier can
    # also come from task-list/body relations.
    membership = snapshot.get("membership") if isinstance(snapshot.get("membership"), dict) else {}
    if membership.get("candidate_completeness") == "verified" and isinstance(root, int):
        children_of = membership.get("children_of") if isinstance(membership.get("children_of"), dict) else {}
        expected_children = children_of.get(str(root), children_of.get(root, []))
        if isinstance(expected_children, list):
            native_edges = [
                item
                for item in snapshot.get("edges") or []
                if isinstance(item, dict)
                and item.get("source") == root
                and item.get("type") == "child"
                and item.get("target_kind", "issue") == "issue"
                and any(
                    isinstance(provenance, dict) and provenance.get("evidence") == "github-native-sub-issue"
                    for provenance in (item.get("provenance") or [])
                )
            ]
            expected_native = [item.get("target") for item in native_edges if isinstance(item.get("target"), int)]
            live_children = client.paginated_get(f"/repos/{repo}/issues/{root}/sub_issues")
            live_numbers = sorted(
                c.get("number") for c in live_children if isinstance(c, dict) and isinstance(c.get("number"), int)
            )
            if sorted(expected_native) != live_numbers:
                stale.append({"kind": "membership", "number": root, "reason": "changed", "field": "children"})
    # Relationship edges for the read-set: live re-parse must match authored snapshot edges.
    _INVERSE = {
        "parent": "child",
        "child": "parent",
        "depends_on": "blocks",
        "blocked_by": "blocks",
        "blocks": "blocked_by",
        "supersedes": "superseded_by",
        "superseded_by": "supersedes",
    }

    def _expand(triples: set[tuple[int, str, int]]) -> set[tuple[int, str, int]]:
        expanded = set(triples)
        for source, etype, target in list(triples):
            inverse = _INVERSE.get(etype)
            if inverse:
                expanded.add((target, inverse, source))
        return expanded

    authored: set[tuple[int, str, int]] = set()
    for item in snapshot.get("edges") or []:
        if not isinstance(item, dict) or not item.get("provenance"):
            continue
        if item.get("target_kind", "issue") != "issue":
            continue
        if item.get("source") in readset and item.get("selection_relevant"):
            authored.add((item["source"], item["type"], item["target"]))
    authored = _expand(authored)
    live_edge_set: set[tuple[int, str, int]] = set()
    for number in sorted(readset):
        if number not in live_bodies:
            continue
        stored_issue = issues_by.get(number, {})
        task_lists = number == root
        for rel in parse_relations(
            live_bodies[number],
            repo=repo,
            issue_number=number,
            source_updated_at=stored_issue.get("updated_at"),
            source_kind="issue-body",
            task_lists_are_children=task_lists,
        ):
            if rel.get("target_kind", "issue") == "issue" and rel.get("selection_relevant"):
                live_edge_set.add((number, rel["type"], rel["target"]))
        for comment in live_comments.get(number, []):
            if not isinstance(comment, dict):
                continue
            for rel in parse_relations(
                str(comment.get("body") or ""),
                repo=repo,
                issue_number=number,
                source_updated_at=comment.get("updated_at"),
                source_kind="issue-comment",
                comment_id=comment.get("id"),
                task_lists_are_children=task_lists,
            ):
                if rel.get("target_kind", "issue") == "issue" and rel.get("selection_relevant"):
                    live_edge_set.add((number, rel["type"], rel["target"]))
        native_kids = client.paginated_get(f"/repos/{repo}/issues/{number}/sub_issues")
        if isinstance(native_kids, list):
            for kid in native_kids:
                if isinstance(kid, dict) and isinstance(kid.get("number"), int):
                    live_edge_set.add((number, "child", kid["number"]))
    live_edge_set = _expand(live_edge_set)
    # Compare only edges whose source was parsed live; missing sources stay stale-neutral here.
    for triple in sorted(live_edge_set - authored):
        stale.append({"kind": "relation", "number": triple[0], "reason": "new", "field": f"{triple[1]}:{triple[2]}"})
    for triple in sorted(authored - live_edge_set):
        if triple[0] in live_bodies:
            stale.append(
                {"kind": "relation", "number": triple[0], "reason": "deleted", "field": f"{triple[1]}:{triple[2]}"}
            )
    # Linked pull requests for the read-set.
    snapshot_prs = {
        (e.get("source"), e.get("target"))
        for e in (snapshot.get("edges") or [])
        if isinstance(e, dict) and e.get("type") == "linked_pr" and e.get("source") in readset
    }
    live_prs: set[tuple[int, int]] = set()
    pr_targets = [n for n in sorted(readset) if n in issues_by]
    for number in pr_targets:
        events = client.paginated_get(f"/repos/{repo}/issues/{number}/timeline")
        for event in events:
            if not isinstance(event, dict) or event.get("event") != "cross-referenced":
                continue
            source_issue = (event.get("source") or {}).get("issue") or {}
            if "pull_request" not in source_issue:
                continue
            pr_number = source_issue.get("number")
            repo_url = source_issue.get("repository_url") or ""
            if isinstance(pr_number, int) and repo_url.casefold().endswith(f"/{repo.casefold()}"):
                live_prs.add((number, pr_number))
    for pair in sorted(live_prs - snapshot_prs):
        stale.append({"kind": "pull_request", "number": pair[1], "reason": "new"})
    for pair in sorted(snapshot_prs - live_prs):
        stale.append({"kind": "pull_request", "number": pair[1], "reason": "deleted"})
    for _, pr_number in sorted(snapshot_prs & live_prs):
        stored_pr = next(
            (p for p in (snapshot.get("pull_requests") or []) if isinstance(p, dict) and p.get("number") == pr_number),
            None,
        )
        if stored_pr is None:
            continue
        try:
            raw = client.request("GET", f"/repos/{repo}/pulls/{pr_number}")
        except GitHubError as exc:
            if exc.status == 404:
                stale.append({"kind": "pull_request", "number": pr_number, "reason": "missing"})
                continue
            raise
        current = normalize_pr(raw) if isinstance(raw, dict) else {}
        for field in ("updated_at", "state", "draft", "merged_at", "merge_commit_sha", "head", "base"):
            if current.get(field) != stored_pr.get(field):
                stale.append({"kind": "pull_request", "number": pr_number, "reason": "changed", "field": field})
                break
    stale.sort(key=lambda item: (str(item.get("kind")), int(item.get("number") or 0), str(item.get("field", ""))))
    fresh = not stale
    next_action = None
    if fresh:
        next_action = "narrow_selected" if isinstance(selected_issue_number, int) else "proceed"
    return {
        "fresh": fresh,
        "stale": stale,
        "graph_receipt": snapshot["graph_receipt"],
        "next_action": next_action,
        "checked": sorted(readset),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch or verify one bounded GitHub epic graph.")
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch", help="Fetch a canonical graph snapshot.")
    fetch.add_argument("--github-repo", required=True, help="GitHub repository URL or owner/repo.")
    fetch.add_argument("--epic-issue-number", required=False, type=int, default=None)
    fetch.add_argument("--issue-number", required=False, type=int, default=None)
    fetch.add_argument("--mode", choices=("epic", "single"), default="epic")
    fetch.add_argument("--repo-root", required=True, help="Local target repository root used for output safety.")
    fetch.add_argument("--output", required=True)
    fetch.add_argument("--comment-policy", choices=("auto", "none", "all"), default="auto")
    fetch.add_argument("--max-nodes", type=int, default=DEFAULT_MAX_NODES)
    fetch.add_argument("--max-edges", type=int, default=DEFAULT_MAX_EDGES)
    fetch.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH)
    fetch.add_argument("--max-comments", type=int, default=DEFAULT_MAX_COMMENTS)
    fetch.add_argument("--max-comments-per-issue", type=int, default=DEFAULT_MAX_COMMENTS_PER_ISSUE)
    fetch.add_argument("--max-response-bytes", type=int, default=DEFAULT_MAX_RESPONSE_BYTES)
    verify = commands.add_parser("verify", help="Verify remote identities without rewriting the snapshot.")
    verify.add_argument("--snapshot", required=True)
    verify.add_argument("--scope-inputs", required=False, default=None)
    verify.add_argument("--selected-issue-number", required=False, type=int, default=None)
    verify.add_argument("--max-response-bytes", type=int, default=DEFAULT_MAX_RESPONSE_BYTES)
    return parser


def _limits(args: argparse.Namespace) -> Limits:
    return Limits(
        positive_int(args.max_nodes, "--max-nodes"),
        positive_int(args.max_edges, "--max-edges"),
        positive_int(args.max_depth, "--max-depth"),
        positive_int(args.max_comments, "--max-comments"),
        positive_int(args.max_comments_per_issue, "--max-comments-per-issue"),
        positive_int(args.max_response_bytes, "--max-response-bytes"),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        max_response_bytes = positive_int(args.max_response_bytes, "--max-response-bytes")
        if args.command == "verify":
            snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
            if not compatible_version(snapshot.get("graph_snapshot_version"), TICKET_VERSION):
                raise ConfigError("verify requires graph snapshot v1; refetch from an epic")
            if snapshot.get("graph_receipt") != graph_receipt(snapshot):
                raise ConfigError("graph receipt mismatch; refetch the snapshot")
            if snapshot.get("digest") != snapshot_digest(snapshot):
                raise ConfigError("snapshot digest mismatch; refetch the snapshot")
            client = GitHubClient(max_response_bytes=max_response_bytes)
            client.preflight()
            if args.scope_inputs:
                scope_inputs = json.loads(Path(args.scope_inputs).read_text(encoding="utf-8"))
                result = verify_readset(client, snapshot, scope_inputs, args.selected_issue_number)
            else:
                result = verify_snapshot(client, snapshot)
            print(json.dumps(result, sort_keys=True))
            return 0 if result["fresh"] else 3

        repo = normalize_github_repo_target(args.github_repo)
        has_epic = args.epic_issue_number is not None
        has_issue = args.issue_number is not None
        if has_epic == has_issue:
            raise ConfigError("pass exactly one of --epic-issue-number or --issue-number")
        if args.mode == "single" and not has_issue:
            raise ConfigError("single mode requires --issue-number")
        if args.mode == "epic" and not has_epic:
            raise ConfigError("epic mode requires --epic-issue-number")
        root = positive_int(
            args.issue_number if has_issue else args.epic_issue_number,
            "--issue-number" if has_issue else "--epic-issue-number",
        )
        repo_root = Path(args.repo_root).resolve(strict=True)
        output = ensure_external_output(Path(args.output), repo_root=repo_root, skill_root=SKILL_ROOT)
        client = GitHubClient(max_response_bytes=max_response_bytes)
        client.preflight()
        snapshot_mode = "index" if args.mode == "epic" else "single"
        snapshot = GraphBuilder(client, repo, root, _limits(args), args.comment_policy).build(snapshot_mode)
        write_json_atomic(output, snapshot)
        print(f"Fetched {snapshot['count']} GitHub issues rooted at #{root} from {repo}")
        print(f"Coverage: {snapshot['coverage']['state']}; receipt: {snapshot['graph_receipt']}")
        print(f"Wrote {output}")
        return 0
    except (ConfigError, json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except GitHubError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

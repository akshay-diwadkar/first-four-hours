#!/usr/bin/env python3
"""Publish one ready Ticket GitHub reconciliation plan exactly as reviewed, over the gh CLI.

Requires explicit confirmation, replays the reconciliation reads so only a fresh
and unchanged plan is published, then performs each planned write once in
publication order through ``GitHubClient.mutate`` and proves its postcondition
by readback. A rejected, ambiguous, or unverified write stops the attempt
without retry and ``publication-result.json`` records the exact step state.
"""

from __future__ import annotations

import argparse
import copy
import errno
import json
import os
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import IO, Any, Callable, Protocol

from _diagnostic_contract import Diagnostic
from github_common import TICKET_VERSION, GitHubClient, GitHubError, ResponseBudgetExceeded, contract_matches
from reconcile_github import (
    Bound,
    LocalRejection,
    ReadClient,
    _canonical,
    _emit,
    _is_404,
    _is_gone,
    _issue_fact,
    _receipt,
    _ref_label,
    _write_atomic,
    stored_ready,
    verified,
)

CONTRACT = {"skill": "ticket", "branch": "persist", "artifact": "github-publication", "version": TICKET_VERSION}
CREATE_MATCH_LIMIT = 300
CLOCK_MARGIN = timedelta(hours=1)
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
OUTCOME_CODES = {
    "rejected": "persist.publish_rejected",
    "ambiguous": "persist.publish_ambiguous",
    "unverified": "persist.publish_unverified",
}
CODE_RULES: dict[str, tuple[str, str]] = {
    "persist.publish_unconfirmed": (
        "contract_contradiction",
        "Publish only from publication review with publish_confirmation=yes after reading reconciliation.json.",
    ),
    "persist.publish_in_progress": (
        "unsafe_state",
        "Another publish is running for this run: wait for it to finish, then present publication-result.json or "
        "run next again; never run a second publish beside it.",
    ),
    "persist.publish_already_attempted": (
        "unsafe_state",
        "publication-result.json records a completed publication: present its recorded issues; never publish "
        "again from this run.",
    ),
    "persist.publish_output_unwritable": (
        "unavailable_prerequisite",
        "Make the run directory writable, then run next again: an existing publication-result.json resumes and "
        "rereads GitHub before any write; otherwise no GitHub write was attempted.",
    ),
    "persist.publish_rejected": (
        "unsafe_state",
        "GitHub rejected the recorded step and nothing was retried: read publication-result.json if it exists, "
        "where verified steps are done; repair the cause GitHub reported, then run next again, which rereads "
        "GitHub before any write.",
    ),
    "persist.publish_ambiguous": (
        "unsafe_state",
        "The recorded step may or may not have applied and was never retried: present publication-result.json, "
        "then run next again to resume; resume reads current GitHub state and never repeats a write that applied.",
    ),
    "persist.publish_unverified": (
        "unsafe_state",
        "The recorded write returned but its postcondition did not read back: present publication-result.json, "
        "then run next again to resume; resume reads current GitHub state and never repeats a write that applied.",
    ),
    "persist.publication_result_invalid": (
        "unsafe_state",
        "publication-result.json is unreadable, altered, or bound to another reconciliation, so this run cannot "
        "resume: never edit it; find any issues this run created on GitHub and start a new run whose "
        "reconciliation reuses them.",
    ),
    "persist.recovery_read_failed": (
        "unavailable_prerequisite",
        "Current GitHub state could not be read and nothing was written: restore gh access, then run next again "
        "to resume.",
    ),
    "persist.recovery_ambiguous": (
        "unsafe_state",
        "An interrupted create cannot be matched to at most one existing issue and nothing was written: find "
        "the issue on GitHub, then start a new run whose reconciliation reuses it and every issue "
        "publication-result.json names.",
    ),
    "persist.recovery_drift": (
        "unsafe_state",
        "A postcondition this publication established or relied on no longer holds on GitHub and nothing was "
        "written: this run cannot resume; start a new run whose reconciliation reuses every issue "
        "publication-result.json names.",
    ),
    "persist.recovery_conflict": (
        "unsafe_state",
        "A planned issue sits under a different parent and nothing was written; Ticket never re-parents: "
        "resolve the parent on GitHub, then run next again, or start a new run.",
    ),
}


class WriteClient(ReadClient, Protocol):
    def mutate(self, method: str, path: str, payload: dict[str, Any]) -> Any: ...


class Unverified(Exception):
    """A write returned but its expected postcondition did not read back."""


class Halt(Exception):
    """A resume pre-check found GitHub state that makes writing unsafe; nothing was written."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _diag(code: str, message: str, *, path: Path) -> dict[str, Any]:
    category, action = CODE_RULES[code]
    return Diagnostic(
        code=code,
        message=message,
        category=category,
        skill="ticket",
        phase="publish",
        artifact="publication-result.json",
        path=str(path),
        required_action=action,
        valid_repairs=(action,),
        supporting_evidence=(message,),
    ).to_dict()


def _steps(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Publication order: issue writes, then native sub-issue links, then dependency links."""

    steps: list[dict[str, Any]] = []
    for action in plan["actions"]:
        if action["action"] == "create":
            steps.append(
                {"kind": "create", "target": action["target"], "issue": None, "status": "pending", "attempted_at": None}
            )
        elif action["labels_to_apply"]:
            steps.append({"kind": "labels", "target": action["target"], "issue": action["issue"], "status": "pending"})
    for link in plan["sub_issue_links"]:
        steps.append(
            {
                "kind": "sub_issue",
                "child": link["child"],
                "child_issue": link["child_issue"],
                "parent_issue": None,
                "status": "pending",
            }
        )
    for link in plan["dependency_links"]:
        steps.append(
            {
                "kind": "dependency",
                "from": link["from"],
                "to": link["to"],
                "from_issue": link["from_issue"],
                "to_issue": link["to_issue"],
                "status": "pending",
            }
        )
    return steps


def _outcome(exc: GitHubError) -> str:
    """Only a definitive client-error response proves a write did not apply."""

    status = exc.status
    definitive = status is not None and 400 <= status < 500 and status not in (408, 429)
    return "rejected" if definitive and not isinstance(exc, ResponseBudgetExceeded) else "ambiguous"


def _describe(step: dict[str, Any]) -> str:
    if step["kind"] == "create":
        return f"create {_ref_label(step['target'])}"
    if step["kind"] == "labels":
        return f"add labels to #{step['issue']}"
    if step["kind"] == "sub_issue":
        return f"link item {step['child']} under #{step['parent_issue']}"
    return f"mark item {step['from']} blocked by item {step['to']}"


def _hold_lock(path: Path) -> IO[bytes] | None:
    """Take an exclusive non-blocking kernel lock on path, released on close or process exit.

    Returns None only when another holder has it; any other locking failure propagates as OSError.
    """

    handle = open(path, "a+b")
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK, errno.EDEADLK):
            return None
        raise
    return handle


def _release_lock(handle: IO[bytes]) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        handle.close()


def _load_prior(output: Path) -> dict[str, Any] | None:
    """Return the recorded publication result when it parses and its receipt and contract verify."""

    try:
        prior = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(prior, dict)
        or not contract_matches(prior.get("contract"), CONTRACT)
        or prior.get("receipt") != _receipt(prior)
        or prior.get("status") not in ("in-progress", "stopped", "complete")
        or not isinstance(prior.get("steps"), list)
        or not isinstance(prior.get("issues"), dict)
    ):
        return None
    return prior


def publish(args: argparse.Namespace, client_factory: Callable[[], WriteClient]) -> int:
    """Publish or resume under the run's lock, so one publish at a time acts on a run."""

    output = Path(args.output)

    def stop(code: str, message: str) -> int:
        _emit({"valid": False, "diagnostics": [_diag(code, message, path=output)]})
        return 1

    if args.confirmation != "yes":
        return stop("persist.publish_unconfirmed", "publish_confirmation=yes was not supplied")
    lock_path = output.with_name(f"{output.name}.lock")
    try:
        lock = _hold_lock(lock_path)
    except OSError as exc:
        return stop("persist.publish_output_unwritable", f"cannot open {lock_path.name}: {exc}")
    if lock is None:
        return stop("persist.publish_in_progress", f"another publish holds {lock_path.name}")
    try:
        return _publish(args, client_factory, output)
    finally:
        _release_lock(lock)


def _publish(args: argparse.Namespace, client_factory: Callable[[], WriteClient], output: Path) -> int:
    def stop(code: str, message: str) -> int:
        _emit({"valid": False, "diagnostics": [_diag(code, message, path=output)]})
        return 1

    reconcile_args = argparse.Namespace(
        command="publish",
        backend=args.backend,
        github_repo=args.github_repo,
        label=args.label,
        persist_input=args.persist_input,
        preview=args.preview,
        reconciliation_input=args.reconciliation_input,
        reconciliation=args.reconciliation,
    )
    prior: dict[str, Any] | None = None
    try:
        os.close(os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        try:
            empty = output.stat().st_size == 0
        except OSError as exc:
            return stop("persist.publish_output_unwritable", f"cannot read {output.name}: {exc}")
        if not empty:
            # An empty file is a claim that recorded nothing, so no write happened: proceed fresh.
            prior = _load_prior(output)
            if prior is None:
                return stop(
                    "persist.publication_result_invalid",
                    f"{output.name} cannot be read or its receipt or contract does not verify",
                )
            if prior["status"] == "complete":
                return stop("persist.publish_already_attempted", f"{output.name} records a completed publication")
    except OSError as exc:
        return stop("persist.publish_output_unwritable", f"cannot create {output.name}: {exc}")

    bound: Bound | None = None
    if prior is None:
        try:
            client = client_factory()
            stored = verified(reconcile_args, lambda: client)
        except LocalRejection as exc:
            output.unlink(missing_ok=True)
            _emit({"valid": False, "diagnostics": exc.diagnostics})
            return 1
        except BaseException:
            output.unlink(missing_ok=True)
            raise
    else:
        try:
            bound, stored = stored_ready(reconcile_args)
        except LocalRejection as exc:
            _emit({"valid": False, "diagnostics": exc.diagnostics})
            return 1
        if prior["binding"] != {**stored["binding"], "reconciliation_receipt": stored["receipt"]}:
            return stop(
                "persist.publication_result_invalid",
                f"{output.name} is bound to a different reconciliation than reconciliation.json",
            )
        client = client_factory()

    repo = stored["binding"]["repository"]
    labels: list[str] = stored["binding"]["labels"]
    plan = stored["plan"]
    content = {_ref_label(action["target"]): action for action in plan["actions"]}
    ids: dict[int, int] = {fact["number"]: fact["id"] for fact in stored["issues"].values()}
    numbers: dict[str, int | None]
    if prior is None:
        numbers = {_ref_label(action["target"]): action["issue"] for action in plan["actions"]}
        steps = _steps(plan)
        result: dict[str, Any] = {
            "contract": CONTRACT,
            "status": "in-progress",
            "binding": {**stored["binding"], "reconciliation_receipt": stored["receipt"]},
            "issues": numbers,
            "steps": steps,
        }
    else:
        result = prior
        numbers = result["issues"]
        steps = result["steps"]

    def record(status: str) -> None:
        result["status"] = status
        result.pop("receipt", None)
        result["receipt"] = _receipt(result)
        _write_atomic(output, _canonical(result).decode("ascii") + "\n")

    def item(item_id: str) -> int:
        number = numbers[_ref_label({"kind": "item", "id": item_id})]
        assert number is not None
        return number

    def issue_path(number: int) -> str:
        return f"/repos/{repo}/issues/{number}"

    def read_issue(number: int, labels: list[str]) -> dict[str, Any]:
        path = issue_path(number)
        raw = client.request("GET", path)
        fact = _issue_fact(raw, path, labels_of_interest={name.casefold() for name in labels})
        if fact["number"] != number or fact["repository"] != repo or fact["pull_request"]:
            raise Unverified(f"#{number} does not read back as an issue in {repo}")
        present = {name.casefold() for name in fact["labels"]}
        missing = [name for name in labels if name.casefold() not in present]
        if missing:
            raise Unverified(f"#{number} is missing labels {', '.join(missing)}")
        return raw

    def execute(step: dict[str, Any]) -> None:
        kind = step["kind"]
        if kind == "create":
            action = content[_ref_label(step["target"])]
            response = client.mutate(
                "POST",
                f"/repos/{repo}/issues",
                {"title": action["title"], "body": action["body"], "labels": action["labels_to_apply"]},
            )
            if not isinstance(response, dict) or not isinstance(response.get("number"), int) or not isinstance(
                response.get("id"), int
            ):
                raise GitHubError("GitHub returned no issue identity for the created issue")
            step["issue"] = response["number"]
            numbers[_ref_label(step["target"])] = response["number"]
            ids[response["number"]] = response["id"]
        elif kind == "labels":
            labels = content[_ref_label(step["target"])]["labels_to_apply"]
            client.mutate("POST", f"{issue_path(step['issue'])}/labels", {"labels": labels})
        elif kind == "sub_issue":
            step["parent_issue"] = numbers["epic"]
            step["child_issue"] = item(step["child"])
            client.mutate(
                "POST",
                f"{issue_path(step['parent_issue'])}/sub_issues",
                {"sub_issue_id": ids[step["child_issue"]]},
            )
        else:
            step["from_issue"] = item(step["from"])
            step["to_issue"] = item(step["to"])
            client.mutate(
                "POST",
                f"{issue_path(step['from_issue'])}/dependencies/blocked_by",
                {"issue_id": ids[step["to_issue"]]},
            )

    def read_back(step: dict[str, Any]) -> None:
        kind = step["kind"]
        if kind == "create":
            action = content[_ref_label(step["target"])]
            raw = read_issue(step["issue"], action["labels_to_apply"])
            body = (raw.get("body") or "").replace("\r\n", "\n").strip()
            if raw.get("state") != "open" or raw.get("title") != action["title"] or body != action["body"].strip():
                raise Unverified(f"#{step['issue']} does not read back with the previewed state, title, and body")
        elif kind == "labels":
            read_issue(step["issue"], content[_ref_label(step["target"])]["labels_to_apply"])
        elif kind == "sub_issue":
            path = f"{issue_path(step['child_issue'])}/parent"
            parent = _issue_fact(client.request("GET", path), path, labels_of_interest=None)
            if parent["repository"] != repo or parent["number"] != step["parent_issue"]:
                raise Unverified(f"#{step['child_issue']} does not read back under #{step['parent_issue']}")
        else:
            path = f"{issue_path(step['from_issue'])}/dependencies/blocked_by"
            blockers = [_issue_fact(entry, path, labels_of_interest=None) for entry in client.paginated_get(path)]
            if not any(fact["repository"] == repo and fact["number"] == step["to_issue"] for fact in blockers):
                raise Unverified(f"#{step['from_issue']} does not read back as blocked by #{step['to_issue']}")

    def issue_state(number: int) -> str:
        """'ok': an open issue in repo with every bound label; 'unlabeled': only labels missing; else 'gone'."""

        path = issue_path(number)
        try:
            raw = client.request("GET", path)
        except GitHubError as exc:
            if _is_gone(exc):
                return "gone"
            raise
        fact = _issue_fact(raw, path, labels_of_interest={name.casefold() for name in labels})
        if fact["number"] != number or fact["repository"] != repo or fact["pull_request"] or fact["state"] != "open":
            return "gone"
        ids[number] = fact["id"]
        present = {name.casefold() for name in fact["labels"]}
        return "ok" if all(name.casefold() in present for name in labels) else "unlabeled"

    def parent_of(number: int) -> dict[str, Any] | None:
        path = f"{issue_path(number)}/parent"
        try:
            raw = client.request("GET", path)
        except GitHubError as exc:
            if _is_404(exc):
                return None
            raise
        fact = _issue_fact(raw, path, labels_of_interest=None)
        return {"repository": fact["repository"], "number": fact["number"]}

    def blockers(number: int) -> set[int]:
        path = f"{issue_path(number)}/dependencies/blocked_by"
        facts = [_issue_fact(entry, path, labels_of_interest=None) for entry in client.paginated_get(path)]
        return {fact["number"] for fact in facts if fact["repository"] == repo}

    def find_created(step: dict[str, Any]) -> int | None:
        label = _ref_label(step["target"])
        action = content[label]
        if not step.get("attempted_at"):
            raise Halt("persist.recovery_ambiguous", f"{label} create has no recorded attempt time")
        since = (
            datetime.strptime(step["attempted_at"], TIME_FORMAT).replace(tzinfo=timezone.utc) - CLOCK_MARGIN
        ).strftime(TIME_FORMAT)
        path = f"/repos/{repo}/issues?" + urllib.parse.urlencode(
            {"state": "all", "sort": "created", "direction": "desc", "since": since}
        )
        listed = client.paginated_get(path, item_limit=CREATE_MATCH_LIMIT)
        if len(listed) >= CREATE_MATCH_LIMIT:
            # paginated_get truncates silently, so a full listing may be partial.
            raise Halt(
                "persist.recovery_ambiguous",
                f"{CREATE_MATCH_LIMIT} or more issues changed since the interrupted {label} create",
            )
        # Issues reconciliation already saw are never this create.
        known = {number for number in numbers.values() if number is not None} | {
            fact["number"] for fact in stored["issues"].values()
        }
        matches: list[int] = []
        for raw in listed:
            fact = _issue_fact(raw, path, labels_of_interest=None)
            body = (raw.get("body") or "").replace("\r\n", "\n").strip()
            if (
                fact["repository"] == repo
                and not fact["pull_request"]
                and fact["number"] not in known
                and raw.get("title") == action["title"]
                and body == action["body"].strip()
            ):
                matches.append(fact["number"])
        if len(matches) > 1:
            raise Halt(
                "persist.recovery_ambiguous",
                f"{label} create matches issues {', '.join(f'#{number}' for number in sorted(matches))}",
            )
        return matches[0] if matches else None

    def reset(step: dict[str, Any]) -> None:
        step["status"] = "pending"
        step.pop("detail", None)
        if step["kind"] == "create":
            step["attempted_at"] = None

    adopted: dict[str, int] = {}

    def classify(step: dict[str, Any]) -> None:
        """Mark a step verified when its postcondition holds now, pending when nothing applied; else Halt."""

        kind, status = step["kind"], step["status"]
        carrying = f"an open issue in {repo} carrying {', '.join(labels) or 'its labels'}"
        if kind == "create":
            label = _ref_label(step["target"])
            if step["issue"] is None and status in ("attempting", "ambiguous"):
                match = find_created(step)
                if match is not None:
                    step["issue"] = match
                    numbers[label] = match
                    adopted[label] = match
            if step["issue"] is None:
                reset(step)
                return
            if issue_state(step["issue"]) != "ok":
                raise Halt(
                    "persist.recovery_drift", f"{label} was created as #{step['issue']} but is no longer {carrying}"
                )
            if status != "verified":
                # Never confirmed: require the previewed state, title, and body.
                try:
                    read_back(step)
                except Unverified as exc:
                    raise Halt("persist.recovery_drift", str(exc)) from exc
            step["status"] = "verified"
            return
        if kind == "labels":
            state = issue_state(step["issue"])
            if state == "ok":
                step["status"] = "verified"
                return
            if state == "gone" or status == "verified":
                raise Halt("persist.recovery_drift", f"#{step['issue']} is no longer {carrying}")
            reset(step)
            return
        if kind == "sub_issue":
            parent = numbers["epic"]
            child = numbers[_ref_label({"kind": "item", "id": step["child"]})]
            if parent is None or child is None:
                reset(step)
                return
            ref = parent_of(child)
            if ref == {"repository": repo, "number": parent}:
                step["parent_issue"], step["child_issue"] = parent, child
                step["status"] = "verified"
                return
            if ref is not None:
                raise Halt(
                    "persist.recovery_conflict",
                    f"#{child} is a sub-issue of {ref['repository']}#{ref['number']}, not #{parent}",
                )
            if status == "verified":
                raise Halt("persist.recovery_drift", f"#{child} is no longer a sub-issue of #{parent}")
            reset(step)
            return
        first = numbers[_ref_label({"kind": "item", "id": step["from"]})]
        second = numbers[_ref_label({"kind": "item", "id": step["to"]})]
        if first is None or second is None:
            reset(step)
            return
        if second in blockers(first):
            step["from_issue"], step["to_issue"] = first, second
            step["status"] = "verified"
            return
        if status == "verified":
            raise Halt("persist.recovery_drift", f"#{first} is no longer blocked by #{second}")
        reset(step)

    def check_assumed() -> None:
        """Reread postconditions reconciliation found already present, which no step owns."""

        assert bound is not None
        linked = {link["child"] for link in plan["sub_issue_links"]}
        missing = {(link["from"], link["to"]) for link in plan["dependency_links"]}
        for action in plan["actions"]:
            if action["action"] != "reuse":
                continue
            if not action["labels_to_apply"] and issue_state(action["issue"]) != "ok":
                raise Halt(
                    "persist.recovery_drift",
                    f"reused #{action['issue']} is no longer an open issue in {repo} "
                    f"carrying {', '.join(labels) or 'its labels'}",
                )
            target = action["target"]
            if stored["shape"] == "epic" and target["kind"] == "item" and target["id"] not in linked:
                ref = parent_of(action["issue"])
                if ref is None:
                    raise Halt(
                        "persist.recovery_drift",
                        f"reused #{action['issue']} is no longer a sub-issue of #{numbers['epic']}",
                    )
                if ref != {"repository": repo, "number": numbers["epic"]}:
                    raise Halt(
                        "persist.recovery_conflict",
                        f"#{action['issue']} is a sub-issue of {ref['repository']}#{ref['number']}, "
                        f"not #{numbers['epic']}",
                    )
        for source, destination in bound.edges:
            if (source, destination) not in missing:
                first, second = item(source), item(destination)
                if second not in blockers(first):
                    raise Halt("persist.recovery_drift", f"#{first} is no longer blocked by #{second}")

    def check_searches() -> None:
        """Replay each reviewed duplicate search whose target's create is still to be performed."""

        pending = {
            _ref_label(step["target"]) for step in steps if step["kind"] == "create" and step["status"] == "pending"
        }
        known = {number for number in numbers.values() if number is not None}
        for search in stored["searches"]:
            label = _ref_label(search["target"])
            if label not in pending:
                continue
            path = "/search/issues?" + urllib.parse.urlencode({"q": search["query"], "per_page": str(search["limit"])})
            raw = client.request("GET", path)
            if (
                not isinstance(raw, dict)
                or not isinstance(raw.get("items"), list)
                or not isinstance(raw.get("total_count"), int)
            ):
                raise GitHubError(f"GitHub API returned unexpected data for {path}")
            facts = [_issue_fact(entry, path, labels_of_interest=None) for entry in raw["items"]]
            new = sorted(
                {fact["number"] for fact in facts if fact["repository"] == repo} - set(search["results"]) - known
            )
            if new or raw.get("incomplete_results") or raw["total_count"] > len(raw["items"]):
                found = ", ".join(f"#{number}" for number in new) or "more results than it lists"
                raise Halt(
                    "persist.recovery_drift",
                    f"the {label} duplicate search now returns {found}, which reconciliation never classified",
                )

    def check_children() -> None:
        """Under a reused epic root, a child reconciliation never classified blocks an item create still pending."""

        hierarchy = stored["hierarchy"]
        if hierarchy is None or hierarchy["root_children"] is None:
            return
        if not any(
            step["kind"] == "create" and step["status"] == "pending" and step["target"]["kind"] == "item"
            for step in steps
        ):
            return
        root = numbers["epic"]
        assert root is not None
        path = f"{issue_path(root)}/sub_issues"
        children = {
            fact["number"]
            for fact in (_issue_fact(entry, path, labels_of_interest=None) for entry in client.paginated_get(path))
            if fact["repository"] == repo
        }
        reviewed = {ref["number"] for ref in hierarchy["root_children"] if ref["repository"] == repo}
        known = {number for number in numbers.values() if number is not None}
        new = sorted(children - reviewed - known)
        if new:
            raise Halt(
                "persist.recovery_drift",
                f"epic root #{root} now has child {', '.join(f'#{number}' for number in new)}, "
                "which reconciliation never classified",
            )

    def remember_matches(snapshot: dict[str, Any], message: str) -> str:
        """On a pre-check stop, record only the issues this pass matched to interrupted creates."""

        if not adopted:
            return message
        for entry in snapshot["steps"]:
            if entry["kind"] == "create" and _ref_label(entry["target"]) in adopted:
                entry["issue"] = adopted[_ref_label(entry["target"])]
        snapshot["issues"].update(adopted)
        snapshot["status"] = "stopped"
        snapshot.pop("receipt", None)
        snapshot["receipt"] = _receipt(snapshot)
        try:
            _write_atomic(output, _canonical(snapshot).decode("ascii") + "\n")
        except OSError as error:
            return f"{message}; {output.name} could not record the matched issues: {error}"
        matched = ", ".join(f"#{number}" for number in adopted.values())
        return f"{message}; {output.name} now names matched issue {matched}"

    if prior is not None:
        snapshot = copy.deepcopy(result)
        try:
            client.preflight()
            for step in steps:
                classify(step)
            check_assumed()
            check_children()
            check_searches()
        except Halt as exc:
            return stop(exc.code, remember_matches(snapshot, str(exc)))
        except GitHubError as exc:
            return stop("persist.recovery_read_failed", remember_matches(snapshot, str(exc)))

    try:
        record("in-progress")
    except BaseException as exc:
        if prior is None:
            output.unlink(missing_ok=True)
        if isinstance(exc, OSError):
            return stop("persist.publish_output_unwritable", f"cannot write {output.name}: {exc}")
        raise

    for index, step in enumerate(steps):
        if step["status"] == "verified":
            continue
        step["status"] = "attempting"
        if step["kind"] == "create":
            step["attempted_at"] = datetime.now(timezone.utc).strftime(TIME_FORMAT)
        try:
            record("in-progress")
        except OSError as exc:
            done = sum(entry["status"] == "verified" for entry in steps)
            return stop(
                "persist.publish_output_unwritable",
                f"cannot record step {index + 1} of {len(steps)} before writing it: {exc}; "
                f"{done} step(s) verified and none attempted since",
            )
        outcome: str | None = None
        try:
            execute(step)
        except GitHubError as exc:
            outcome, detail = _outcome(exc), str(exc)
        else:
            try:
                read_back(step)
            except (GitHubError, Unverified) as exc:
                outcome, detail = "unverified", str(exc)
        if outcome is None:
            step["status"] = "verified"
            continue
        step["status"] = outcome
        step["detail"] = detail
        done = sum(entry["status"] == "verified" for entry in steps)
        untouched = sum(entry["status"] == "pending" for entry in steps)
        message = (
            f"step {index + 1} of {len(steps)} ({_describe(step)}) is {outcome}: {detail}; "
            f"{done} step(s) verified and {untouched} not attempted"
        )
        if outcome == "rejected" and done == 0:
            try:
                output.unlink()
            except OSError:
                pass
            else:
                return stop(OUTCOME_CODES[outcome], f"{message}; no write applied, so {output.name} was removed")
        try:
            record("stopped")
        except OSError as exc:
            message += f"; {output.name} still records the attempt as in-progress because it cannot be updated: {exc}"
        return stop(OUTCOME_CODES[outcome], message)

    try:
        record("complete")
    except OSError as exc:
        return stop(
            "persist.publish_unverified",
            f"every step verified but {output.name} cannot record completion: {exc}; issues: {json.dumps(numbers)}",
        )
    _emit({"valid": True, "status": "complete", "publication": str(output), "issues": numbers})
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", required=True)
    parser.add_argument("--github-repo")
    parser.add_argument("--label", action="append", default=[])
    parser.add_argument("--persist-input", type=Path, required=True)
    parser.add_argument("--preview", type=Path, required=True)
    parser.add_argument("--reconciliation-input", type=Path, required=True)
    parser.add_argument("--reconciliation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--publish-confirmation", dest="confirmation", default=None)
    return parser


def main(argv: list[str] | None = None, *, client_factory: Callable[[], WriteClient] = GitHubClient) -> int:
    return publish(_parser().parse_args(argv), client_factory)


if __name__ == "__main__":
    raise SystemExit(main())

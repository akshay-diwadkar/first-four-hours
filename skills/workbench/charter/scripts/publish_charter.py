"""Check, create, or revise the one GitHub umbrella issue that publishes a charter, bound to a confirmed hash."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _diagnostic_contract import normalize_diagnostic  # noqa: E402
from charter_workspace import WorkspaceError, charter_path, normalize_slug  # noqa: E402

MARKER = "<!-- first-four-hours-charter: {slug} -->"
SECTIONS = ("Purpose", "Agreed", "Unsettled", "Revisions", "Authority")
GH_TIMEOUT_SECONDS = 60
REPO_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
STATE_PATTERN = re.compile(r"- State: (settling|ready)\s*")
ISSUE_PATTERN = re.compile(r"- Issue: ([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#([1-9][0-9]*)\s*")
HASH_PATTERN = re.compile(r"- Published content_sha256: ([0-9a-f]{64})\s*")


class GitHubError(Exception):
    """A failed or unreadable GitHub call."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class CharterError(Exception):
    """A named publication defect with its smallest credible repair."""

    def __init__(self, code: str, message: str, action: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.action = action


def _http_status(stderr: str) -> int | None:
    match = re.search(r"(?:HTTP|status(?: code)?)\s*[:=]?\s*(\d{3})", stderr, re.IGNORECASE)
    return int(match.group(1)) if match else None


def gh_api(method: str, path: str, payload: dict[str, str] | None = None) -> Any:
    """Run one `gh api` call with the caller's environment; never retried."""
    argv = ["gh", "api", path, "-X", method]
    data = None
    if payload is not None:
        argv += ["--input", "-"]
        data = json.dumps(payload).encode("utf-8")
    try:
        completed = subprocess.run(argv, input=data, capture_output=True, timeout=GH_TIMEOUT_SECONDS, check=False)
    except FileNotFoundError:
        raise GitHubError("gh is not installed; install GitHub CLI, then run `gh auth login`") from None
    except subprocess.TimeoutExpired:
        raise GitHubError(f"gh did not finish {method} {path} within {GH_TIMEOUT_SECONDS} seconds") from None
    except OSError as exc:
        raise GitHubError(f"gh could not run {method} {path}: {exc}") from None
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        status = _http_status(stderr)
        if status == 401 or "gh auth login" in stderr:
            raise GitHubError("gh is not authenticated for github.com; run `gh auth login`", status=401)
        raise GitHubError(f"GitHub API {method} {path} failed: {stderr}", status=status)
    stdout = completed.stdout.decode("utf-8", errors="replace").strip()
    if not stdout:
        return None
    try:
        return json.loads(stdout)
    except ValueError:
        raise GitHubError(f"GitHub API {method} {path} returned invalid JSON") from None


def _canonical(title: str, body: str | None) -> tuple[str, str]:
    return title.strip(), (body or "").replace("\r\n", "\n").replace("\r", "\n").rstrip()


def content_sha256(title: str, body: str | None) -> str:
    canonical_title, canonical_body = _canonical(title, body)
    encoded = json.dumps([canonical_title, canonical_body], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def render(text: str, slug: str) -> dict[str, Any]:
    """Render the issue title and body from the local charter text, or refuse its shape."""
    lines = text.split("\n")
    first = next((line for line in lines if line.strip()), "")
    title_match = re.fullmatch(r"# (\S.*)", first)
    if title_match is None:
        raise CharterError(
            "charter.shape", "charter.md must start with a `# <title>` heading", "restore the `# Charter — <name>` heading"
        )
    title = title_match.group(1).strip()
    headings = [(index, match.group(1)) for index, line in enumerate(lines) if (match := re.fullmatch(r"## (.+?)\s*", line))]
    names = [name for _, name in headings]
    if tuple(names) != SECTIONS:
        raise CharterError(
            "charter.shape",
            f"charter.md must hold exactly the `##` headings {', '.join(SECTIONS)} in that order; found: {', '.join(names) or 'none'}",
            "repair the headings (use `###` inside a section) and rerun",
        )
    purpose_index, authority_index = headings[0][0], headings[-1][0]
    content = "\n".join(lines[purpose_index:authority_index]).rstrip()
    authority = lines[authority_index + 1 :]
    states = [match.group(1) for line in authority if (match := STATE_PATTERN.fullmatch(line))]
    if len(states) != 1:
        raise CharterError(
            "charter.state_missing",
            "Authority must hold exactly one `- State: settling` or `- State: ready` line",
            "repair the State line and rerun",
        )
    state = states[0]
    not_live_lines = [line for line in authority if line.startswith("- Not live: ")]
    if len(not_live_lines) > 1:
        raise CharterError("charter.shape", "Authority holds more than one `- Not live:` line", "keep a single Not live line")
    not_live = not_live_lines[0][len("- Not live: ") :].strip() if not_live_lines else None
    issues = [match for line in authority if (match := ISSUE_PATTERN.fullmatch(line))]
    hashes = [match for line in authority if (match := HASH_PATTERN.fullmatch(line))]
    pointer = None
    if issues or hashes:
        if len(issues) != 1 or len(hashes) != 1:
            raise CharterError(
                "charter.pointer_malformed",
                "Authority holds only one of the `- Issue:` and `- Published content_sha256:` lines, or repeats one",
                "restore both pointer lines, or remove both only if the user confirms the charter was never published",
            )
        pointer = {"repo": issues[0].group(1), "number": int(issues[0].group(2)), "content_sha256": hashes[0].group(1)}
    body = (
        content
        + "\n\n## Authority\n\nThis issue owns the charter for project `"
        + slug
        + "`. A local `charter.md` copy is non-authoritative context.\n\n"
        + (f"- Not live: {not_live}\n" if not_live else "")
        + f"- State: {state}\n\n"
        + MARKER.format(slug=slug)
    )
    if len(title) > 256 or len(body) > 65536:
        raise CharterError(
            "charter.too_long",
            f"the issue title ({len(title)} characters, limit 256) or body ({len(body)} characters, limit 65536) is too long",
            "shorten the charter and rerun",
        )
    canonical_title, canonical_body = _canonical(title, body)
    return {
        "title": canonical_title,
        "body": canonical_body,
        "content_sha256": content_sha256(canonical_title, canonical_body),
        "state": state,
        "not_live": not_live,
        "pointer": pointer,
        "authority_index": authority_index,
    }


def _where(issue: dict[str, Any]) -> str:
    return f"issue #{issue.get('number')} ({issue.get('html_url', '')})"


def _issue_hash(issue: dict[str, Any]) -> str:
    return content_sha256(issue.get("title") or "", issue.get("body"))


def _find_marked(repo: str, slug: str) -> list[dict[str, Any]]:
    marker = MARKER.format(slug=slug)
    found: list[dict[str, Any]] = []
    page = 1
    while True:
        try:
            items = gh_api("GET", f"/repos/{repo}/issues?state=all&per_page=100&page={page}")
        except GitHubError as exc:
            raise CharterError("charter.github_failed", str(exc), "repair gh or the network and rerun; nothing was written") from None
        items = items or []
        for item in items:
            if "pull_request" in item:
                continue
            if marker in _canonical("", item.get("body"))[1].split("\n"):
                found.append(item)
        if len(items) < 100:
            return found
        page += 1


def _get_issue(repo: str, number: int) -> dict[str, Any]:
    try:
        issue = gh_api("GET", f"/repos/{repo}/issues/{number}")
    except GitHubError as exc:
        if exc.status in (404, 410):
            raise CharterError(
                "charter.issue_missing",
                f"issue {repo}#{number} no longer exists",
                "ask the user; restoring local authority means restoring the unpublished Authority lines",
            ) from None
        raise CharterError("charter.github_failed", str(exc), "repair gh or the network and rerun; nothing was written") from None
    if not isinstance(issue, dict) or "pull_request" in issue:
        raise CharterError(
            "charter.issue_missing",
            f"{repo}#{number} is not an issue",
            "ask the user; restoring local authority means restoring the unpublished Authority lines",
        )
    return issue


def _summary(issue: dict[str, Any]) -> dict[str, Any]:
    title, body = _canonical(issue.get("title") or "", issue.get("body"))
    return {
        "number": issue["number"],
        "url": issue.get("html_url", ""),
        "state": issue.get("state", ""),
        "title": title,
        "body": body,
        "content_sha256": content_sha256(title, body),
    }


def _readback(repo: str, number: int, confirm: str) -> dict[str, Any]:
    try:
        issue = gh_api("GET", f"/repos/{repo}/issues/{number}")
    except GitHubError as exc:
        raise CharterError(
            "charter.publish_uncertain",
            f"issue {repo}#{number} could not be read back ({exc}); it may hold the confirmed text",
            "rerun check, then the same command; it adopts an issue that already holds the confirmed text",
        ) from None
    actual = _issue_hash(issue)
    if actual != confirm:
        raise CharterError(
            "charter.readback_mismatch",
            f"{_where(issue)} holds other text than was sent: content_sha256 {actual}, confirmed {confirm}",
            "show the user the issue, then revise with base after their decision; the local pointer was not written",
        )
    return issue


def _write_pointer(path: Path, text: str, rendered: dict[str, Any], repo: str, issue: dict[str, Any], confirm: str) -> None:
    lines = text.split("\n")
    authority = [
        f"- Owner: GitHub issue {issue.get('html_url', '')} owns this definition. "
        "The sections above are non-authoritative context; read the issue before acting on them.",
        f"- Issue: {repo}#{issue['number']}",
        f"- Published content_sha256: {confirm}",
    ]
    if rendered["not_live"]:
        authority.append(f"- Not live: {rendered['not_live']}")
    authority.append(f"- State: {rendered['state']}")
    new_text = "\n".join(lines[: rendered["authority_index"]]).rstrip("\n") + "\n\n## Authority\n\n" + "".join(f"{line}\n" for line in authority)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False, prefix=".charter-", suffix=".tmp"
        ) as handle:
            temporary = handle.name
            handle.write(new_text)
        os.replace(temporary, path)
    except OSError as exc:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass
        raise CharterError(
            "charter.pointer_write_failed",
            f"{_where(issue)} is verified but the local pointer was not written: {exc}",
            "repair the file problem and rerun the same command; it adopts the verified issue",
        ) from None


def _finish(status: str, path: Path, text: str, rendered: dict[str, Any], repo: str, issue: dict[str, Any], confirm: str) -> dict[str, Any]:
    _write_pointer(path, text, rendered, repo, issue, confirm)
    return {
        "status": status,
        "issue": {"repo": repo, "number": issue["number"], "url": issue.get("html_url", "")},
        "content_sha256": confirm,
        "path": str(path),
    }


def _payload(rendered: dict[str, Any]) -> dict[str, str]:
    return {"title": rendered["title"], "body": rendered["body"]}


def _update(repo: str, number: int, path: Path, text: str, rendered: dict[str, Any], confirm: str) -> dict[str, Any]:
    try:
        gh_api("PATCH", f"/repos/{repo}/issues/{number}", _payload(rendered))
    except GitHubError as exc:
        raise CharterError(
            "charter.publish_uncertain",
            f"updating issue {repo}#{number} failed or its result was lost ({exc}); it may have changed",
            "rerun check, then the same command; it adopts an issue that already holds the confirmed text",
        ) from None
    issue = _readback(repo, number, confirm)
    return _finish("revised", path, text, rendered, repo, issue, confirm)


def _check(repo: str, slug: str, rendered: dict[str, Any]) -> dict[str, Any]:
    pointer = rendered["pointer"]
    if pointer is not None:
        _same_destination(pointer, repo)
        existing = [_summary(_get_issue(pointer["repo"], pointer["number"]))]
        matches: bool | None = rendered["content_sha256"] == pointer["content_sha256"]
    else:
        existing = [_summary(issue) for issue in _find_marked(repo, slug)]
        matches = None
    return {
        "status": "checked",
        "title": rendered["title"],
        "body": rendered["body"],
        "content_sha256": rendered["content_sha256"],
        "state": rendered["state"],
        "destination": repo,
        "pointer": pointer,
        "existing": existing,
        "local_matches_pointer": matches,
    }


def _same_destination(pointer: dict[str, Any], repo: str) -> None:
    if pointer["repo"].lower() != repo.lower():
        raise CharterError(
            "charter.destination_mismatch",
            f"the charter is published at {pointer['repo']}#{pointer['number']}, not {repo}",
            f"pass the pointer's repository {pointer['repo']}",
        )


def _create(repo: str, slug: str, path: Path, text: str, rendered: dict[str, Any], confirm: str) -> dict[str, Any]:
    if rendered["pointer"] is not None:
        pointer = rendered["pointer"]
        raise CharterError(
            "charter.already_published",
            f"the charter is already published at {pointer['repo']}#{pointer['number']}",
            "use revise to change the published charter",
        )
    marked = _find_marked(repo, slug)
    if len(marked) > 1:
        numbers = ", ".join(_where(issue) for issue in marked)
        raise CharterError(
            "charter.umbrella_ambiguous",
            f"several issues carry this slug's marker: {numbers}",
            "ask the user which is the umbrella and to remove the marker from the others",
        )
    if marked:
        issue = marked[0]
        if issue.get("state") != "open":
            raise CharterError(
                "charter.umbrella_closed",
                f"{_where(issue)} carries this slug's marker but is closed",
                "ask the user to reopen it, or define a different project under a new slug",
            )
        if _issue_hash(issue) == confirm:
            return _finish("adopted", path, text, rendered, repo, issue, confirm)
        raise CharterError(
            "charter.umbrella_differs",
            f"{_where(issue)} carries this slug's marker but holds other text (content_sha256 {_issue_hash(issue)})",
            "show the user its text from check; after their decision to replace it, run revise with base",
        )
    try:
        created = gh_api("POST", f"/repos/{repo}/issues", _payload(rendered))
    except GitHubError as exc:
        created = None
        detail = str(exc)
    else:
        detail = "the result carried no issue number"
    if not isinstance(created, dict) or not isinstance(created.get("number"), int):
        raise CharterError(
            "charter.publish_uncertain",
            f"creating the issue in {repo} failed or its result was lost ({detail}); an issue may exist",
            "rerun check, which finds it by its marker, then create again; it adopts an issue that already holds the confirmed text",
        )
    issue = _readback(repo, created["number"], confirm)
    return _finish("created", path, text, rendered, repo, issue, confirm)


def _revise(repo: str, slug: str, path: Path, text: str, rendered: dict[str, Any], confirm: str, base: str | None) -> dict[str, Any]:
    pointer = rendered["pointer"]
    if pointer is not None:
        _same_destination(pointer, repo)
        issue = _get_issue(pointer["repo"], pointer["number"])
        target_repo = pointer["repo"]
        recorded: str | None = pointer["content_sha256"]
    else:
        marked = _find_marked(repo, slug)
        if not marked:
            raise CharterError("charter.not_published", "no umbrella issue carries this slug's marker", "use create to publish it")
        if len(marked) > 1:
            numbers = ", ".join(_where(issue) for issue in marked)
            raise CharterError(
                "charter.umbrella_ambiguous",
                f"several issues carry this slug's marker: {numbers}",
                "ask the user which is the umbrella and to remove the marker from the others",
            )
        issue, target_repo, recorded = marked[0], repo, None
    if issue.get("state") != "open":
        raise CharterError(
            "charter.umbrella_closed",
            f"{_where(issue)} is closed",
            "ask the user to reopen it, or define a different project under a new slug",
        )
    current = _issue_hash(issue)
    if current == confirm:
        return _finish("adopted", path, text, rendered, target_repo, issue, confirm)
    expected = base if base is not None else recorded
    if expected is None or current != expected:
        recorded_note = f"; the pointer records {recorded}" if recorded else ""
        raise CharterError(
            "charter.issue_changed",
            f"{_where(issue)} holds text the user has not confirmed (content_sha256 {current}{recorded_note})",
            "show the user its text from check; bring the local file to it, or after their decision to replace it pass base",
        )
    return _update(target_repo, issue["number"], path, text, rendered, confirm)


def _emit(diagnostic: dict[str, Any]) -> None:
    print(json.dumps([diagnostic], sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("check", "create", "revise"))
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--confirm")
    parser.add_argument("--base")
    args = parser.parse_args(argv)
    path: Path | None = None
    try:
        if args.base is not None and args.mode != "revise":
            raise CharterError("charter.base_unsupported", "base is accepted only by revise", "drop base, or use revise")
        slug = normalize_slug(args.slug)
        repo = args.repo.strip()
        if REPO_PATTERN.fullmatch(repo) is None:
            raise CharterError("charter.repo_invalid", f"{args.repo!r} is not an owner/repo destination", "pass owner/repo from the user")
        path = charter_path(Path(args.repo_root), slug)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        rendered = render(text, slug)
        if args.mode != "check" and args.confirm != rendered["content_sha256"]:
            raise CharterError(
                "charter.unconfirmed",
                "the confirmation does not match the exact title and body rendered from the charter now",
                "run check, show the user the complete text, and ask again",
            )
        if args.mode == "check":
            result = _check(repo, slug, rendered)
        elif args.mode == "create":
            result = _create(repo, slug, path, text, rendered, args.confirm)
        else:
            result = _revise(repo, slug, path, text, rendered, args.confirm, args.base)
    except (WorkspaceError, CharterError) as exc:
        _emit(
            normalize_diagnostic(
                {"code": exc.code, "message": exc.message, "required_action": exc.action},
                skill="charter",
                phase=args.mode,
                artifact="charter",
                path=path if path is not None else args.repo_root,
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

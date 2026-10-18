#!/usr/bin/env python3
"""Shared, CLI-only GitHub helpers for ticket."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable

from _skill_protocol_runtime import compatible_version

TICKET_VERSION = "1.0.0"
OWNER_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?$")
SSH_REPO_PATTERN = re.compile(r"^git@github\.com:([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?)$")
WRITE_TIMEOUT_SECONDS = 120


class ConfigError(Exception):
    """Raised for invalid explicit input."""


class GitHubError(Exception):
    """Raised for GitHub CLI failures."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ResponseBudgetExceeded(GitHubError):
    """Raised after a response crosses the declared byte budget."""


def _http_status(stderr: str) -> int | None:
    match = re.search(r"(?:HTTP|status(?: code)?)\s*[:=]?\s*(\d{3})", stderr, re.IGNORECASE)
    return int(match.group(1)) if match else None


class GitHubClient:
    """Small wrapper around authenticated ``gh api`` reads and single-attempt writes."""

    def __init__(
        self,
        *,
        max_response_bytes: int = 8 * 1024 * 1024,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.max_response_bytes = max_response_bytes
        self.response_bytes = 0
        self.max_retries = max_retries
        self.sleep = sleep

    @staticmethod
    def _cli_environment() -> dict[str, str]:
        """Use only the GitHub CLI's stored authentication and configuration."""

        return {key: value for key, value in os.environ.items() if not key.upper().startswith(("GH_", "GITHUB_"))}

    def preflight(self) -> None:
        try:
            subprocess.run(
                ["gh", "auth", "status", "--hostname", "github.com"],
                capture_output=True,
                text=True,
                check=True,
                env=self._cli_environment(),
            )
        except FileNotFoundError as exc:
            raise GitHubError("gh is not installed; install GitHub CLI, then run `gh auth login`") from exc
        except OSError as exc:
            raise GitHubError(f"gh could not run `gh auth status`: {exc}") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            raise GitHubError(
                "gh is not authenticated for github.com; run `gh auth login`" + (f": {detail}" if detail else "")
            ) from exc

    def request(self, method: str, path: str) -> Any:
        if method != "GET":
            raise ConfigError("GitHubClient.request supports only GET; select stays read-only")
        for attempt in range(self.max_retries + 1):
            try:
                remaining = self.max_response_bytes - self.response_bytes
                with tempfile.TemporaryFile() as stderr_file:
                    process = subprocess.Popen(
                        ["gh", "api", path, "-X", method],
                        stdout=subprocess.PIPE,
                        stderr=stderr_file,
                        env=self._cli_environment(),
                    )
                    assert process.stdout is not None
                    stdout = process.stdout.read(remaining + 1)
                    if len(stdout) > remaining:
                        process.kill()
                        process.wait()
                        self.response_bytes += len(stdout)
                        raise ResponseBudgetExceeded(
                            f"GitHub response budget exceeded: {self.response_bytes} > {self.max_response_bytes} bytes"
                        )
                    returncode = process.wait()
                    stderr_file.seek(0)
                    stderr = stderr_file.read().decode("utf-8", errors="replace").strip()
                self.response_bytes += len(stdout)
                if returncode != 0:
                    status = _http_status(stderr)
                    transient = status is not None and (status == 429 or status >= 500)
                    if transient and attempt < self.max_retries:
                        self.sleep(1.0)
                        continue
                    raise GitHubError(f"GitHub API {method} {path} failed: {returncode} {stderr}", status=status)
                try:
                    decoded = stdout.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise GitHubError(f"GitHub API returned non-UTF-8 data for {method} {path}") from exc
                if not decoded.strip():
                    return None
                try:
                    return json.loads(decoded)
                except json.JSONDecodeError as exc:
                    raise GitHubError(f"GitHub API returned invalid JSON for {method} {path}") from exc
            except ResponseBudgetExceeded:
                raise
            except FileNotFoundError as exc:
                raise GitHubError("gh is not installed; install GitHub CLI, then run `gh auth login`") from exc
            except OSError as exc:
                raise GitHubError(f"gh could not run {method} {path}: {exc}") from exc
        raise GitHubError(f"GitHub API {method} {path} failed after retries")

    def mutate(self, method: str, path: str, payload: dict[str, Any]) -> Any:
        """Send one write through ``gh api`` exactly once; a write is never retried."""

        if method != "POST":
            raise ConfigError("GitHubClient.mutate supports only POST")
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        try:
            result = subprocess.run(
                ["gh", "api", path, "-X", method, "--input", "-"],
                input=body,
                capture_output=True,
                check=False,
                env=self._cli_environment(),
                timeout=WRITE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitHubError(f"gh did not finish {method} {path} within {WRITE_TIMEOUT_SECONDS} seconds") from exc
        except FileNotFoundError as exc:
            raise GitHubError("gh is not installed; install GitHub CLI, then run `gh auth login`") from exc
        except OSError as exc:
            raise GitHubError(f"gh could not run {method} {path}: {exc}") from exc
        stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        if result.returncode != 0:
            raise GitHubError(
                f"GitHub API {method} {path} failed: {result.returncode} {stderr}", status=_http_status(stderr)
            )
        try:
            decoded = (result.stdout or b"").decode("utf-8")
            return json.loads(decoded) if decoded.strip() else None
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubError(f"GitHub API returned invalid JSON for {method} {path}") from exc

    def paginated_get(self, path: str, *, item_limit: int | None = None) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        page = 1
        separator = "&" if "?" in path else "?"
        while item_limit is None or len(collected) < item_limit:
            per_page = min(100, item_limit - len(collected)) if item_limit is not None else 100
            batch = self.request("GET", f"{path}{separator}per_page={per_page}&page={page}")
            if not isinstance(batch, list):
                raise GitHubError(f"GitHub API returned unexpected response for {path}")
            collected.extend(item for item in batch if isinstance(item, dict))
            if len(batch) < per_page:
                break
            page += 1
        return collected[:item_limit] if item_limit is not None else collected


def normalize_github_repo_target(value: str | None) -> str:
    if not value or not value.strip():
        raise ConfigError("pass --github-repo with a GitHub URL or owner/repo target")

    target = value.strip()
    ssh_match = SSH_REPO_PATTERN.match(target)
    if ssh_match:
        target = ssh_match.group(1)
    elif OWNER_REPO_PATTERN.match(target):
        pass
    else:
        parsed = urllib.parse.urlparse(target)
        if parsed.scheme not in {"https", "ssh"} or parsed.hostname != "github.com":
            raise ConfigError("--github-repo must be a GitHub HTTPS URL, SSH URL, or owner/repo target")
        path = parsed.path.strip("/")
        if parsed.scheme == "ssh" and parsed.username and parsed.username != "git":
            raise ConfigError("SSH GitHub URLs must use the git user")
        if not OWNER_REPO_PATTERN.match(path):
            raise ConfigError("--github-repo must point to exactly one GitHub repository")
        target = path

    if target.endswith(".git"):
        target = target[:-4]
    if not OWNER_REPO_PATTERN.match(target):
        raise ConfigError("--github-repo must normalize to owner/repo")
    return target.casefold()


def positive_int(value: int, name: str) -> int:
    if value <= 0:
        raise ConfigError(f"{name} must be greater than zero")
    return value


def ensure_external_output(output: Path, *, repo_root: Path, skill_root: Path) -> Path:
    candidate = output.expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    for ancestor in (candidate.parent, *candidate.parents):
        if ancestor.exists() and ancestor.is_symlink():
            raise ConfigError(f"--output parent must not traverse a symlink: {ancestor}")
    resolved = candidate.resolve(strict=False)
    for label, root in (("target repository", repo_root), ("installed skill", skill_root)):
        resolved_root = root.resolve(strict=True)
        if resolved == resolved_root or resolved_root in resolved.parents:
            raise ConfigError(f"--output must be outside the {label}: {resolved_root}")
    return resolved


def contract_matches(value: object, expected: dict[str, Any]) -> bool:
    """Accept a recorded Ticket run contract whose fields match and whose version shares Ticket's major."""

    return (
        isinstance(value, dict)
        and set(value) == set(expected)
        and all(value[key] == expected[key] for key in expected if key != "version")
        and compatible_version(value.get("version"), expected["version"])
    )


def snapshot_digest(snapshot: dict[str, Any]) -> str:
    """Handoff digest; excludes the sole local wall-clock field."""

    excluded = {"digest", "fetched_at"}
    payload = {key: value for key, value in snapshot.items() if key not in excluded}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def graph_receipt(snapshot: dict[str, Any]) -> str:
    """Canonical graph receipt excluding only local fetch wall-clock time and receipts."""

    payload = {key: value for key, value in snapshot.items() if key not in {"digest", "graph_receipt", "fetched_at"}}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

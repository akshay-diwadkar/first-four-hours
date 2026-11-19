"""Shared dataclasses for normalized requests, results and reports.

These are deliberately plain dataclasses so the core can run without Pydantic.
The MCP layer converts Pydantic inputs into these types and renders the reports
back to text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PRIORITIES = ("must", "should", "nice")


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------
@dataclass
class ReadRequest:
    """One normalized read spec."""

    kind: str  # file | glob | grep | git_diff | git_changed | compare | handle | artifact
    label: str = ""
    artifact: str | None = None  # artifact reference ("artifact:NAME" or NAME)
    priority: str = "should"

    # file / handle
    path: str | None = None
    range: str | None = None
    mode: str = "auto"  # auto | lines | raw | target | context | grep | list | block | outline
    pattern: str | None = None
    context: int = 3
    handle: str | None = None
    since: str | None = None  # sha256 prefix or read handle; unchanged file -> no body
    depth: int = 1  # outline nesting depth

    # glob
    glob: str | None = None
    expand: bool = False
    max_files: int = 200
    include_ignored: bool = False  # glob: also list files git ignores

    # grep
    paths: list[str] = field(default_factory=list)
    ignore_case: bool = False
    fixed: bool = False
    max_matches: int = 200
    exclude: list[str] = field(default_factory=list)  # grep: path globs to skip
    max_line: int = 300  # grep: clip match lines to this many characters

    # git
    base: str = "HEAD"
    staged: bool = False
    stat: bool = False  # git diff: per-file change counts only

    # compare
    children: list["ReadRequest"] = field(default_factory=list)

    # common
    allow_outside: bool = False  # read paths outside cwd (reads only)
    encoding: str | None = None
    max_bytes: int | None = None
    max_lines: int | None = None
    stream: str = "stdout"

    # parse failure kept in-band so one bad spec never aborts the batch
    error: str | None = None


@dataclass
class RunRequest:
    """One normalized command spec."""

    index: int
    cmd: str | None = None
    argv: list[str] | None = None
    label: str = ""
    cwd: str | None = None
    timeout: float = 120.0
    env: dict[str, str] = field(default_factory=dict)
    shell: str = "auto"  # auto | bash | sh | cmd | powershell | direct
    slices: list[str] = field(default_factory=list)
    stdin: str | None = None
    priority: str = "should"
    merge_streams: bool = False
    max_bytes: int = 16384
    display: str = ""
    ok_exit: list[int] = field(default_factory=lambda: [0])  # exit codes that count as success


@dataclass
class EditRequest:
    path: str
    search: str
    replace: str
    replace_all: bool = False
    occurrence: int | None = None
    encoding: str | None = None
    label: str = ""
    range: tuple[int, int] | None = None  # whole lines N-M, instead of search
    since: str | None = None  # sha prefix or read handle the range was read at


@dataclass
class NewFileRequest:
    path: str
    content: str
    overwrite: bool = False
    mode: int | None = None
    encoding: str = "utf-8"


@dataclass
class RenameRequest:
    source: str
    destination: str
    overwrite: bool = False


@dataclass
class VerifyRequest:
    cmd: str | None = None
    argv: list[str] | None = None
    cwd: str | None = None
    timeout: float = 120.0
    env: dict[str, str] = field(default_factory=dict)
    shell: str = "auto"
    label: str = "verify"


@dataclass
class EditRequestBundle:
    edits: list[EditRequest] = field(default_factory=list)
    new_files: list[NewFileRequest] = field(default_factory=list)
    deletes: list[str] = field(default_factory=list)
    renames: list[RenameRequest] = field(default_factory=list)
    manifest: str | None = None
    cwd: str = "."
    dry_run: bool = False
    verify: VerifyRequest | None = None
    rollback_on_failure: bool = True
    overwrite: bool = False
    allow_outside: bool = False
    max_files: int = 100
    normalize_eol: bool = False


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
@dataclass
class ReadResult:
    id: str
    kind: str
    label: str
    status: str = "ok"  # ok | error | missing | skipped | truncated | binary | lossy | stale | unchanged | no_match
    path: str | None = None
    range: tuple[int, int] | None = None
    body: str = ""
    hash: str | None = None
    bytes_total: int | None = None
    bytes_shown: int = 0
    lines_total: int | None = None
    lines_shown: int = 0
    truncated: bool = False
    message: str | None = None
    handle: str | None = None
    artifact: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    id: str
    label: str
    status: str = "ok"  # ok | error | timeout | skipped
    exit_code: int | None = None
    timed_out: bool = False
    elapsed_ms: int = 0
    stdout: str = ""
    stderr: str = ""
    bytes_total: int = 0
    bytes_shown: int = 0
    truncated: bool = False
    shell: str = ""
    cwd: str = ""
    cmd_display: str = ""
    stdout_artifact: str | None = None
    stderr_artifact: str | None = None
    message: str | None = None
    slice_errors: list[str] = field(default_factory=list)
    budget_cut: bool = False  # output cut to fit the report budget (not the passing-output trim)


@dataclass
class FileChange:
    path: str
    action: str  # modify | create | delete | rename
    status: str = "ok"  # ok | error | skipped | rolled_back
    replacements: int = 0
    before_hash: str | None = None
    after_hash: str | None = None
    diff: str = ""
    message: str | None = None
    destination: str | None = None
    diff_artifact: str | None = None  # full diff when the shown one is cut
    diff_truncated: bool = False


@dataclass
class EditReport:
    ok: bool = True
    dry_run: bool = False
    changes: list[FileChange] = field(default_factory=list)
    verify: list[RunResult] = field(default_factory=list)
    rolled_back: bool = False
    rollback_status: str = "none"  # none | complete | partial | failed
    artifacts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    message: str | None = None


@dataclass
class Coverage:
    requested: int = 0
    read: int = 0
    ok: int = 0
    failed: int = 0
    missing: int = 0
    skipped: int = 0
    binary: int = 0
    lossy: int = 0
    stale: int = 0
    truncated: int = 0
    unchanged: int = 0
    no_match: int = 0
    commands_run: int = 0
    commands_failed: int = 0
    commands_timed_out: int = 0
    bytes_total: int = 0
    bytes_shown: int = 0
    not_inspected: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class Workspace:
    root: str = ""
    git_root: str | None = None
    head: str | None = None
    branch: str | None = None
    dirty: bool | None = None
    changed_count: int | None = None


@dataclass
class Report:
    tool: str
    mode: str = ""
    cwd: str = ""
    ok: bool = True
    workspace: Workspace = field(default_factory=Workspace)
    budget_tokens: int = 0
    budget_bytes: int = 0
    used_bytes: int = 0
    elapsed_ms: int = 0
    reads: list[ReadResult] = field(default_factory=list)
    runs: list[RunResult] = field(default_factory=list)
    edit: EditReport | None = None
    coverage: Coverage = field(default_factory=Coverage)
    unknowns: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    body: str = ""

"""Parse string and dictionary specifications into normalized requests.

String forms are deliberately small sugar.  Structured dictionaries are the
primary interface because they can carry cwd, timeouts, environments, labels,
priorities and slices without shell-quoting ambiguity.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .types import (
    EditRequest,
    NewFileRequest,
    ReadRequest,
    RenameRequest,
    RunRequest,
    VerifyRequest,
)


class SpecError(ValueError):
    pass


READ_MODES = {
    "auto",
    "lines",
    "raw",
    "target",
    "context",
    "grep",
    "list",
    "block",
    "outline",
    "diff",
    "changed",
    "compare",
    "handle",
}
SHELLS = {"auto", "bash", "sh", "cmd", "powershell", "direct"}
PRIORITIES = {"must", "should", "nice"}


def _as_dict(spec: Any, what: str) -> dict[str, Any]:
    if hasattr(spec, "model_dump"):
        data = spec.model_dump(exclude_none=True)
        return dict(data)
    if isinstance(spec, dict):
        return dict(spec)
    raise SpecError(f"{what} must be a string or object, got {type(spec).__name__}")


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def parse_read_spec(spec: Any) -> ReadRequest:
    if isinstance(spec, str):
        s = spec.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                data = json.loads(s)
                if isinstance(data, dict):
                    return _parse_read_dict(data)
            except Exception:
                pass
        return _parse_read_string(spec)
    return _parse_read_dict(_as_dict(spec, "read spec"))


def _parse_read_string(value: str) -> ReadRequest:
    s = value.strip()
    if not s:
        raise SpecError("read spec must not be empty")

    if s in ("@survey", "survey"):
        raise SpecError('use batch_read(mode="survey") for a repository survey')

    if s.startswith("git:diff"):
        return ReadRequest(kind="git_diff")
    if s.startswith("git:changed"):
        return ReadRequest(kind="git_changed")
    if s.startswith("grep:"):
        grep_pattern = s[len("grep:") :]
        if not grep_pattern:
            raise SpecError("grep spec requires a pattern")
        return ReadRequest(kind="grep", pattern=grep_pattern, max_files=5000)
    if s.startswith("artifact:"):
        ref = s[len("artifact:") :]
        m = re.match(r"^(.+?):(\d+(?:-\d+)?)$", ref)
        if m:
            return ReadRequest(kind="artifact", artifact=m.group(1), range=m.group(2))
        if not ref:
            raise SpecError("artifact spec requires a name")
        return ReadRequest(kind="artifact", artifact=ref)
    if s.startswith("glob:"):
        glob_pattern = s[len("glob:") :]
        if not glob_pattern:
            raise SpecError("glob spec requires a pattern")
        return ReadRequest(kind="glob", glob=glob_pattern)
    if s.startswith("handle:"):
        return ReadRequest(kind="handle", handle=s[len("handle:") :])

    mode = "auto"
    range_value: str | None = None
    pattern: str | None = None
    ctx = 3
    path_part = s

    if "@" in s:
        base, suffix = s.rsplit("@", 1)
        handled = False
        for prefix, op_mode in (
            ("target:", "target"),
            ("raw:", "raw"),
            ("lines:", "lines"),
            ("context:", "context"),
            ("grep:", "grep"),
            ("block:", "block"),
        ):
            if suffix.startswith(prefix):
                mode = op_mode
                rest = suffix[len(prefix) :]
                if op_mode in ("target", "raw", "lines"):
                    range_value = rest
                elif op_mode in ("grep", "block"):
                    if not rest:
                        raise SpecError(f"{op_mode} spec requires a pattern")
                    pattern = rest
                else:
                    pattern, ctx = _parse_context(rest)
                handled = True
                break
        if suffix in ("list", "diff", "changed", "outline"):
            mode = suffix
            handled = True
        if suffix.startswith("handle:"):
            return ReadRequest(kind="handle", handle=suffix[len("handle:") :])
        if not handled and re.match(r"^\d+(?:-\d+)?$", suffix):
            mode = "lines"
            range_value = suffix
            handled = True
        if handled:
            path_part = base

    if mode == "auto":
        m = re.match(r"^(.*):(\d+(?:-\d+)?)$", path_part)
        if m and m.group(1):
            path_part = m.group(1)
            range_value = m.group(2)
            mode = "lines"

    if not path_part:
        raise SpecError(f"read spec has no path: {value}")

    if mode in ("diff", "changed"):
        return ReadRequest(kind=f"git_{mode}", base="HEAD")
    return ReadRequest(
        kind="file",
        path=path_part,
        mode=mode,
        range=range_value,
        pattern=pattern,
        context=ctx,
    )


def _parse_context(rest: str) -> tuple[str, int]:
    if not rest:
        raise SpecError("context spec requires a pattern")
    pattern = rest
    ctx = 3
    if ":" in rest:
        maybe_pattern, maybe_n = rest.rsplit(":", 1)
        if maybe_n.strip().isdigit():
            pattern = maybe_pattern
            ctx = max(0, int(maybe_n))
    if not pattern:
        raise SpecError("context spec requires a pattern")
    return pattern, ctx


def _parse_read_dict(data: dict[str, Any]) -> ReadRequest:
    kinds = [k for k in ("path", "glob", "handle", "git", "compare", "artifact") if data.get(k) is not None]
    grep_value = data.get("grep")
    if grep_value is not None and not kinds:
        kinds.append("grep")
    if len(kinds) != 1:
        raise SpecError(
            "read spec must have exactly one of: path, glob, handle, grep, git, compare, artifact"
        )
    kind_key = kinds[0]

    if kind_key == "artifact":
        ref = str(data["artifact"]).strip()
        if not ref:
            raise SpecError("artifact must not be empty")
        range_value = data.get("range", data.get("lines"))
        pattern = data.get("pattern", data.get("grep"))
        return ReadRequest(
            kind="artifact",
            artifact=ref,
            range=str(range_value) if range_value is not None else None,
            pattern=str(pattern) if pattern else None,
            context=int(data.get("context", 0)),
            ignore_case=bool(data.get("ignore_case", False)),
            label=str(data.get("label") or ""),
            priority=str(data.get("priority") or "should"),
            max_bytes=int(data["max_bytes"]) if data.get("max_bytes") is not None else None,
        )

    mode = str(data.get("mode") or ("grep" if data.get("grep") is not None else "auto"))
    if mode not in READ_MODES:
        raise SpecError(f"unknown read mode: {mode}")

    priority = str(data.get("priority") or "should")
    if priority not in PRIORITIES:
        raise SpecError(f"unknown priority: {priority}")

    common: dict[str, Any] = dict(
        label=str(data.get("label") or ""),
        priority=priority,
        mode=mode,
        encoding=data.get("encoding"),
        max_bytes=int(data["max_bytes"]) if data.get("max_bytes") is not None else None,
        max_lines=int(data["max_lines"]) if data.get("max_lines") is not None else None,
        stream=str(data.get("stream") or "stdout"),
    )

    if kind_key == "path":
        path = str(data["path"])
        if not path:
            raise SpecError("path must not be empty")
        range_value = data.get("range", data.get("lines"))
        pattern = data.get("pattern")
        if mode == "grep":
            pattern = pattern if pattern is not None else data.get("grep")
            if not pattern:
                raise SpecError("file grep mode requires pattern or grep")
        if mode in ("context", "block"):
            pattern = pattern if pattern is not None else data.get("grep")
            if not pattern:
                raise SpecError(f"{mode} mode requires pattern")
        if mode == "target" and not range_value:
            raise SpecError("target mode requires range")
        since = data.get("since")
        return ReadRequest(
            kind="file",
            path=path,
            range=str(range_value) if range_value is not None else None,
            pattern=str(pattern) if pattern is not None else None,
            context=int(data.get("context", 3)),
            since=str(since) if since else None,
            depth=max(1, int(data.get("depth", 1))),
            **common,
        )

    if kind_key == "glob":
        pattern = str(data["glob"])
        if not pattern:
            raise SpecError("glob must not be empty")
        return ReadRequest(
            kind="glob",
            glob=pattern,
            expand=bool(data.get("expand", False)),
            include_ignored=bool(data.get("ignored", False)),
            max_files=_positive_int(data.get("max_files", 200), "max_files"),
            **common,
        )

    if kind_key == "handle":
        handle = str(data["handle"])
        if not handle:
            raise SpecError("handle must not be empty")
        return ReadRequest(kind="handle", handle=handle, **common)

    if kind_key == "grep":
        pattern = str(data["grep"])
        if not pattern:
            raise SpecError("grep must not be empty")
        return ReadRequest(
            kind="grep",
            pattern=pattern,
            paths=_str_list(data.get("paths")),
            ignore_case=bool(data.get("ignore_case", False)),
            fixed=bool(data.get("fixed", False)),
            context=int(data.get("context", 0)),
            max_matches=_positive_int(data.get("max_matches", 200), "max_matches"),
            max_files=_positive_int(data.get("max_files", 5000), "max_files"),
            exclude=_str_list(data.get("exclude")),
            max_line=_positive_int(data.get("max_line", 300), "max_line"),
            **common,
        )

    if kind_key == "git":
        git_mode = str(data["git"])
        if git_mode not in ("diff", "changed"):
            raise SpecError("git must be 'diff' or 'changed'")
        return ReadRequest(
            kind=f"git_{git_mode}",
            base=str(data.get("base") or "HEAD"),
            staged=bool(data.get("staged", False)),
            paths=_str_list(data.get("paths")),
            context=int(data.get("context", 3)),
            **common,
        )

    # compare
    children_raw = data.get("compare")
    if not isinstance(children_raw, list) or len(children_raw) < 2:
        raise SpecError("compare requires a list of at least two read specs")
    children = [parse_read_spec(child) for child in children_raw]
    if any(child.kind not in ("file", "handle") for child in children):
        raise SpecError("compare children must be file or handle specs")
    return ReadRequest(kind="compare", children=children, **common)


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------
def parse_run_spec(spec: Any, index: int, *, default_timeout: float = 120.0) -> RunRequest:
    if isinstance(spec, str):
        s = spec.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                data = json.loads(s)
                if isinstance(data, dict):
                    return _parse_run_dict(data, index, default_timeout)
            except Exception:
                pass
        return _parse_run_string(spec, index, default_timeout)
    return _parse_run_dict(_as_dict(spec, "command spec"), index, default_timeout)


def _parse_run_string(value: str, index: int, default_timeout: float) -> RunRequest:
    s = value.strip()
    if not s:
        raise SpecError("command spec must not be empty")

    parts = s.split(" ||| ")
    command_part = parts[0].strip()
    slices = [p.strip() for p in parts[1:] if p.strip()]

    label = ""
    if command_part.startswith("@") and ": " in command_part:
        label_part, command_part = command_part.split(": ", 1)
        label = label_part[1:].strip()
        command_part = command_part.strip()

    if not command_part:
        raise SpecError("command must not be empty")
    return RunRequest(
        index=index,
        cmd=command_part,
        label=label,
        timeout=default_timeout,
        slices=slices,
        display=_display(label, command_part),
    )


def _parse_run_dict(data: dict[str, Any], index: int, default_timeout: float) -> RunRequest:
    if bool(data.get("cmd")) == bool(data.get("argv")):
        raise SpecError("command spec must have exactly one of cmd or argv")
    cmd = str(data["cmd"]) if data.get("cmd") is not None else None
    if cmd is not None and not cmd.strip():
        raise SpecError("cmd must not be empty")
    argv = data.get("argv")
    if argv is not None:
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            raise SpecError("argv must be a non-empty list of strings")
        argv = [str(a) for a in argv]

    shell = str(data.get("shell") or "auto")
    if shell not in SHELLS:
        raise SpecError(f"unknown shell: {shell}")
    priority = str(data.get("priority") or "should")
    if priority not in PRIORITIES:
        raise SpecError(f"unknown priority: {priority}")

    timeout = float(data.get("timeout", default_timeout))
    if timeout <= 0:
        raise SpecError("timeout must be positive")

    env_raw = data.get("env") or {}
    if not isinstance(env_raw, dict):
        raise SpecError("env must be an object")
    env = {str(k): str(v) for k, v in env_raw.items()}

    slices_raw = data.get("slices") or []
    if isinstance(slices_raw, str):
        slices = [p.strip() for p in slices_raw.split("|||") if p.strip()]
    elif isinstance(slices_raw, list):
        slices = [str(p).strip() for p in slices_raw if str(p).strip()]
    else:
        raise SpecError("slices must be a list or string")

    max_bytes = _positive_int(data.get("max_bytes", 16384), "max_bytes")
    label = str(data.get("label") or "")
    display = _display(label, cmd if cmd is not None else " ".join(argv or []))

    return RunRequest(
        index=index,
        cmd=cmd,
        argv=argv,
        label=label,
        cwd=str(data["cwd"]) if data.get("cwd") is not None else None,
        timeout=timeout,
        env=env,
        shell=shell,
        slices=slices,
        stdin=str(data["stdin"]) if data.get("stdin") is not None else None,
        priority=priority,
        merge_streams=bool(data.get("merge_streams", False)),
        max_bytes=max_bytes,
        display=display,
    )


def _display(label: str, command: str) -> str:
    text = f"{label}: {command}" if label else command
    return text if len(text) <= 120 else text[:117] + "..."


# ---------------------------------------------------------------------------
# Edits
# ---------------------------------------------------------------------------
def parse_edit_spec(spec: Any) -> EditRequest:
    data = _as_dict(spec, "edit spec")
    path = str(data.get("path") or "")
    search = data.get("search")
    replace = data.get("replace")
    if not path:
        raise SpecError("edit spec requires path")
    if not isinstance(search, str):
        raise SpecError(f"edit for {path}: search must be a string")
    if not isinstance(replace, str):
        raise SpecError(f"edit for {path}: replace must be a string")
    if not search or not search.strip():
        raise SpecError(f"edit for {path}: search must not be empty or whitespace-only")

    replace_all = bool(data.get("replace_all", False))
    occurrence = data.get("occurrence")
    if occurrence is not None:
        try:
            occurrence = int(occurrence)
        except (TypeError, ValueError) as exc:
            raise SpecError(f"edit for {path}: occurrence must be an integer") from exc
        if occurrence < 1:
            raise SpecError(f"edit for {path}: occurrence is 1-based")
        if replace_all:
            raise SpecError(f"edit for {path}: use either replace_all or occurrence, not both")

    return EditRequest(
        path=path,
        search=search,
        replace=replace,
        replace_all=replace_all,
        occurrence=occurrence,
        encoding=data.get("encoding"),
        label=str(data.get("label") or ""),
    )


def parse_new_file(spec: Any) -> NewFileRequest:
    data = _as_dict(spec, "new file spec")
    path = str(data.get("path") or "")
    content = data.get("content")
    if not path:
        raise SpecError("new file spec requires path")
    if not isinstance(content, str):
        raise SpecError(f"new file {path}: content must be a string")
    mode_value = data.get("mode")
    if mode_value is None:
        mode = None
    elif isinstance(mode_value, int):
        mode = mode_value
    else:
        try:
            mode = int(str(mode_value), 8)
        except ValueError as exc:
            raise SpecError(f"new file {path}: mode must be an octal integer") from exc
    return NewFileRequest(
        path=path,
        content=content,
        overwrite=bool(data.get("overwrite", False)),
        mode=mode,
        encoding=str(data.get("encoding") or "utf-8"),
    )


def parse_new_files(value: Any) -> list[NewFileRequest]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [parse_new_file({"path": path, "content": content}) for path, content in value.items()]
    if isinstance(value, list):
        return [parse_new_file(item) for item in value]
    raise SpecError("new_files must be an object of path -> content or a list")


def parse_rename(spec: Any) -> RenameRequest:
    data = _as_dict(spec, "rename spec")
    source = str(data.get("from", data.get("source", "")) or "")
    destination = str(data.get("to", data.get("destination", "")) or "")
    if not source or not destination:
        raise SpecError("rename spec requires from and to")
    return RenameRequest(source=source, destination=destination, overwrite=bool(data.get("overwrite", False)))


def parse_verify(spec: Any) -> VerifyRequest | None:
    if spec is None:
        return None
    if isinstance(spec, str):
        text = spec.strip()
        if not text:
            raise SpecError("verify command must not be empty")
        return VerifyRequest(cmd=text)
    data = _as_dict(spec, "verify spec")
    if bool(data.get("cmd")) == bool(data.get("argv")):
        raise SpecError("verify must have exactly one of cmd or argv")
    argv = data.get("argv")
    if argv is not None:
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            raise SpecError("verify argv must be a non-empty list of strings")
        argv = [str(a) for a in argv]
    env_raw = data.get("env") or {}
    if not isinstance(env_raw, dict):
        raise SpecError("verify env must be an object")
    return VerifyRequest(
        cmd=str(data["cmd"]) if data.get("cmd") is not None else None,
        argv=argv,
        cwd=str(data["cwd"]) if data.get("cwd") is not None else None,
        timeout=float(data.get("timeout", 120)),
        env={str(k): str(v) for k, v in env_raw.items()},
        shell=str(data.get("shell") or "auto"),
        label=str(data.get("label") or "verify"),
    )


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
_BLOCK = re.compile(r"<<<(FILE|NEW_FILE|NEWFILE):\s*([^\n>]+)>>>", re.MULTILINE)
_SEARCH_REPLACE = re.compile(
    r"<<<SEARCH>>>\n?(.*?)\n?<<<REPLACE>>>\n?(.*?)\n?<<<END>>>",
    re.DOTALL,
)


def parse_manifest(text: str, work_dir: str = ".") -> tuple[str, list[EditRequest], list[NewFileRequest]]:
    """Return ("blocks", edits, new_files) or ("diff", [], []).

    The delimiter format is sugar for shell-free multi-file edits.  Missing
    END markers, empty searches and blocks without SEARCH/REPLACE pairs are
    errors, not silent best-effort parses.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    stripped = normalized.strip()
    if not stripped:
        raise SpecError("manifest is empty")
    if stripped.startswith("diff --git") or stripped.startswith("--- a/") or stripped.startswith("--- /dev/null"):
        return "diff", [], []

    matches = list(_BLOCK.finditer(normalized))
    if not matches:
        raise SpecError("manifest has no <<<FILE: path>>> or <<<NEWFILE: path>>> blocks")

    edits: list[EditRequest] = []
    new_files: list[NewFileRequest] = []
    for i, match in enumerate(matches):
        block_type = match.group(1)
        path = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(normalized)
        body = normalized[start:end]

        if block_type in ("NEW_FILE", "NEWFILE"):
            end_tag = body.rfind("<<<END>>>")
            if end_tag == -1:
                raise SpecError(f"manifest new file {path}: missing <<<END>>>")
            content = body[:end_tag]
            if content.startswith("\n"):
                content = content[1:]
            new_files.append(NewFileRequest(path=path, content=content))

        elif block_type == "FILE":
            pairs = list(_SEARCH_REPLACE.finditer(body))
            if not pairs:
                raise SpecError(f"manifest file {path}: no complete <<<SEARCH>>>...<<<REPLACE>>>...<<<END>>> block")
            for pair in pairs:
                search = pair.group(1)
                replace = pair.group(2)
                if not search or not search.strip():
                    raise SpecError(f"manifest file {path}: empty or whitespace-only search block")
                edits.append(EditRequest(path=path, search=search, replace=replace))

    if not edits and not new_files:
        raise SpecError("manifest produced no edits or new files")
    return "blocks", edits, new_files


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _positive_int(value: Any, name: str) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise SpecError(f"{name} must be an integer") from exc
    if n < 1:
        raise SpecError(f"{name} must be positive")
    return n


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, (str, int)) for v in value):
        return [str(v) for v in value]
    raise SpecError("expected a string or list of strings")

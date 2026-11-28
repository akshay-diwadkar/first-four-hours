#!/usr/bin/env python3
"""Common provider-neutral CLI runtime for declaratively wrapped stateful skills."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, Sequence

_diagnostics = importlib.import_module("tools.diagnostics" if __package__ else "_diagnostic_contract")
diagnostic_command = _diagnostics.command
is_canonical = _diagnostics.is_canonical
normalize_diagnostic = _diagnostics.normalize_diagnostic

PROTOCOL_VERSION = "1.0.0"
STATE_FILE = ".skill-cli-state.json"
MANIFEST_FILE = "skill-protocol.json"
STATUSES = {"ready", "in_progress", "blocked", "complete", "error"}
PLACEHOLDER_RE = re.compile(r"\{(python|skill_dir|repo_root|run_dir|input\.[A-Za-z][A-Za-z0-9_-]*)\}")
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_BLOCKED = 3
EXIT_OPERATIONAL = 4
EXIT_INTERNAL = 70


def compatible_version(value: object, built_against: str) -> bool:
    """Accept a recorded producer version that shares the major of the version a consumer was built against."""
    return (
        isinstance(value, str)
        and SEMVER_RE.fullmatch(value) is not None
        and value.split(".")[0] == built_against.split(".")[0]
    )


def compatible_version_pattern(built_against: str) -> str:
    """Return a regex fragment matching exactly the versions ``compatible_version`` accepts."""
    major = built_against.split(".")[0]
    return rf"{major}\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"


class ProtocolError(Exception):
    """Expected protocol error carrying a stable code and exit status."""

    def __init__(self, code: str, message: str, hint: str, exit_code: int = EXIT_USAGE):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.exit_code = exit_code


class JsonArgumentParser(argparse.ArgumentParser):
    """Argument parser whose failures can be rendered through the protocol."""

    def error(self, message: str) -> NoReturn:
        raise ProtocolError("invocation.invalid", message, "Correct the command arguments and retry.")


@dataclass(frozen=True)
class Context:
    cli_path: Path
    skill_dir: Path
    repo_root: Path
    run_dir: Path | None
    manifest: dict[str, Any]
    manifest_digest: str
    inputs: dict[str, Any]
    output_format: str

    @property
    def skill(self) -> str:
        return str(self.manifest["skill"])


def _diagnostic(
    code: str,
    message: str,
    hint: str,
    *,
    severity: str = "error",
    details: dict[str, Any] | None = None,
    skill: str = "skill-protocol",
    phase: str = "validate",
    artifact: str = "skill-protocol",
    path: str | Path = ".",
    next_command: dict[str, Any] | None = None,
    category: str | None = None,
    required_action: str | None = None,
    valid_repairs: Sequence[str] | None = None,
    supporting_evidence: Sequence[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "message": message,
        "hint": hint,
        "details": details or {},
    }
    if category is not None:
        payload["category"] = category
    if required_action is not None:
        payload["required_action"] = required_action
    if valid_repairs is not None:
        payload["valid_repairs"] = list(valid_repairs)
    if supporting_evidence is not None:
        payload["supporting_evidence"] = list(supporting_evidence)
    return normalize_diagnostic(
        payload,
        skill=skill,
        phase=phase,
        artifact=artifact,
        path=path,
        next_command=next_command,
    )


def _empty_envelope(skill: str = "unknown") -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "skill": skill,
        "status": "error",
        "phase": None,
        "next_action": None,
        "next_command": None,
        "required_reads": [],
        "required_inputs": [],
        "allowed_writes": [],
        "forbidden_actions": [],
        "blocking_reasons": [],
        "diagnostics": [],
        "artifacts": [],
        "result": None,
    }


def _error_envelope(error: ProtocolError, skill: str = "unknown") -> dict[str, Any]:
    envelope = _empty_envelope(skill)
    envelope["status"] = "blocked" if error.exit_code == EXIT_BLOCKED else "error"
    envelope["blocking_reasons"] = [error.code]
    envelope["diagnostics"] = [
        _diagnostic(error.code, error.message, error.hint, skill=skill, artifact="invocation")
    ]
    return envelope


def _within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _canonical_dir(raw: str | Path, label: str) -> Path:
    try:
        path = Path(raw).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ProtocolError(
            f"path.{label}_invalid",
            f"{label.replace('_', ' ')} cannot be resolved: {raw}",
            f"Pass an existing directory with --{label.replace('_', '-')}. Details: {exc}",
        ) from exc
    if not path.is_dir():
        raise ProtocolError(
            f"path.{label}_invalid",
            f"{label.replace('_', ' ')} is not a directory: {path}",
            f"Pass an existing directory with --{label.replace('_', '-')}.",
        )
    return path


def _safe_future_path(raw: str | Path) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    missing: list[str] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor.name)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    try:
        resolved = cursor.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ProtocolError(
            "path.run_dir_invalid",
            f"run directory cannot be resolved safely: {raw}",
            f"Use a path beneath an existing directory. Details: {exc}",
        ) from exc
    for part in reversed(missing):
        resolved /= part
    return resolved


def _read_skill_name(skill_dir: Path) -> str:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise ProtocolError(
            "skill.metadata_missing",
            f"installed skill has no SKILL.md: {skill_dir}",
            "Pass the root directory of an installed skill.",
        )
    text = skill_md.read_text(encoding="utf-8")
    match = re.search(r"^name:\s*([A-Za-z0-9_-]+)\s*$", text, re.MULTILINE)
    if not match:
        raise ProtocolError(
            "skill.name_missing",
            f"SKILL.md has no valid name field: {skill_md}",
            "Add a YAML frontmatter name matching the installed skill directory.",
        )
    return match.group(1)


def _manifest_error(message: str) -> ProtocolError:
    return ProtocolError("manifest.invalid", message, "Repair skill-protocol.json and run doctor again.")


def _validate_template(value: str, input_names: set[str]) -> None:
    scrubbed = PLACEHOLDER_RE.sub("", value)
    if "{" in scrubbed or "}" in scrubbed:
        raise _manifest_error(f"unknown or malformed placeholder in {value!r}")
    for placeholder in PLACEHOLDER_RE.findall(value):
        if placeholder.startswith("input.") and placeholder.removeprefix("input.") not in input_names:
            raise _manifest_error(f"placeholder references unknown input {placeholder!r}")


def validate_manifest(data: Any, *, skill_dir: Path | None = None) -> list[str]:
    """Return deterministic manifest contract errors without third-party dependencies."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["manifest must be a JSON object"]
    required_fields = {
        "protocol_version",
        "skill",
        "minimum_python",
        "run_dir_policy",
        "requirements",
        "inputs",
        "artifacts",
        "phases",
        "commands",
    }
    if not required_fields <= set(data) or set(data) - required_fields - {"mode", "classification"}:
        errors.append(f"manifest fields must contain {sorted(required_fields)} with optional mode and classification")
    if not compatible_version(data.get("protocol_version"), PROTOCOL_VERSION):
        errors.append(f"protocol_version must share major version {PROTOCOL_VERSION.split('.')[0]} with {PROTOCOL_VERSION!r}")
    mode = data.get("mode", "stateful")
    if mode not in {"stateful", "stateless"}:
        errors.append("mode must be stateful or stateless")
    skill = data.get("skill")
    if not isinstance(skill, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", skill):
        errors.append("skill must be a kebab-case string")
    minimum_python = data.get("minimum_python")
    if not isinstance(minimum_python, str) or not re.fullmatch(r"\d+\.\d+", minimum_python):
        errors.append("minimum_python must be MAJOR.MINOR")
    if data.get("run_dir_policy") not in {"outside_skill", "outside_skill_and_repo"}:
        errors.append("run_dir_policy must be outside_skill or outside_skill_and_repo")

    requirements = data.get("requirements")
    if not isinstance(requirements, list):
        errors.append("requirements must be an array")
    else:
        for item in requirements:
            if (
                not isinstance(item, dict)
                or set(item) != {"distribution", "specifier"}
                or not isinstance(item.get("distribution"), str)
                or not isinstance(item.get("specifier"), str)
            ):
                errors.append("each requirement must contain only string distribution and specifier fields")

    inputs = data.get("inputs")
    input_names: set[str] = set()
    if not isinstance(inputs, list):
        errors.append("inputs must be an array")
    else:
        for item in inputs:
            required_input_fields = {
                "name",
                "kind",
                "required",
                "repeatable",
                "description",
                "choices",
            }
            optional_input_fields = {"required_for", "accepted_for", "path_policy"}
            if (
                not isinstance(item, dict)
                or not required_input_fields <= set(item)
                or set(item) - required_input_fields - optional_input_fields
            ):
                errors.append("each input must contain the complete input contract")
                continue
            name = item.get("name")
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name):
                errors.append("input names must be identifiers")
            elif name in input_names:
                errors.append(f"duplicate input {name!r}")
            else:
                input_names.add(name)
            if item.get("kind") not in {"string", "path", "choice"}:
                errors.append(f"input {name!r} has an unsupported kind")
            if not isinstance(item.get("required"), bool) or not isinstance(item.get("repeatable"), bool):
                errors.append(f"input {name!r} required and repeatable must be booleans")
            if not isinstance(item.get("description"), str):
                errors.append(f"input {name!r} description must be a string")
            choices = item.get("choices")
            if not isinstance(choices, list) or not all(isinstance(choice, str) for choice in choices):
                errors.append(f"input {name!r} choices must be an array of strings")
            if item.get("kind") == "choice" and not choices:
                errors.append(f"choice input {name!r} must declare choices")
            required_for = item.get("required_for", [])
            if not isinstance(required_for, list) or not all(
                isinstance(command, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", command)
                for command in required_for
            ):
                errors.append(f"input {name!r} required_for must be an array of command identifiers")
            accepted_for = item.get("accepted_for", [])
            if not isinstance(accepted_for, list) or not all(
                isinstance(command, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", command)
                for command in accepted_for
            ):
                errors.append(f"input {name!r} accepted_for must be an array of command identifiers")
            elif accepted_for and not set(required_for) <= set(accepted_for):
                errors.append(f"input {name!r} required_for must be a subset of accepted_for")
            path_policy = item.get("path_policy", "existing")
            if path_policy not in {"existing", "future"}:
                errors.append(f"input {name!r} path_policy must be existing or future")
            if "path_policy" in item and item.get("kind") != "path":
                errors.append(f"input {name!r} path_policy is only valid for path inputs")

    classification = data.get("classification")
    if classification is not None:
        fields = {
            "phase", "artifact", "required_inputs", "controlled_inputs",
            "override_input", "argv", "repeat",
        }
        if not isinstance(classification, dict) or set(classification) != fields:
            errors.append("classification must contain the complete classification contract")
        else:
            for key in ("required_inputs", "controlled_inputs"):
                values = classification.get(key)
                if not isinstance(values, list) or not all(value in input_names for value in values):
                    errors.append(f"classification {key} must reference declared inputs")
            if classification.get("override_input") not in input_names:
                errors.append("classification override_input must reference a declared input")
            argv = classification.get("argv")
            if not isinstance(argv, list) or not argv or not all(isinstance(value, str) for value in argv):
                errors.append("classification argv must be a non-empty string array")
            else:
                for value in argv:
                    try:
                        _validate_template(value, input_names)
                    except ProtocolError as exc:
                        errors.append(exc.message)
            repeat = classification.get("repeat")
            if not isinstance(repeat, list):
                errors.append("classification repeat must be an array")
            else:
                for item in repeat:
                    if (
                        not isinstance(item, dict)
                        or set(item) != {"input", "flag"}
                        or item.get("input") not in input_names
                        or not isinstance(item.get("flag"), str)
                    ):
                        errors.append("classification contains an invalid repeat expansion")

    artifacts = data.get("artifacts")
    artifact_names: set[str] = set()
    if not isinstance(artifacts, list):
        errors.append("artifacts must be an array")
    else:
        for item in artifacts:
            required_artifact_fields = {"name", "path", "media_type"}
            if (
                not isinstance(item, dict)
                or not required_artifact_fields <= set(item)
                or set(item) - required_artifact_fields - {"external"}
                or not all(isinstance(item.get(key), str) for key in required_artifact_fields)
                or not isinstance(item.get("external", False), bool)
            ):
                errors.append("each artifact must contain only name, path, and media_type strings")
                continue
            artifact_names.add(item["name"])
            if item.get("external", False):
                definitions = {
                    definition.get("name"): definition for definition in inputs or [] if isinstance(definition, dict)
                }
                placeholders = re.findall(r"\{input\.([A-Za-z][A-Za-z0-9_-]*)\}", item["path"])
                if not placeholders or any(definitions.get(name, {}).get("kind") != "path" for name in placeholders):
                    errors.append(
                        f"external artifact {item['name']!r} path must reference a declared path input"
                    )
            else:
                path = Path(item["path"])
                if path.is_absolute() or ".." in path.parts or "{" in item["path"]:
                    errors.append(f"artifact {item['name']!r} path must remain within the run directory")
            if item.get("external", False):
                try:
                    _validate_template(item["path"], input_names)
                except ProtocolError as exc:
                    errors.append(exc.message)

    phases = data.get("phases")
    phase_names = set(phases) if isinstance(phases, dict) else set()
    if not isinstance(phases, dict) or (mode == "stateful" and not phases):
        errors.append("stateful phases must be a non-empty object")
    else:
        if mode == "stateful" and "complete" not in phases:
            errors.append("phases must include complete")
        for phase_name, phase in phases.items():
            required_phase_fields = {
                "status",
                "next_action",
                "next_command",
                "required_reads",
                "allowed_writes",
                "forbidden_actions",
            }
            phase_fields = set(phase) if isinstance(phase, dict) else set()
            if (
                not isinstance(phase, dict)
                or not required_phase_fields <= set(phase)
                or phase_fields - required_phase_fields - {"conditional_reads", "result_artifact"}
            ):
                errors.append(f"phase {phase_name!r} must contain the complete phase contract")
                continue
            if phase.get("status") not in STATUSES - {"error"}:
                errors.append(f"phase {phase_name!r} has an invalid status")
            next_command = phase.get("next_command")
            if next_command is not None and (
                not isinstance(next_command, str)
                or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", next_command)
            ):
                errors.append(f"phase {phase_name!r} next_command must be a command identifier or null")
            for field in ("required_reads", "allowed_writes", "forbidden_actions"):
                if not isinstance(phase.get(field), list) or not all(
                    isinstance(value, str) for value in phase.get(field, [])
                ):
                    errors.append(f"phase {phase_name!r} {field} must be an array of strings")
            for value in [*phase.get("required_reads", []), *phase.get("allowed_writes", [])]:
                try:
                    _validate_template(value, input_names)
                except ProtocolError as exc:
                    errors.append(exc.message)
            conditional_reads = phase.get("conditional_reads", [])
            if not isinstance(conditional_reads, list):
                errors.append(f"phase {phase_name!r} conditional_reads must be an array")
            else:
                for condition in conditional_reads:
                    if (
                        not isinstance(condition, dict)
                        or set(condition) != {"input", "values", "paths"}
                        or condition.get("input") not in input_names
                        or not isinstance(condition.get("values"), list)
                        or not condition["values"]
                        or not all(isinstance(value, str) for value in condition["values"])
                        or not isinstance(condition.get("paths"), list)
                        or not condition["paths"]
                        or not all(isinstance(path, str) for path in condition["paths"])
                    ):
                        errors.append(f"phase {phase_name!r} contains an invalid conditional read")
                        continue
                    for value in condition["paths"]:
                        try:
                            _validate_template(value, input_names)
                        except ProtocolError as exc:
                            errors.append(exc.message)
            result_artifact = phase.get("result_artifact")
            if result_artifact is not None and (
                not isinstance(result_artifact, str) or result_artifact not in artifact_names
            ):
                errors.append(f"phase {phase_name!r} result_artifact must reference a declared artifact")

    if isinstance(classification, dict):
        if classification.get("phase") not in phase_names:
            errors.append("classification phase must reference a declared phase")
        if classification.get("artifact") not in artifact_names:
            errors.append("classification artifact must reference a declared artifact")

    commands = data.get("commands")
    if not isinstance(commands, dict):
        errors.append("commands must be an object")
        commands = {}
    if mode == "stateful" and "start" not in commands:
        errors.append("stateful manifests must declare start")
    if mode == "stateless" and not commands:
        errors.append("stateless manifests must declare at least one command")
    for command_name, raw_command in commands.items():
        if not isinstance(command_name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", command_name):
            errors.append("command names must be identifiers")
            continue
        variants = raw_command if isinstance(raw_command, list) else [raw_command]
        if not variants:
            errors.append(f"command {command_name!r} must declare at least one variant")
            continue
        for command in variants:
            required_command_fields = {"allowed_phases", "success_phase", "steps"}
            if (
                not isinstance(command, dict)
                or not required_command_fields <= set(command)
                or set(command) - required_command_fields - {"when", "allowed_writes"}
            ):
                errors.append(f"command {command_name!r} must contain the complete command contract")
                continue
            allowed_writes = command.get("allowed_writes", [])
            if not isinstance(allowed_writes, list) or not all(
                isinstance(path, str) for path in allowed_writes
            ):
                errors.append(f"command {command_name!r} allowed_writes must be an array of strings")
            when = command.get("when", {})
            if not isinstance(when, dict):
                errors.append(f"command {command_name!r} when must be an object")
            else:
                for input_name, values in when.items():
                    if (
                        input_name not in input_names
                        or not isinstance(values, list)
                        or not values
                        or not all(isinstance(value, str) for value in values)
                    ):
                        errors.append(f"command {command_name!r} contains an invalid variant condition")
            allowed = command.get("allowed_phases")
            if not isinstance(allowed, list) or not all(phase in phase_names for phase in allowed):
                errors.append(f"command {command_name!r} allowed_phases contains an unknown phase")
            success_phase = command.get("success_phase")
            if mode == "stateful":
                if success_phase not in phase_names:
                    errors.append(f"command {command_name!r} success_phase contains an unknown phase")
            elif success_phase is not None:
                errors.append(f"stateless command {command_name!r} success_phase must be null")
            steps = command.get("steps")
            if not isinstance(steps, list) or (not steps and command_name != "start"):
                errors.append(f"command {command_name!r} steps must be non-empty except for start")
                continue
            for step in steps:
                if not isinstance(step, dict) or set(step) != {
                    "argv",
                    "repeat",
                    "capture_stdout",
                    "diagnostics_json",
                    "failure",
                }:
                    errors.append(f"command {command_name!r} contains an invalid step contract")
                    continue
                argv = step.get("argv")
                if not isinstance(argv, list) or not argv or not all(isinstance(token, str) for token in argv):
                    errors.append(f"command {command_name!r} step argv must be a non-empty string array")
                    continue
                for token in argv:
                    try:
                        _validate_template(token, input_names)
                    except ProtocolError as exc:
                        errors.append(exc.message)
                repeat = step.get("repeat")
                if not isinstance(repeat, list):
                    errors.append(f"command {command_name!r} step repeat must be an array")
                else:
                    for item in repeat:
                        if (
                            not isinstance(item, dict)
                            or set(item) != {"input", "flag"}
                            or item.get("input") not in input_names
                            or not isinstance(item.get("flag"), str)
                        ):
                            errors.append(f"command {command_name!r} contains an invalid repeat expansion")
                capture = step.get("capture_stdout")
                if capture is not None and capture not in artifact_names:
                    errors.append(f"command {command_name!r} captures unknown artifact {capture!r}")
                if not isinstance(step.get("diagnostics_json"), bool):
                    errors.append(f"command {command_name!r} diagnostics_json must be boolean")
                if step.get("failure") not in {"blocked", "operational"}:
                    errors.append(f"command {command_name!r} failure must be blocked or operational")
                if skill_dir is not None and argv and argv[0] == "{python}" and len(argv) > 1:
                    script = argv[1].replace("{skill_dir}/", "")
                    if "{" not in script:
                        candidate = (skill_dir / script).resolve()
                        if not _within(candidate, skill_dir) or not candidate.is_file():
                            errors.append(f"command {command_name!r} script is missing or escapes the skill: {script}")
    for phase_name, phase in phases.items() if isinstance(phases, dict) else []:
        next_command = phase.get("next_command") if isinstance(phase, dict) else None
        synthetic = (
            isinstance(classification, dict)
            and phase_name == classification.get("phase")
            and next_command == "apply_classification"
        )
        if next_command is not None and next_command not in commands and not synthetic:
            errors.append(f"phase {phase_name!r} references unknown command {next_command!r}")
    declared_writes = {
        value
        for phase in (phases.values() if isinstance(phases, dict) else [])
        if isinstance(phase, dict)
        for value in phase.get("allowed_writes", [])
    }
    if mode == "stateless" and isinstance(commands, dict):
        declared_writes.update(
            value
            for raw_command in commands.values()
            for command in (raw_command if isinstance(raw_command, list) else [raw_command])
            if isinstance(command, dict)
            for value in command.get("allowed_writes", [])
        )
    for artifact in artifacts or []:
        if (
            isinstance(artifact, dict)
            and artifact.get("external", False)
            and artifact.get("path") not in declared_writes
        ):
            errors.append(
                f"external artifact {artifact.get('name')!r} must be declared in phase allowed_writes"
            )
    for item in inputs or []:
        if isinstance(item, dict):
            for command_name in item.get("required_for", []):
                if command_name not in commands:
                    errors.append(f"input {item.get('name')!r} requires unknown command {command_name!r}")
            for command_name in item.get("accepted_for", []):
                if command_name not in commands:
                    errors.append(f"input {item.get('name')!r} accepts unknown command {command_name!r}")
    return sorted(set(errors))


def _manifest_path(skill_dir: Path, manifest_relative_path: str) -> Path:
    relative = Path(manifest_relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ProtocolError(
            "manifest.path_invalid",
            f"manifest path must be relative and stay inside the installed skill: {manifest_relative_path}",
            "Pass a package-relative JSON manifest path.",
        )
    try:
        path = (skill_dir / relative).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ProtocolError(
            "manifest.path_invalid",
            f"manifest path cannot be resolved: {manifest_relative_path}",
            f"Pass an existing package-relative JSON file. Details: {exc}",
        ) from exc
    if not _within(path, skill_dir) or not path.is_file():
        raise ProtocolError(
            "manifest.path_invalid",
            f"manifest path must resolve to an existing regular file inside the installed skill: {manifest_relative_path}",
            "Pass an existing package-relative JSON file.",
        )
    return path


def _load_manifest(skill_dir: Path, manifest_relative_path: str = MANIFEST_FILE) -> tuple[dict[str, Any], str]:
    path = _manifest_path(skill_dir, manifest_relative_path)
    if not path.is_file():
        raise ProtocolError(
            "manifest.missing",
            f"installed skill does not opt into protocol {PROTOCOL_VERSION}: {path}",
            f"Add a valid {MANIFEST_FILE} or use the skill's existing public scripts.",
        )
    try:
        raw = path.read_bytes()
        data = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _manifest_error(f"cannot read {path}: {exc}") from exc
    errors = validate_manifest(data, skill_dir=skill_dir)
    if errors:
        raise _manifest_error("; ".join(errors))
    assert isinstance(data, dict)
    return data, hashlib.sha256(raw).hexdigest()


def _parse_inputs(raw_values: Sequence[str], manifest: dict[str, Any]) -> dict[str, Any]:
    definitions = {item["name"]: item for item in manifest["inputs"]}
    collected: dict[str, list[str]] = {}
    for raw in raw_values:
        if "=" not in raw:
            raise ProtocolError(
                "input.malformed",
                f"input must use name=value syntax: {raw!r}",
                "Pass each input as --input name=value.",
            )
        name, value = raw.split("=", 1)
        if name not in definitions:
            raise ProtocolError(
                "input.unknown",
                f"unknown input {name!r}",
                f"Use one of: {', '.join(sorted(definitions))}.",
            )
        collected.setdefault(name, []).append(value)
    result: dict[str, Any] = {}
    for name, definition in definitions.items():
        values = collected.get(name, [])
        if definition["required"] and not values:
            continue
        if not definition["repeatable"] and len(values) > 1:
            raise ProtocolError(
                "input.not_repeatable",
                f"input {name!r} may be provided only once",
                f"Remove duplicate --input {name}=... arguments.",
            )
        checked: list[str] = []
        for value in values:
            if definition["kind"] == "choice" and value not in definition["choices"]:
                raise ProtocolError(
                    "input.invalid_choice",
                    f"input {name!r} must be one of {definition['choices']}",
                    "Choose a declared manifest value.",
                )
            if definition["kind"] == "path":
                try:
                    value = str(
                        _safe_future_path(value)
                        if definition.get("path_policy", "existing") == "future"
                        else Path(value).expanduser().resolve(strict=True)
                    )
                except (OSError, RuntimeError) as exc:
                    raise ProtocolError(
                        "input.path_invalid",
                        f"input path {name!r} cannot be resolved: {value}",
                        f"Pass an existing path. Details: {exc}",
                    ) from exc
            checked.append(value)
        if checked:
            result[name] = checked if definition["repeatable"] else checked[0]
    return result


def _required_inputs(
    manifest: dict[str, Any],
    inputs: dict[str, Any],
    command_name: str | None = None,
) -> list[dict[str, Any]]:
    return [
        {
            "name": item["name"],
            "kind": item["kind"],
            "required": bool(
                item["required"] and command_name in {None, "start", "run"}
                or command_name in item.get("required_for", [])
            ),
            "repeatable": item["repeatable"],
            "description": item["description"],
        }
        for item in manifest["inputs"]
        if item["name"] not in inputs
        and (not item.get("accepted_for") or command_name in item["accepted_for"])
    ]


def _expand(value: str, context: Context, run_dir: Path) -> str:
    replacements = {
        "python": sys.executable,
        "skill_dir": str(context.skill_dir),
        "repo_root": str(context.repo_root),
        "run_dir": str(run_dir),
    }

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name.startswith("input."):
            input_name = name.removeprefix("input.")
            input_value = context.inputs.get(input_name)
            if isinstance(input_value, str):
                return input_value
            raise ProtocolError(
                "input.missing",
                f"command requires scalar input {input_name!r}",
                f"Pass --input {input_name}=<value> to start.",
            )
        return replacements[name]

    return PLACEHOLDER_RE.sub(replace, value)


def _resolve_display_path(value: str, context: Context) -> str:
    run_dir = context.run_dir or Path("{run_dir}")
    expanded = _expand(value, context, run_dir) if "{run_dir}" not in value or context.run_dir else value
    return expanded


def _artifact_list(context: Context, run_dir: Path | None = None) -> list[dict[str, Any]]:
    base = run_dir or context.run_dir
    artifacts: list[dict[str, Any]] = []
    for item in context.manifest["artifacts"]:
        if item.get("external", False):
            input_names = re.findall(r"\{input\.([A-Za-z][A-Za-z0-9_-]*)\}", item["path"])
            if any(name not in context.inputs for name in input_names):
                continue
            path = Path(_expand(item["path"], context, base or context.repo_root))
        else:
            path = base / item["path"] if base else Path(item["path"])
        artifacts.append(
            {
                "name": item["name"],
                "path": str(path),
                "media_type": item["media_type"],
                "exists": path.is_file(),
            }
        )
    return artifacts


def _command_variant(context: Context, command_name: str) -> dict[str, Any]:
    raw = context.manifest["commands"].get(command_name)
    if raw is None:
        raise ProtocolError(
            "command.unsupported",
            f"{command_name} is not supported by {context.skill}",
            "Use the next_command returned by the current phase.",
            EXIT_BLOCKED,
        )
    variants = raw if isinstance(raw, list) else [raw]
    matches = [
        command
        for command in variants
        if all(context.inputs.get(name) in values for name, values in command.get("when", {}).items())
    ]
    if len(matches) != 1:
        raise ProtocolError(
            "command.variant_unresolved",
            f"{command_name} requires one unambiguous input-selected variant",
            "Supply the required choice inputs returned by the protocol.",
            EXIT_BLOCKED,
        )
    return matches[0]


def _next_command(context: Context, command: str | None) -> dict[str, Any] | None:
    if command is None:
        return None
    argv = [
        sys.executable,
        str(context.cli_path),
        "--skill-dir",
        str(context.skill_dir),
        "--repo-root",
        str(context.repo_root),
    ]
    if context.run_dir:
        argv.extend(["--run-dir", str(context.run_dir)])
    if command in {"start", "run"}:
        for definition in context.manifest["inputs"]:
            name = definition["name"]
            values = context.inputs.get(name, [])
            if isinstance(values, str):
                values = [values]
            for value in values:
                argv.extend(["--input", f"{name}={value}"])
    argv.extend(["--format", context.output_format, command])
    return {"argv": argv, "cwd": str(context.repo_root)}


def _phase_envelope(
    context: Context,
    phase_name: str,
    *,
    diagnostics: list[dict[str, Any]] | None = None,
    blocking_reasons: list[str] | None = None,
) -> dict[str, Any]:
    phase = context.manifest["phases"][phase_name]
    reads = [
        {"path": _resolve_display_path(path, context), "reason": "Required by the current skill phase."}
        for path in phase["required_reads"]
    ]
    for condition in phase.get("conditional_reads", []):
        if context.inputs.get(condition["input"]) in condition["values"]:
            reads.extend(
                {
                    "path": _resolve_display_path(path, context),
                    "reason": f"Required for input {condition['input']} in this phase.",
                }
                for path in condition["paths"]
            )
    retry = _next_command(context, "next" if phase["next_command"] else None)
    normalized_diagnostics = [
        normalize_diagnostic(
            {
                **item,
                "skill": context.skill,
                "phase": phase_name,
            },
            skill=context.skill,
            phase=phase_name,
            artifact="workflow",
            path=context.run_dir or context.repo_root,
            next_command=item.get("next_command") or retry,
        )
        for item in diagnostics or []
    ]
    envelope = _empty_envelope(context.skill)
    envelope.update(
        {
            "status": "blocked" if blocking_reasons else phase["status"],
            "phase": phase_name,
            "next_action": phase["next_action"],
            "next_command": retry,
            "required_reads": reads,
            "required_inputs": _required_inputs(
                context.manifest,
                context.inputs,
                phase["next_command"],
            ),
            "allowed_writes": [_resolve_display_path(path, context) for path in phase["allowed_writes"]],
            "forbidden_actions": phase["forbidden_actions"],
            "blocking_reasons": blocking_reasons or [],
            "diagnostics": normalized_diagnostics,
            "artifacts": _artifact_list(context),
        }
    )
    result_artifact = phase.get("result_artifact")
    if result_artifact:
        definition = next(
            item for item in context.manifest["artifacts"] if item["name"] == result_artifact
        )
        assert context.run_dir is not None
        result_path = context.run_dir / definition["path"]
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProtocolError(
                "classification.result_invalid",
                f"cannot read classification result: {result_path}",
                f"Restart classification. Details: {exc}",
            ) from exc
        envelope["result"] = result
        controlled = set(context.manifest.get("classification", {}).get("controlled_inputs", []))
        envelope["required_inputs"] = [
            item for item in envelope["required_inputs"] if item["name"] not in controlled
        ]
    return envelope


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _state_data(context: Context, phase: str) -> dict[str, Any]:
    assert context.run_dir is not None
    state = {
        "protocol_version": PROTOCOL_VERSION,
        "skill": context.skill,
        "manifest_sha256": context.manifest_digest,
        "skill_dir": str(context.skill_dir),
        "repo_root": str(context.repo_root),
        "run_dir": str(context.run_dir),
        "inputs": context.inputs,
        "phase": phase,
        "status": context.manifest["phases"][phase]["status"],
        "artifacts": _artifact_list(context),
    }
    state["state_sha256"] = hashlib.sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return state


def _merge_state_inputs(context: Context, state: dict[str, Any]) -> None:
    stored = state["inputs"]
    for name, value in context.inputs.items():
        if name in stored and stored[name] != value:
            raise ProtocolError(
                "input.immutable",
                f"input {name!r} is already bound to a different value",
                "Reuse the original value or start a new run.",
                EXIT_BLOCKED,
            )
        stored[name] = value
    context.inputs.clear()
    context.inputs.update(stored)


def _write_state(context: Context, phase: str) -> None:
    assert context.run_dir is not None
    _atomic_json(context.run_dir / STATE_FILE, _state_data(context, phase))


def _load_state(context: Context) -> dict[str, Any]:
    if context.run_dir is None:
        raise ProtocolError("path.run_dir_required", "--run-dir is required", "Pass the run directory returned by start.")
    path = context.run_dir / STATE_FILE
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(
            "state.invalid",
            f"cannot read protocol state: {path}",
            f"Use the exact run directory returned by start. Details: {exc}",
        ) from exc
    if not isinstance(state, dict):
        raise ProtocolError("state.invalid", "protocol state must be a JSON object", "Repair or restart the run.")
    checksum = state.get("state_sha256")
    body = {key: value for key, value in state.items() if key != "state_sha256"}
    actual_checksum = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if not isinstance(checksum, str) or checksum != actual_checksum:
        raise ProtocolError(
            "state.tampered",
            "protocol state checksum does not match its contents",
            "Restore the original state or restart the run.",
        )
    if not compatible_version(state.get("protocol_version"), PROTOCOL_VERSION):
        raise ProtocolError(
            "state.identity_mismatch",
            f"state protocol_version must share major version {PROTOCOL_VERSION.split('.')[0]} with {PROTOCOL_VERSION!r}",
            "Restart the run with the current skill runtime.",
        )
    expected = {
        "skill": context.skill,
        "manifest_sha256": context.manifest_digest,
        "skill_dir": str(context.skill_dir),
        "repo_root": str(context.repo_root),
        "run_dir": str(context.run_dir),
    }
    for key, value in expected.items():
        if state.get(key) != value:
            raise ProtocolError(
                "state.identity_mismatch",
                f"state {key} does not match the current invocation",
                "Use the original skill, repository, runtime manifest, and run directory.",
            )
    phase = state.get("phase")
    if phase not in context.manifest["phases"]:
        raise ProtocolError("state.phase_invalid", f"unknown stored phase: {phase!r}", "Repair or restart the run.")
    if not isinstance(state.get("inputs"), dict):
        raise ProtocolError("state.inputs_invalid", "stored inputs are invalid", "Repair or restart the run.")
    return state


def _version_tuple(value: str) -> tuple[int, ...]:
    match = re.match(r"(\d+(?:\.\d+)*)", value)
    return tuple(int(part) for part in match.group(1).split(".")) if match else ()


def _satisfies(installed: str, specifier: str) -> bool:
    current = _version_tuple(installed)
    for operator, expected_text in re.findall(r"(>=|<=|==|!=|>|<)\s*([0-9][^,;\s]*)", specifier):
        expected = _version_tuple(expected_text)
        width = max(len(current), len(expected))
        left = current + (0,) * (width - len(current))
        right = expected + (0,) * (width - len(expected))
        if not {">=": left >= right, "<=": left <= right, "==": left == right, "!=": left != right, ">": left > right, "<": left < right}[operator]:
            return False
    return True


def _doctor(context: Context) -> tuple[int, dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    major, minor = (int(part) for part in context.manifest["minimum_python"].split("."))
    if sys.version_info[:2] < (major, minor):
        diagnostics.append(
            _diagnostic(
                "doctor.python_unsupported",
                f"Python {major}.{minor} or newer is required.",
                "Run the protocol with a supported Python interpreter.",
            )
        )
    for requirement in context.manifest["requirements"]:
        name = requirement["distribution"]
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            diagnostics.append(
                _diagnostic(
                    "doctor.dependency_missing",
                    f"Required distribution is not installed: {name}{requirement['specifier']}",
                    f"Install the requirements declared by {context.skill_dir / 'requirements.txt'}.",
                    details={"distribution": name, "specifier": requirement["specifier"]},
                )
            )
            continue
        if not _satisfies(installed, requirement["specifier"]):
            diagnostics.append(
                _diagnostic(
                    "doctor.dependency_incompatible",
                    f"{name} {installed} does not satisfy {requirement['specifier']}.",
                    f"Install the requirements declared by {context.skill_dir / 'requirements.txt'}.",
                )
            )
    if context.run_dir is not None:
        parent = context.run_dir.parent
        if not parent.is_dir() or not os.access(parent, os.W_OK):
            diagnostics.append(
                _diagnostic(
                    "doctor.run_dir_unwritable",
                    f"Run directory parent is not writable: {parent}",
                    "Choose a run directory beneath an existing writable directory.",
                )
            )
    mode = context.manifest.get("mode", "stateful")
    first_command = (
        "run"
        if mode == "stateless" and "run" in context.manifest["commands"]
        else next(iter(context.manifest["commands"]))
        if mode == "stateless"
        else "start"
    )
    required_inputs = (
        _classification_missing(context)
        if mode == "stateful" and context.manifest.get("classification") is not None
        else _required_inputs(context.manifest, context.inputs, first_command)
    )
    doctor_retry = _next_command(context, "doctor")
    diagnostics = [
        normalize_diagnostic(
            {**item, "skill": context.skill, "phase": "doctor"},
            skill=context.skill,
            phase="doctor",
            artifact="prerequisite",
            path=context.skill_dir,
            next_command=doctor_retry,
        )
        for item in diagnostics
    ]
    envelope = _empty_envelope(context.skill)
    envelope.update(
        {
            "status": "blocked" if diagnostics else "ready",
            "next_action": "repair_prerequisites" if diagnostics else first_command,
            "next_command": (
                _next_command(context, first_command)
                if not diagnostics
                and (mode == "stateless" or context.run_dir is not None)
                and not any(item["required"] for item in required_inputs)
                else None
            ),
            "required_reads": [
                {"path": str(context.skill_dir / "SKILL.md"), "reason": "Read the skill workflow before starting."}
            ],
            "required_inputs": required_inputs,
            "allowed_writes": [],
            "forbidden_actions": ["write_installed_skill", "write_target_repository_during_doctor"],
            "blocking_reasons": [item["code"] for item in diagnostics],
            "diagnostics": diagnostics,
        }
    )
    return (EXIT_BLOCKED if diagnostics else EXIT_OK), envelope


def _build_argv(step: dict[str, Any], context: Context, run_dir: Path) -> list[str]:
    argv = [_expand(token, context, run_dir) for token in step["argv"]]
    for expansion in step["repeat"]:
        values = context.inputs.get(expansion["input"], [])
        if isinstance(values, str):
            values = [values]
        for value in values:
            argv.extend([expansion["flag"], value])
    if len(argv) > 1 and Path(argv[0]).resolve() == Path(sys.executable).resolve():
        script = Path(argv[1]).resolve()
        if not _within(script, context.skill_dir) or not script.is_file():
            raise ProtocolError(
                "command.script_unsafe",
                f"declared script is missing or outside the installed skill: {script}",
                "Repair the manifest script path.",
            )
    return argv


def _classification_argv(context: Context, run_dir: Path) -> list[str]:
    config = context.manifest["classification"]
    argv = [_expand(token, context, run_dir) for token in config["argv"]]
    for expansion in config["repeat"]:
        values = context.inputs.get(expansion["input"], [])
        if isinstance(values, str):
            values = [values]
        for value in values:
            argv.extend([expansion["flag"], value])
    return argv


def _classification_artifact_path(context: Context, run_dir: Path) -> Path:
    name = context.manifest["classification"]["artifact"]
    artifact = next(item for item in context.manifest["artifacts"] if item["name"] == name)
    return run_dir / artifact["path"]


def _classification_missing(context: Context) -> list[dict[str, Any]]:
    required = set(context.manifest["classification"]["required_inputs"])
    definitions = {item["name"]: item for item in context.manifest["inputs"]}
    return [
        {
            "name": definitions[name]["name"],
            "kind": definitions[name]["kind"],
            "required": True,
            "repeatable": definitions[name]["repeatable"],
            "description": definitions[name]["description"],
        }
        for name in sorted(required)
        if name not in context.inputs
    ]


def _run_initial_classification(
    context: Context,
    run_dir: Path,
) -> tuple[int, list[dict[str, Any]], list[str]]:
    argv = _classification_argv(context, run_dir)
    try:
        result = subprocess.run(
            argv,
            cwd=context.skill_dir,
            capture_output=True,
            text=True,
            shell=False,
            check=False,
        )
    except OSError as exc:
        diagnostic = _diagnostic(
            "classification.execution_failed",
            f"classifier could not start: {exc}",
            "Repair the installed classifier and restart.",
        )
        return EXIT_OPERATIONAL, [diagnostic], [diagnostic["code"]]
    if result.returncode:
        diagnostic = _diagnostic(
            "classification.failed",
            result.stderr.strip() or f"classifier exited {result.returncode}",
            "Repair the observable inputs and restart classification.",
        )
        return EXIT_BLOCKED, [diagnostic], [diagnostic["code"]]
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        diagnostic = _diagnostic(
            "classification.output_invalid",
            f"classifier did not return JSON: {exc}",
            "Repair the installed classifier and restart.",
        )
        return EXIT_OPERATIONAL, [diagnostic], [diagnostic["code"]]
    required = {"recommendation", "evidence", "confidence", "alternatives", "override_requirements"}
    if not isinstance(payload, dict) or set(payload) != required:
        diagnostic = _diagnostic(
            "classification.output_invalid",
            "classifier result does not match the required contract",
            "Repair the installed classifier and restart.",
        )
        return EXIT_OPERATIONAL, [diagnostic], [diagnostic["code"]]
    target = _classification_artifact_path(context, run_dir)
    _atomic_json(target, payload)
    return EXIT_OK, [], []


def _apply_classification(context: Context, state: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    assert context.run_dir is not None
    path = _classification_artifact_path(context, context.run_dir)
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        recommendation = result["recommendation"]
        recommended = recommendation["values"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ProtocolError(
            "classification.result_invalid",
            f"cannot apply classification: {exc}",
            "Restart the classified run.",
            EXIT_BLOCKED,
        ) from exc
    config = context.manifest["classification"]
    definitions = {item["name"]: item for item in context.manifest["inputs"]}
    conflicts: dict[str, Any] = {}
    for name in config["controlled_inputs"]:
        value = recommended.get(name)
        if name in context.inputs and context.inputs[name] != value:
            conflicts[name] = context.inputs[name]
    effective = dict(recommended)
    if recommendation.get("status") != "ready" and not conflicts:
        error = ProtocolError(
            "classification.product_input_required",
            "classification cannot proceed without concrete contrary evidence",
            "Provide a hash-bound classification_override artifact through the returned input.",
            EXIT_BLOCKED,
        )
        return error.exit_code, _phase_envelope(
            context,
            state["phase"],
            diagnostics=[_diagnostic(error.code, error.message, error.hint)],
            blocking_reasons=[error.code],
        )
    if conflicts:
        override_name = config["override_input"]
        override_value = context.inputs.get(override_name)
        if not isinstance(override_value, str):
            error = ProtocolError(
                "classification.override_required",
                "classification inputs differ from the recorded recommendation",
                "Provide a hash-bound override artifact with concrete contrary evidence.",
                EXIT_BLOCKED,
            )
            return error.exit_code, _phase_envelope(
                context,
                state["phase"],
                diagnostics=[_diagnostic(error.code, error.message, error.hint, details={"fields": sorted(conflicts)})],
                blocking_reasons=[error.code],
            )
        argv = [
            *_classification_argv(context, context.run_dir),
            "--classification",
            str(path),
            "--override-file",
            override_value,
            "--verify-override",
        ]
        verified = subprocess.run(
            argv,
            cwd=context.skill_dir,
            capture_output=True,
            text=True,
            shell=False,
            check=False,
        )
        if verified.returncode:
            error = ProtocolError(
                "classification.override_invalid",
                verified.stderr.strip() or "classification override was rejected",
                "Repair the hash-bound contrary evidence and retry.",
                EXIT_BLOCKED,
            )
            return error.exit_code, _phase_envelope(
                context,
                state["phase"],
                diagnostics=[_diagnostic(error.code, error.message, error.hint)],
                blocking_reasons=[error.code],
            )
        try:
            effective = json.loads(verified.stdout)
        except json.JSONDecodeError as exc:
            raise ProtocolError(
                "classification.override_invalid",
                f"override verifier returned invalid JSON: {exc}",
                "Repair the installed classifier.",
                EXIT_OPERATIONAL,
            ) from exc
        if any(effective.get(name) != value for name, value in conflicts.items()):
            error = ProtocolError(
                "classification.override_mismatch",
                "verified override values do not match the contrary CLI inputs",
                "Make the override artifact values exactly match the requested classification values.",
                EXIT_BLOCKED,
            )
            return error.exit_code, _phase_envelope(
                context,
                state["phase"],
                diagnostics=[_diagnostic(error.code, error.message, error.hint)],
                blocking_reasons=[error.code],
            )
    for name in config["controlled_inputs"]:
        value = effective.get(name)
        if value is None:
            continue
        definition = definitions[name]
        if definition["repeatable"] and not isinstance(value, list):
            value = [value]
        context.inputs[name] = value
    missing = _required_inputs(context.manifest, context.inputs, "start")
    required_missing = [item for item in missing if item["required"]]
    if required_missing:
        error = ProtocolError(
            "input.required",
            "missing required inputs: " + ", ".join(item["name"] for item in required_missing),
            "Pass every remaining workflow input to next.",
            EXIT_BLOCKED,
        )
        envelope = _phase_envelope(
            context,
            state["phase"],
            diagnostics=[_diagnostic(error.code, error.message, error.hint)],
            blocking_reasons=[error.code],
        )
        envelope["required_inputs"] = missing
        return error.exit_code, envelope
    command = _command_variant(context, "start")
    _write_state(context, state["phase"])
    exit_code, diagnostics, reasons = _run_command(context, "start", context.run_dir)
    if exit_code:
        return exit_code, _phase_envelope(
            context,
            state["phase"],
            diagnostics=diagnostics,
            blocking_reasons=reasons,
        )
    success_phase = command["success_phase"]
    _write_state(context, success_phase)
    return EXIT_OK, _phase_envelope(context, success_phase)


def _child_diagnostics(
    stdout: str,
    *,
    context: Context,
    command_name: str,
    argv: Sequence[str],
) -> list[dict[str, Any]]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    raw: object
    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, dict):
        raw = payload.get("diagnostics")
        if raw is None:
            raw = payload.get("errors")
        if raw is None:
            raw = payload.get("violations")
    else:
        raw = None
    if not isinstance(raw, list):
        return []
    diagnostics: list[dict[str, Any]] = []
    for item in raw:
        if not is_canonical(item):
            diagnostics.append(
                normalize_diagnostic(
                    {
                        "code": "adapter.diagnostic_contract_invalid",
                        "category": "contract_contradiction",
                        "message": "Wrapped validator returned a noncanonical diagnostic object.",
                        "hint": "Update the wrapped validator to emit every required repair-ready diagnostic field.",
                        "details": {"child_diagnostic": item},
                        "supporting_evidence": [json.dumps(item, sort_keys=True, default=str)],
                    },
                    skill=context.skill,
                    phase=command_name,
                    artifact=Path(argv[1]).name if len(argv) > 1 else "validator",
                    path=argv[1] if len(argv) > 1 else context.repo_root,
                    next_command=diagnostic_command(argv, context.repo_root),
                )
            )
            continue
        normalized = normalize_diagnostic(
                item,
                skill=context.skill,
                phase=command_name,
                artifact=Path(argv[1]).name if len(argv) > 1 else "validator",
                path=argv[1] if len(argv) > 1 else context.repo_root,
                next_command=diagnostic_command(argv, context.repo_root),
            )
        normalized.setdefault("hint", normalized["required_action"])
        normalized.setdefault("details", {})
        diagnostics.append(normalized)
    return diagnostics


def _run_command(
    context: Context,
    command_name: str,
    run_dir: Path,
) -> tuple[int, list[dict[str, Any]], list[str]]:
    command = _command_variant(context, command_name)
    for step in command["steps"]:
        argv = _build_argv(step, context, run_dir)
        result = subprocess.run(
            argv,
            cwd=context.repo_root,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode:
            diagnostics = (
                _child_diagnostics(
                    result.stdout,
                    context=context,
                    command_name=command_name,
                    argv=argv,
                )
                if step["diagnostics_json"]
                else []
            )
            if not diagnostics:
                message = result.stderr.strip() or result.stdout.strip() or f"child exited {result.returncode}"
                diagnostics = [
                    _diagnostic(
                        f"adapter.{command_name}_failed",
                        message,
                        "Use the diagnostic from the wrapped skill, repair the run, and retry.",
                        details={"returncode": result.returncode},
                        skill=context.skill,
                        phase=command_name,
                        artifact=Path(argv[1]).name if len(argv) > 1 else "validator",
                        path=argv[1] if len(argv) > 1 else context.repo_root,
                        next_command=diagnostic_command(argv, context.repo_root),
                        required_action=(
                            "Repair the reported artifact at the captured command path, "
                            "then run the exact next_command."
                        ),
                        valid_repairs=(
                            "Correct the local value named by the captured validator message.",
                            "Provide the missing local prerequisite named by the captured validator message.",
                        ),
                        supporting_evidence=(message, f"child return code: {result.returncode}"),
                    )
                ]
            exit_code = EXIT_BLOCKED if step["failure"] == "blocked" else EXIT_OPERATIONAL
            return exit_code, diagnostics, [item["code"] for item in diagnostics]
        capture = step["capture_stdout"]
        if capture is not None:
            artifact = next(item for item in context.manifest["artifacts"] if item["name"] == capture)
            target = (
                Path(_expand(artifact["path"], context, run_dir))
                if artifact.get("external", False)
                else run_dir / artifact["path"]
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            handle, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
            try:
                with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                    stream.write(result.stdout)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            except BaseException:
                Path(temporary).unlink(missing_ok=True)
                raise
    return EXIT_OK, [], []


def _start(context: Context) -> tuple[int, dict[str, Any]]:
    if context.run_dir is None:
        raise ProtocolError("path.run_dir_required", "--run-dir is required for start", "Pass a new run directory.")
    classification = context.manifest.get("classification")
    if classification is not None:
        missing = _classification_missing(context)
        if missing:
            error = ProtocolError(
                "input.required",
                "missing classification inputs: " + ", ".join(item["name"] for item in missing),
                "Pass every required classification input.",
            )
            envelope = _error_envelope(error, context.skill)
            envelope["required_inputs"] = missing
            return error.exit_code, envelope
        if context.run_dir.exists():
            raise ProtocolError(
                "state.run_exists",
                f"start requires a new run directory: {context.run_dir}",
                "Choose a path that does not exist, or use status for the existing run.",
            )
        parent = context.run_dir.parent
        if not parent.is_dir():
            raise ProtocolError(
                "path.run_parent_missing",
                f"run directory parent does not exist: {parent}",
                "Create or choose an existing parent directory.",
            )
        staging = Path(tempfile.mkdtemp(prefix=f".{context.run_dir.name}.", suffix=".staging", dir=parent))
        try:
            exit_code, diagnostics, reasons = _run_initial_classification(context, staging)
            if exit_code:
                shutil.rmtree(staging, ignore_errors=True)
                envelope = _empty_envelope(context.skill)
                envelope.update(
                    {
                        "status": "blocked" if exit_code == EXIT_BLOCKED else "error",
                        "blocking_reasons": reasons,
                        "diagnostics": diagnostics,
                        "required_inputs": missing,
                    }
                )
                return exit_code, envelope
            staging.rename(context.run_dir)
        except BaseException:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise
        phase = classification["phase"]
        _write_state(context, phase)
        return EXIT_OK, _phase_envelope(context, phase)
    missing = _required_inputs(context.manifest, context.inputs, "start")
    required_missing = [item for item in missing if item["required"]]
    if required_missing:
        error = ProtocolError(
            "input.required",
            "missing required inputs: " + ", ".join(item["name"] for item in required_missing),
            "Pass every required value with --input name=value.",
        )
        envelope = _error_envelope(error, context.skill)
        envelope["required_inputs"] = missing
        return error.exit_code, envelope
    command = _command_variant(context, "start")
    if context.run_dir.exists():
        raise ProtocolError(
            "state.run_exists",
            f"start requires a new run directory: {context.run_dir}",
            "Choose a path that does not exist, or use status for the existing run.",
        )
    parent = context.run_dir.parent
    if not parent.is_dir():
        raise ProtocolError(
            "path.run_parent_missing",
            f"run directory parent does not exist: {parent}",
            "Create or choose an existing parent directory.",
        )
    staging = Path(tempfile.mkdtemp(prefix=f".{context.run_dir.name}.", suffix=".staging", dir=parent))
    try:
        staging.rmdir()
        exit_code, diagnostics, reasons = _run_command(context, "start", staging)
        if exit_code:
            shutil.rmtree(staging, ignore_errors=True)
            envelope = _empty_envelope(context.skill)
            envelope.update(
                {
                    "status": "blocked" if exit_code == EXIT_BLOCKED else "error",
                    "blocking_reasons": reasons,
                    "diagnostics": diagnostics,
                    "required_inputs": _required_inputs(context.manifest, context.inputs, "start"),
                }
            )
            return exit_code, envelope
        staging.rename(context.run_dir)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    success_phase = command["success_phase"]
    _write_state(context, success_phase)
    return EXIT_OK, _phase_envelope(context, success_phase)


def _status(context: Context) -> tuple[int, dict[str, Any]]:
    if context.inputs:
        raise ProtocolError(
            "input.status_read_only",
            "status does not accept new inputs",
            "Pass late inputs to next, validate, or finalize.",
        )
    state = _load_state(context)
    _merge_state_inputs(context, state)
    return EXIT_OK, _phase_envelope(context, state["phase"])


def _transition(context: Context, command_name: str) -> tuple[int, dict[str, Any]]:
    state = _load_state(context)
    _merge_state_inputs(context, state)
    phase = state["phase"]
    missing = _required_inputs(context.manifest, context.inputs, command_name)
    required_missing = [item for item in missing if item["required"]]
    if required_missing:
        error = ProtocolError(
            "input.required",
            "missing required inputs: " + ", ".join(item["name"] for item in required_missing),
            "Pass every required value with --input name=value.",
            EXIT_BLOCKED,
        )
        envelope = _phase_envelope(
            context,
            phase,
            diagnostics=[_diagnostic(error.code, error.message, error.hint)],
            blocking_reasons=[error.code],
        )
        envelope["required_inputs"] = missing
        return error.exit_code, envelope
    command = _command_variant(context, "start")
    command = _command_variant(context, command_name)
    if phase not in command["allowed_phases"]:
        error = ProtocolError(
            "phase.command_forbidden",
            f"{command_name} is not allowed from phase {phase!r}",
            f"Follow next_action for phase {phase!r} before retrying.",
            EXIT_BLOCKED,
        )
        envelope = _phase_envelope(
            context,
            phase,
            diagnostics=[_diagnostic(error.code, error.message, error.hint)],
            blocking_reasons=[error.code],
        )
        return error.exit_code, envelope
    assert context.run_dir is not None
    _write_state(context, phase)
    exit_code, diagnostics, reasons = _run_command(context, command_name, context.run_dir)
    if exit_code:
        return exit_code, _phase_envelope(
            context,
            phase,
            diagnostics=diagnostics,
            blocking_reasons=reasons,
        )
    success_phase = command["success_phase"]
    _write_state(context, success_phase)
    return EXIT_OK, _phase_envelope(context, success_phase)


def _next(context: Context) -> tuple[int, dict[str, Any]]:
    state = _load_state(context)
    _merge_state_inputs(context, state)
    phase_name = state["phase"]
    classification = context.manifest.get("classification")
    if classification is not None and phase_name == classification["phase"]:
        return _apply_classification(context, state)
    next_command = context.manifest["phases"][phase_name]["next_command"]
    if next_command is None:
        return EXIT_OK, _phase_envelope(context, phase_name)
    return _transition(context, next_command)


def _run_stateless(context: Context, command_name: str = "run") -> tuple[int, dict[str, Any]]:
    if context.manifest.get("mode", "stateful") != "stateless":
        raise ProtocolError(
            "command.unsupported",
            f"{command_name} is not supported by stateful skill {context.skill}",
            "Use start for a stateful skill.",
            EXIT_BLOCKED,
        )
    if context.run_dir is not None:
        raise ProtocolError(
            "path.run_dir_forbidden",
            "stateless commands do not accept --run-dir",
            "Remove --run-dir and retry.",
        )
    rejected = sorted(
        item["name"]
        for item in context.manifest["inputs"]
        if item["name"] in context.inputs
        and item.get("accepted_for")
        and command_name not in item["accepted_for"]
    )
    if rejected:
        raise ProtocolError(
            "input.command_forbidden",
            f"inputs are not accepted by {command_name}: {', '.join(rejected)}",
            "Remove those inputs or pass them to their declared command.",
        )
    missing = _required_inputs(context.manifest, context.inputs, command_name)
    required_missing = [item for item in missing if item["required"]]
    if required_missing:
        error = ProtocolError(
            "input.required",
            "missing required inputs: " + ", ".join(item["name"] for item in required_missing),
            "Pass every required value with --input name=value.",
        )
        envelope = _error_envelope(error, context.skill)
        envelope["required_inputs"] = missing
        return error.exit_code, envelope
    command = _command_variant(context, command_name)
    result_payload: Any = None
    for step in command["steps"]:
        argv = _build_argv(step, context, context.repo_root)
        result = subprocess.run(
            argv,
            cwd=context.repo_root,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode:
            diagnostics = (
                _child_diagnostics(
                    result.stdout,
                    context=context,
                    command_name=command_name,
                    argv=argv,
                )
                if step["diagnostics_json"]
                else []
            )
            if diagnostics:
                envelope = _empty_envelope(context.skill)
                envelope.update(
                    {
                        "status": "blocked",
                        "phase": None,
                        "blocking_reasons": [item["code"] for item in diagnostics],
                        "diagnostics": diagnostics,
                    }
                )
                return (
                    EXIT_BLOCKED if step["failure"] == "blocked" else EXIT_OPERATIONAL,
                    envelope,
                )
            message = result.stderr.strip() or result.stdout.strip() or f"child exited {result.returncode}"
            error = ProtocolError(
                f"adapter.{command_name}_failed",
                message,
                "Repair the supplied inputs and retry.",
                EXIT_BLOCKED if step["failure"] == "blocked" else EXIT_OPERATIONAL,
            )
            return error.exit_code, _error_envelope(error, context.skill)
        if result.stdout.strip():
            try:
                result_payload = json.loads(result.stdout)
            except json.JSONDecodeError:
                result_payload = result.stdout.rstrip("\n")
    envelope = _empty_envelope(context.skill)
    envelope.update(
        {
            "status": "complete",
            "phase": "complete",
            "next_action": None,
            "required_inputs": _required_inputs(context.manifest, context.inputs, command_name),
            "allowed_writes": [
                str(Path(_expand(path, context, context.repo_root)).resolve())
                for path in command.get("allowed_writes", [])
            ],
            "artifacts": _artifact_list(context, context.repo_root),
            "forbidden_actions": (
                ["write_installed_skill", "write_target_repository_outside_allowed_writes"]
                if command.get("allowed_writes")
                else ["write_installed_skill", "write_target_repository"]
            ),
            "result": result_payload,
        }
    )
    return EXIT_OK, envelope


def _make_context(
    args: argparse.Namespace,
    output_format: str,
    cli_path: Path | None = None,
    *,
    manifest_relative_path: str = MANIFEST_FILE,
) -> Context:
    skill_dir = _canonical_dir(args.skill_dir, "skill_dir")
    repo_root = _canonical_dir(args.repo_root, "repo_root")
    skill_name = _read_skill_name(skill_dir)
    manifest, digest = _load_manifest(skill_dir, manifest_relative_path)
    if manifest["skill"] != skill_name or manifest["skill"] != skill_dir.name:
        raise ProtocolError(
            "skill.identity_mismatch",
            f"manifest, SKILL.md, and directory names must match: {manifest['skill']!r}, {skill_name!r}, {skill_dir.name!r}",
            "Pass the installed skill root and repair its manifest identity.",
        )
    run_dir = _safe_future_path(args.run_dir) if args.run_dir else None
    if run_dir and _within(run_dir, skill_dir):
        raise ProtocolError(
            "path.run_dir_in_skill",
            f"run directory must not be inside the installed skill: {run_dir}",
            "Choose external temporary or state storage.",
        )
    if run_dir and manifest["run_dir_policy"] == "outside_skill_and_repo" and _within(run_dir, repo_root):
        raise ProtocolError(
            "path.run_dir_in_repo",
            f"this skill forbids run state inside the target repository: {run_dir}",
            "Choose an external temporary or state directory.",
        )
    inputs = _parse_inputs(args.input, manifest)
    for artifact in manifest["artifacts"]:
        if artifact.get("external", False):
            for input_name in re.findall(r"\{input\.([A-Za-z][A-Za-z0-9_-]*)\}", artifact["path"]):
                value = inputs.get(input_name)
                if isinstance(value, str) and _within(Path(value), skill_dir):
                    raise ProtocolError(
                        "path.external_artifact_in_skill",
                        f"external artifact must not overwrite the installed skill: {value}",
                        "Choose an output path outside the installed skill.",
                    )
    return Context(
        cli_path=(cli_path or Path(__file__).resolve().parents[1] / "skill_cli.py").resolve(),
        skill_dir=skill_dir,
        repo_root=repo_root,
        run_dir=run_dir,
        manifest=manifest,
        manifest_digest=digest,
        inputs=inputs,
        output_format=output_format,
    )


def _parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--skill-dir", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--run-dir")
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--format", choices=("human", "json"), default="human")
    parser.add_argument("command")
    return parser


def _render(envelope: dict[str, Any], output_format: str, exit_code: int) -> None:
    if output_format == "json":
        sys.stdout.write(json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n")
        return
    phase = f" phase={envelope['phase']}" if envelope["phase"] else ""
    print(f"{envelope['skill']}: {envelope['status']}{phase}")
    if envelope["next_action"]:
        print(f"Next action: {envelope['next_action']}")
    stream = sys.stderr if exit_code else sys.stdout
    for item in envelope["diagnostics"]:
        print(f"{item['code']}: {item['message']} Fix: {item['hint']}", file=stream)


def main(
    argv: Sequence[str] | None = None,
    *,
    cli_path: Path | None = None,
    expected_skill_dir: Path | None = None,
    manifest_relative_path: str = MANIFEST_FILE,
) -> int:
    """Run one protocol command and convert all failures to the stable envelope."""
    raw = list(argv if argv is not None else sys.argv[1:])
    output_format = "json" if any(
        value == "--format=json" or (value == "--format" and index + 1 < len(raw) and raw[index + 1] == "json")
        for index, value in enumerate(raw)
    ) else "human"
    skill = "unknown"
    try:
        args = _parser().parse_args(raw)
        output_format = args.format
        if expected_skill_dir is not None:
            actual_skill_dir = _canonical_dir(args.skill_dir, "skill_dir")
            if actual_skill_dir != expected_skill_dir.resolve():
                raise ProtocolError(
                    "skill.adapter_mismatch",
                    f"skill-local adapter cannot run a different skill: {actual_skill_dir}",
                    f"Remove --skill-dir or pass {expected_skill_dir.resolve()}.",
                )
        context = _make_context(
            args,
            output_format,
            cli_path,
            manifest_relative_path=manifest_relative_path,
        )
        skill = context.skill
        mode = context.manifest.get("mode", "stateful")
        if mode == "stateless" and args.command != "doctor" and args.command not in context.manifest["commands"]:
            raise ProtocolError(
                "command.unsupported",
                f"{args.command} is not supported by stateless skill {context.skill}",
                "Use doctor or a command declared by the installed skill.",
                EXIT_BLOCKED,
            )
        if args.command in {"validate", "finalize"} and args.command not in context.manifest["commands"]:
            raise ProtocolError(
                "command.unsupported",
                f"{args.command} is not supported by {context.skill}",
                "Use the next_command returned by the current phase.",
                EXIT_BLOCKED,
            )
        handlers = {
            "doctor": _doctor,
            "start": _start,
            "status": _status,
            "next": _next,
            "validate": lambda value: _transition(value, "validate"),
            "finalize": lambda value: _transition(value, "finalize"),
        }
        if mode == "stateless" and args.command != "doctor":
            exit_code, envelope = _run_stateless(context, args.command)
        else:
            handler = handlers.get(args.command)
            if handler is None:
                raise ProtocolError(
                    "command.unsupported",
                    f"{args.command} is not supported by {context.skill}",
                    "Use a command declared by the installed skill.",
                    EXIT_BLOCKED,
                )
            exit_code, envelope = handler(context)
    except ProtocolError as exc:
        exit_code, envelope = exc.exit_code, _error_envelope(exc, skill)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        error = ProtocolError(
            "runtime.operational_error",
            str(exc) or exc.__class__.__name__,
            "Inspect the paths and wrapped skill command, then retry.",
            EXIT_OPERATIONAL,
        )
        exit_code, envelope = error.exit_code, _error_envelope(error, skill)
    except Exception as exc:  # pragma: no cover - defensive public boundary
        error = ProtocolError(
            "runtime.internal_error",
            str(exc) or exc.__class__.__name__,
            "Report this protocol runtime failure with the command and diagnostic code.",
            EXIT_INTERNAL,
        )
        exit_code, envelope = error.exit_code, _error_envelope(error, skill)
    _render(envelope, output_format, exit_code)
    return exit_code

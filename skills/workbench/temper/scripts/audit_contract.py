"""Bundle rules, rendering, receipt, and sealed-audit parsing for Temper."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from pathlib import Path
from typing import Any

from _skill_protocol_runtime import compatible_version, compatible_version_pattern

CONTRACT_VERSION = "1.0.0"
RECEIPT_MARKER = "test-audit"
DATA_MARKER = "<!-- test-audit-data -->"
KINDS: dict[str, dict[str, str]] = {
    "redundant": {"candidate": "killed", "guard": "killed"},
    "vacuous": {"candidate": "survived", "guard": "killed"},
    "gap": {"guard": "survived", "witness": "killed"},
    "rework": {"candidate": "killed"},
}
ROLES: dict[str, tuple[str, ...]] = {
    "redundant": ("candidate", "guard"),
    "vacuous": ("candidate", "guard"),
    "rework": ("candidate", "guard"),
    "gap": ("guard", "witness"),
}


def claims_of(finding: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return the (role, selection, outcome) a finding claims for each of its mutants.

    A gap also claims that the whole suite lets its mutants survive, unless its guard already is the suite.
    """
    rows = [(role, finding[role], outcome) for role, outcome in KINDS[finding["kind"]].items()]
    if finding["kind"] == "gap" and finding["guard"] != "suite":
        rows.append(("suite", "suite", "survived"))
    return rows


RESERVED_RE = re.compile(r"^#{1,6}\s|<!--", re.MULTILINE)
TOP_FIELDS = {"schema_version", "title", "summary", "budget", "copy_git", "copy_exclude", "selections", "mutants", "findings"}
SELECTION_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
MUTANT_RE = re.compile(r"^M[1-9][0-9]*$")


def _scalar(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _title_error(value: object) -> str | None:
    if not _nonempty(value) or not isinstance(value, str):
        return "must be a non-empty string; write a short title"
    if "\n" in value or "\r" in value or "<!--" in value:
        return "must be one line without '<!--'; shorten it"
    return None


def _prose_error(value: object) -> str | None:
    if not _nonempty(value) or not isinstance(value, str):
        return "must be a non-empty string; write the text"
    if RESERVED_RE.search(value):
        return "must not contain a Markdown heading line or '<!--'; reword it"
    return None


def _safe_relative(value: object) -> bool:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        return False
    if re.match(r"^[A-Za-z]:", value):
        return False
    return all(part not in ("", ".", "..") for part in value.split("/"))


def validate_bundle(bundle: object, repo_root: Path) -> list[str]:
    """Return every bundle defect as '<field path>: <defect and repair>'."""
    errors: list[str] = []
    if not isinstance(bundle, dict):
        return ["bundle: must be a JSON object; use the bundle template"]
    keys = set(bundle)
    if keys != TOP_FIELDS:
        missing = sorted(TOP_FIELDS - keys)
        extra = sorted(keys - TOP_FIELDS)
        errors.append(f"bundle: fields must be exactly {sorted(TOP_FIELDS)}; missing {missing}, unexpected {extra}")
    if "schema_version" in bundle and not compatible_version(bundle["schema_version"], CONTRACT_VERSION):
        errors.append(f"schema_version: must be a {CONTRACT_VERSION.split('.')[0]}.x.y string; use the template's value")
    for name, check in (("title", _title_error), ("summary", _prose_error)):
        if name in bundle:
            defect = check(bundle[name])
            if defect:
                errors.append(f"{name}: {defect}")
    if "budget" in bundle:
        budget = bundle["budget"]
        if not isinstance(budget, dict) or set(budget) != {"seconds", "kind", "basis"}:
            errors.append("budget: must be an object with exactly seconds, kind, and basis")
        else:
            seconds = budget["seconds"]
            if seconds is not None and (isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not seconds > 0):
                errors.append("budget.seconds: must be null or a number greater than 0")
            if budget["kind"] not in ("local", "ci"):
                errors.append("budget.kind: must be 'local' or 'ci'")
            if not _nonempty(budget["basis"]):
                errors.append("budget.basis: must be a non-empty string quoting the user's words")
    if "copy_git" in bundle and not isinstance(bundle["copy_git"], bool):
        errors.append("copy_git: must be true or false")
    if "copy_exclude" in bundle:
        excluded = bundle["copy_exclude"]
        if not isinstance(excluded, list):
            errors.append("copy_exclude: must be a list of relative paths")
        else:
            seen: set[str] = set()
            for index, entry in enumerate(excluded):
                if not _safe_relative(entry):
                    errors.append(f"copy_exclude[{index}]: must be a safe relative POSIX path")
                elif entry in seen:
                    errors.append(f"copy_exclude[{index}]: duplicate path {entry}; list it once")
                else:
                    seen.add(entry)

    selections = bundle.get("selections")
    valid_selections: dict[str, dict[str, Any]] = {}
    if "selections" in bundle:
        if not isinstance(selections, dict) or "suite" not in selections:
            errors.append("selections: must be an object containing 'suite'")
        if isinstance(selections, dict):
            argv_owner: dict[tuple[str, ...], str] = {}
            for name, value in selections.items():
                where = f"selections.{name}"
                if not isinstance(name, str) or not SELECTION_RE.match(name):
                    errors.append(f"{where}: name must match {SELECTION_RE.pattern}")
                    continue
                if not isinstance(value, dict) or set(value) != {"argv", "timeout_seconds"}:
                    errors.append(f"{where}: must be an object with exactly argv and timeout_seconds")
                    continue
                argv = value["argv"]
                ok = True
                if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
                    errors.append(f"{where}.argv: must be a non-empty list of non-empty strings")
                    ok = False
                timeout = value["timeout_seconds"]
                if not _is_int(timeout) or not 1 <= timeout <= 86400:
                    errors.append(f"{where}.timeout_seconds: must be an integer from 1 to 86400")
                    ok = False
                if not ok:
                    continue
                key = tuple(argv)
                if key in argv_owner:
                    errors.append(f"{where}.argv: equals selections.{argv_owner[key]}.argv; give each selection a distinct command")
                else:
                    argv_owner[key] = name
                valid_selections[name] = value

    mutants = bundle.get("mutants")
    valid_mutants: dict[str, dict[str, Any]] = {}
    if "mutants" in bundle:
        if not isinstance(mutants, dict):
            errors.append("mutants: must be an object keyed M1, M2, ...")
        else:
            root = repo_root.resolve()
            for mid, value in mutants.items():
                where = f"mutants.{mid}"
                if not isinstance(mid, str) or not MUTANT_RE.match(mid):
                    errors.append(f"{where}: id must match {MUTANT_RE.pattern}")
                    continue
                if not isinstance(value, dict) or set(value) != {"path", "old", "new", "behavior"}:
                    errors.append(f"{where}: must be an object with exactly path, old, new, behavior")
                    continue
                path = value["path"]
                if not _safe_relative(path) or path.split("/")[0] in (".git", ".first-four-hours"):
                    errors.append(f"{where}.path: {path!r} must be a safe relative path outside .git and .first-four-hours")
                    continue
                target = root / path
                try:
                    is_regular = target.is_file() and not target.is_symlink() and target.resolve() == root / path
                except OSError:
                    is_regular = False
                if not is_regular:
                    errors.append(f"{where}.path: {path} must be a regular file inside the repository, not a link or through a linked directory")
                    continue
                old, new = value["old"], value["new"]
                if not isinstance(old, str) or not old or not isinstance(new, str):
                    errors.append(f"{where}: old must be a non-empty string and new a string")
                    continue
                if new == old:
                    errors.append(f"{where}.new: must differ from old")
                    continue
                if not _nonempty(value["behavior"]):
                    errors.append(f"{where}.behavior: must be a non-empty string naming the behavior changed")
                    continue
                try:
                    text = target.read_bytes().decode("utf-8")
                except (OSError, UnicodeDecodeError):
                    errors.append(f"{where}.path: {path} must be a readable UTF-8 file")
                    continue
                if text.count(old) != 1:
                    errors.append(f"{where}.old: text must occur exactly once in {path}; found {text.count(old)}")
                    continue
                valid_mutants[mid] = value

    findings = bundle.get("findings")
    used_selections: set[str] = set()
    used_mutants: set[str] = set()
    claims: dict[tuple[str, str], tuple[str, int]] = {}
    removal_candidates: dict[str, int] = {}
    parsed: list[tuple[int, dict[str, Any]]] = []
    if "findings" in bundle:
        if not isinstance(findings, list):
            errors.append("findings: must be a list")
        else:
            for number, finding in enumerate(findings, 1):
                where = f"findings[{number - 1}]"
                if not isinstance(finding, dict) or finding.get("kind") not in KINDS:
                    errors.append(f"{where}.kind: must be one of {sorted(KINDS)}")
                    continue
                kind = finding["kind"]
                expected = {"kind", "title", "tests", "rationale", "mutants", *ROLES[kind]}
                if set(finding) != expected:
                    errors.append(f"{where}: a {kind} finding has exactly the fields {sorted(expected)}")
                    continue
                defect = _title_error(finding["title"])
                if defect:
                    errors.append(f"{where}.title: {defect}")
                defect = _prose_error(finding["rationale"])
                if defect:
                    errors.append(f"{where}.rationale: {defect}")
                tests = finding["tests"]
                if not isinstance(tests, list) or not all(_nonempty(t) for t in tests) or (not tests and kind != "gap"):
                    errors.append(f"{where}.tests: must be a list of non-empty strings, non-empty unless kind is gap")
                ids = finding["mutants"]
                ids_ok = isinstance(ids, list) and all(isinstance(i, str) for i in ids) and len(set(ids)) == len(ids)
                if not ids_ok or (not ids and kind != "rework"):
                    errors.append(f"{where}.mutants: must be a list of unique mutant ids, non-empty unless kind is rework")
                    ids_ok = False
                elif mutants is not None and isinstance(mutants, dict):
                    for mid in ids:
                        if mid not in mutants:
                            errors.append(f"{where}.mutants: {mid} is not declared in mutants")
                            ids_ok = False
                roles_ok = True
                for role in ROLES[kind]:
                    name = finding[role]
                    if not isinstance(name, str) or (isinstance(selections, dict) and name not in selections):
                        errors.append(f"{where}.{role}: must name a declared selection")
                        roles_ok = False
                if roles_ok:
                    names = [finding[role] for role in ROLES[kind]]
                    if len(set(names)) != len(names):
                        errors.append(f"{where}: the roles {list(ROLES[kind])} must name different selections")
                        roles_ok = False
                if roles_ok:
                    used_selections.update(finding[role] for role in ROLES[kind])
                    if kind in ("redundant", "vacuous"):
                        removal_candidates.setdefault(finding["candidate"], number)
                if ids_ok:
                    used_mutants.update(ids)
                if roles_ok and ids_ok:
                    parsed.append((number, finding))
            for number, finding in parsed:
                kind = finding["kind"]
                if kind in ("redundant", "vacuous"):
                    guard = finding["guard"]
                    if guard == "suite":
                        errors.append(f"findings[{number - 1}].guard: must not be 'suite'; name the tests that stay")
                    elif guard in removal_candidates:
                        errors.append(
                            f"findings[{number - 1}].guard: `{guard}` is the candidate of finding {removal_candidates[guard]}; "
                            f"carrying out both would delete finding {number}'s guard"
                        )
                for mid in finding["mutants"]:
                    for _role, name, outcome in claims_of(finding):
                        key = (mid, name)
                        prior = claims.get(key)
                        if prior is None:
                            claims[key] = (outcome, number)
                        elif prior[0] != outcome:
                            errors.append(
                                f"findings[{number - 1}]: expects mutant {mid} {outcome} by `{name}`, "
                                f"but finding {prior[1]} expects it {prior[0]}"
                            )
    if isinstance(selections, dict) and isinstance(findings, list) and not errors:
        for name in selections:
            if name != "suite" and name not in used_selections:
                errors.append(f"selections.{name}: no finding uses it; remove it or add a finding")
    if isinstance(mutants, dict) and isinstance(findings, list) and not errors:
        for mid in mutants:
            if mid not in used_mutants:
                errors.append(f"mutants.{mid}: no finding uses it; remove it or add a finding")
    return errors


def expectations(bundle: dict[str, Any]) -> dict[tuple[str, str], str]:
    """Map each (mutant id, selection name) to its expected outcome."""
    result: dict[tuple[str, str], str] = {}
    for finding in bundle["findings"]:
        for mid in finding["mutants"]:
            for _role, name, outcome in claims_of(finding):
                result[(mid, name)] = outcome
    return result


def receipt_line(digest: str) -> str:
    return f"<!-- {RECEIPT_MARKER}: {CONTRACT_VERSION}; sha256: {digest} -->"


def _seconds(value: float) -> str:
    return f"{value:.1f}"


def render(bundle: dict[str, Any], results: dict[str, Any], verify_argv: list[str]) -> str:
    """Render the sealed Markdown view with its data line and receipt."""
    budget = bundle["budget"]
    if budget["seconds"] is None:
        target = "- Target: none set"
    else:
        label = "local suite time" if budget["kind"] == "local" else "CI time"
        target = f"- Target: {budget['seconds']} seconds of {label}"
    lines = [
        f"# Test Audit: {bundle['title']}",
        "",
        bundle["summary"],
        "",
        "## Budget",
        "",
        target,
        f"- Basis: {_scalar(budget['basis'])}",
        f"- Baseline: `suite` passed in {_seconds(results['baseline']['suite'])} seconds",
        "",
        "## Selections",
        "",
    ]
    for name in sorted(bundle["selections"]):
        selection = bundle["selections"][name]
        lines.append(
            f"- `{name}`: `{_scalar(selection['argv'])}` passed unmutated in "
            f"{_seconds(results['baseline'][name])} seconds (timeout {selection['timeout_seconds']} seconds)"
        )
    lines.append("")
    findings = bundle["findings"]
    if not findings:
        lines += ["## Findings", "", "No findings.", ""]
    observed = {(o["mutant"], o["selection"]): o["observed"] for o in results["outcomes"]}
    for number, finding in enumerate(findings, 1):
        kind = finding["kind"]
        lines += [
            f"## Finding {number}",
            "",
            f"- Kind: `{kind}`",
            f"- Title: {_scalar(finding['title'])}",
            f"- Tests: {_scalar(finding['tests'])}",
        ]
        for role in ROLES[kind]:
            lines.append(f"- {role.capitalize()}: `{finding[role]}`")
        lines += ["", finding["rationale"], ""]
        if finding["mutants"]:
            lines += ["### Mutants", ""]
            for mid in finding["mutants"]:
                mutant = bundle["mutants"][mid]
                roles = ", ".join(f"{role} `{name}` {observed[(mid, name)]}" for role, name, _outcome in claims_of(finding))
                lines.append(
                    f"- `{mid}` in `{mutant['path']}`, {_scalar(mutant['behavior'])}: "
                    f"{_scalar(mutant['old'])} → {_scalar(mutant['new'])}; {roles}"
                )
            lines.append("")
    lines += [
        "## Verify",
        "",
        f"After the change, run `{shlex.join(verify_argv)}` with `item` set to the finding numbers the plan carries out.",
        "",
        DATA_MARKER,
        _scalar({"bundle": bundle, "results": results}),
    ]
    body = "\n".join(lines) + "\n"
    return body + receipt_line(hashlib.sha256(body.encode("utf-8")).hexdigest()) + "\n"


def read_sealed(text: str) -> dict[str, Any]:
    """Return the parsed {'bundle', 'results'} of a sealed audit or raise ValueError."""
    stripped = text[:-1] if text.endswith("\n") else text
    cut = stripped.rfind("\n")
    last = stripped[cut + 1 :]
    body = stripped[: cut + 1]
    pattern = rf"^<!-- {RECEIPT_MARKER}: {compatible_version_pattern(CONTRACT_VERSION)}; sha256: (?P<sha256>[0-9a-f]{{64}}) -->$"
    match = re.match(pattern, last)
    if match is None or cut < 0:
        raise ValueError("test-audit receipt is missing or malformed; reseal with Temper")
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != match.group("sha256"):
        raise ValueError("test-audit receipt does not match its content; reseal with Temper")
    body_lines = body.split("\n")
    marks = [i for i, line in enumerate(body_lines) if line == DATA_MARKER]
    if len(marks) != 1 or marks[0] + 1 >= len(body_lines):
        raise ValueError("test-audit data marker must appear exactly once; reseal with Temper")
    try:
        data = json.loads(body_lines[marks[0] + 1])
    except ValueError:
        data = None
    if not isinstance(data, dict) or "bundle" not in data or "results" not in data:
        raise ValueError("test-audit data line must be a JSON object with bundle and results; reseal with Temper")
    return {"bundle": data["bundle"], "results": data["results"]}


def select_findings(count: int, item: str | None) -> list[int]:
    """Return all finding numbers 1..count, or the sorted comma-separated selection."""
    if item is None:
        return list(range(1, count + 1))
    chosen: list[int] = []
    for piece in item.split(","):
        text = piece.strip()
        if not text.isdecimal() or not 1 <= int(text) <= count:
            raise ValueError(f"item piece {text!r} must be a finding number from 1 to {count}")
        number = int(text)
        if number in chosen:
            raise ValueError(f"item piece {text!r} is repeated; name each finding once")
        chosen.append(number)
    return sorted(chosen)

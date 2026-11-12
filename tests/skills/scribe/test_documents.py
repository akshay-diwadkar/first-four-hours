from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from bundle_workspace import WorkspaceError, prepare_workspace
from check_document import _validate, load_bundle, validate_document, validate_sources
from check_document_language import collect_diagnostics

from tools.validation.git_test_support import seed_git
from tools.validation.python_test_support import run_python

CLI = Path(__file__).resolve().parents[3] / "skills" / "sensemaking" / "scribe" / "scripts" / "cli.py"
FACT = "The service starts with port 8080."


def cli(repo: Path, command: str, **inputs: str) -> tuple[int, dict[str, Any]]:
    argv = [sys.executable, str(CLI), "--repo-root", str(repo)]
    for name, value in inputs.items():
        argv += ["--input", f"{name}={value}"]
    result = run_python([*argv, "--format", "json", command], capture_output=True, text=True, check=False)
    return result.returncode, json.loads(result.stdout)


def source_types(bundle: dict[str, Any], repo: Path, bundle_path: Path) -> set[str]:
    return {item["type"] for item in validate_sources(bundle, repo, bundle_path)}


def snapshot(*paths: Path) -> dict[Path, tuple[bytes, int]]:
    return {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}


def write_bundle(directory: Path, bundle: dict[str, Any]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "document-bundle.json"
    path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    return path


def with_fact(bundle: dict[str, Any]) -> dict[str, Any]:
    for document in bundle["documents"]:
        document["required_facts"] = [{"id": "FACT-1", "claim": FACT, "source_ids": ["SRC-1"]}]
    return bundle


def add_fact(document: Path) -> None:
    document.write_text(document.read_text(encoding="utf-8") + "\n" + FACT + "\n", encoding="utf-8")


def git_status(repo: Path, *flags: str) -> str:
    command = ["git", "status", "--porcelain", "--untracked-files=all", *flags]
    return subprocess.run(command, cwd=repo, capture_output=True, text=True, check=True).stdout


def codes(payload: dict[str, Any]) -> list[str]:
    return [item["code"] for item in payload["diagnostics"]]


def link_directory(target: Path, link: Path) -> None:
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


def test_write_checks_every_listed_document_without_writing(document_case: tuple[Path, Path, dict[str, Any]]) -> None:
    repo, documents, bundle = document_case
    runbook, reference = documents / "runbook.md", documents / "reference.md"
    # Source validation on the untouched bundle: stale hashes, audit-namespace sources, and undeclared sources.
    temp_bundle = repo.parent / "temp" / "document-bundle.json"
    assert source_types(bundle, repo, temp_bundle) == set()
    assert validate_document(runbook.read_text(encoding="utf-8"), bundle["documents"][0]) == []
    stale = copy.deepcopy(bundle)
    stale["sources"][0]["sha256"] = "0" * 64
    assert "source_hash_mismatch" in source_types(stale, repo, temp_bundle)
    report = copy.deepcopy(bundle)
    report["sources"].append(
        {"id": "SRC-2", "path": ".first-four-hours/scribes/runbook/scribe-audit.md", "sha256": "0" * 64, "authority": "audit report"}
    )
    assert "namespace_source" in source_types(report, repo, temp_bundle)
    undeclared = copy.deepcopy(bundle)
    undeclared["documents"][1]["required_facts"] = [
        {"id": "FACT-1", "claim": "Run the service.", "source_ids": ["SRC-1", "SRC-9"]}
    ]
    undeclared["documents"][1]["integrity_literals"] = [
        {"id": "LIT-1", "kind": "value", "literal": "service", "source_ids": ["SRC-1"]}
    ]
    errors = validate_sources(undeclared, repo, temp_bundle)
    assert [(item["type"], item["location"]) for item in errors] == [("undeclared_source", "source SRC-9")]
    # A schema-valid populated glossary loads unchanged.
    populated = copy.deepcopy(bundle)
    populated["glossary"] = {
        "terms": [
            {
                "preferred": "service",
                "meaning": "the process the runbook manages",
                "forbidden": ["daemon", "server process"],
            }
        ],
        "abbreviations": {
            "API": "application programming interface",
            "TLS-1": "transport layer security version one",
        },
        "action_verbs": ["run", "stop"],
        "phrasal_verbs": ["set up", "shut down"],
        "hazardous_actions": ["purge", "delete"],
    }
    assert load_bundle(write_bundle(repo.parent / "glossary", populated)) == populated
    invalid = copy.deepcopy(bundle)
    invalid["documents"][0]["required_facts"] = "none"
    del invalid["sources"][0]["authority"]
    invalid["documents"][1]["owner"] = "x"
    invalid["glossary"]["abbreviations"] = {"API": "", "api": "x"}
    invalid["sources"][0]["sha256"] = "XYZ"
    invalid["documents"][0]["procedures"] = [{"id": "PROC-1", "ordered_markers": ["one"]}]
    invalid["documents"][1]["profile"] = "loose"
    invalid["glossary"]["action_verbs"] = ["run", "run"]
    invalid["sources"][0]["path"] = 5
    invalid["glossary"]["terms"] = ["word"]
    with pytest.raises(ValueError) as rejected:
        load_bundle(write_bundle(repo.parent / "invalid", invalid))
    assert [part.split(": ", 1)[0] for part in str(rejected.value).split("; ")] == [
        "documents.0.procedures.0.ordered_markers",
        "documents.0.required_facts",
        "documents.1",
        "documents.1.profile",
        "glossary.abbreviations",
        "glossary.abbreviations.API",
        "glossary.action_verbs",
        "glossary.terms.0",
        "sources.0",
        "sources.0.path",
        "sources.0.sha256",
    ]
    with pytest.raises(ValueError, match="unsupported keyword 'maxLength'"):
        _validate({"type": "string", "maxLength": 3}, "x", [], [])
    with pytest.raises(ValueError, match="unsupported keyword 'minLength'"):
        _validate({"type": "object", "propertyNames": {"pattern": "^a$", "minLength": 1}}, {"a": "x"}, [], [])
    with pytest.raises(ValueError, match="unsupported type 'integer'"):
        _validate({"type": "integer"}, 1, [], [])

    bundle_path = write_bundle(repo.parent / "temp", with_fact(bundle))
    status = git_status(repo, "--ignored")
    before = snapshot(runbook, reference, bundle_path)

    code, blocked = cli(repo, "write", bundle=str(bundle_path))
    assert code == 3, blocked
    missing = [item for item in blocked["diagnostics"] if item["code"] == "missing_required_fact"]
    assert sorted(Path(item["document"]) for item in missing) == sorted([runbook.resolve(), reference.resolve()])
    assert missing[0]["required_action"] and missing[0]["valid_repairs"]
    assert snapshot(runbook, reference, bundle_path) == before

    # One repaired document is not enough: write completes only when every listed document passes.
    add_fact(runbook)
    code, partial = cli(repo, "write", bundle=str(bundle_path))
    assert code == 3, partial
    assert [Path(item["document"]) for item in partial["diagnostics"]] == [reference.resolve()]

    add_fact(reference)
    repaired = snapshot(runbook, reference, bundle_path)
    code, complete = cli(repo, "write", bundle=str(bundle_path))
    assert code == 0, complete
    assert complete["result"]["status"] == "complete"
    assert complete["result"]["documents"] == [
        {"path": str(path.resolve()), "document_sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in (runbook, reference)
    ]
    assert snapshot(runbook, reference, bundle_path) == repaired
    assert git_status(repo, "--ignored") == status
    assert not (repo / ".first-four-hours").exists()

    # The same passing bundle is refused inside the repository.
    code, inside = cli(repo, "write", bundle=str(write_bundle(repo / "notes", bundle)))
    assert code == 3, inside
    assert codes(inside) == ["bundle_in_repository"]
    # A document inside the audit namespace is refused before anything reads it.
    namespaced = json.loads(bundle_path.read_text(encoding="utf-8"))
    namespaced["documents"][0]["path"] = str(repo / ".first-four-hours" / "scribes" / "runbook" / "runbook.md")
    code, misplaced = cli(repo, "write", bundle=str(write_bundle(repo.parent / "namespaced", namespaced)))
    assert code == 3, misplaced
    assert codes(misplaced) == ["namespace_document"]
    assert not (repo / ".first-four-hours").exists()

    # A finding whose message cites another file still names the document it was found in.
    cited = json.loads(bundle_path.read_text(encoding="utf-8"))
    cited["documents"][0]["integrity_literals"] = [
        {"id": "LIT-1", "kind": "path", "literal": "deploy/worker.yaml", "source_ids": ["SRC-1"]}
    ]
    code, attributed = cli(repo, "write", bundle=str(write_bundle(repo.parent / "cited", cited)))
    assert code == 3, attributed
    assert [(item["code"], Path(item["document"])) for item in attributed["diagnostics"]] == [
        ("missing_path", runbook.resolve())
    ]

    # Pasted evidence beside the bundle, a non-Markdown document, and gap markers.
    evidence = repo.parent / "evidence"
    evidence.mkdir()
    pasted = evidence / "pasted.txt"
    pasted.write_text("Drain for 30 seconds.\n", encoding="utf-8")
    errors_doc = documents / "errors.py"
    errors_doc.write_text('MESSAGE = "Drain for 30 seconds. Check it in the LOG."\n', encoding="utf-8")
    gapped = documents / "gapped.md"
    gapped.write_text(
        "# Procedure\n\nRun the service.\n\nSet the drain timeout. [GAP: safe drain timeout; owner: operations lead]\n"
        "Write a gap as `[GAP: <missing fact>; owner: <next owner>]`.\n",
        encoding="utf-8",
    )
    captured = json.loads(bundle_path.read_text(encoding="utf-8"))
    captured["sources"].append(
        {
            "id": "SRC-2",
            "path": str(pasted.resolve()),
            "sha256": hashlib.sha256(pasted.read_bytes()).hexdigest(),
            "authority": "pasted by the user",
        }
    )
    captured["documents"] += [
        {
            "path": str(errors_doc),
            "profile": "strict",
            "required_facts": [{"id": "FACT-1", "claim": "Drain for 30 seconds.", "source_ids": ["SRC-2"]}],
        },
        {"path": str(gapped), "profile": "strict"},
    ]
    evidence_bundle = write_bundle(evidence, captured)
    assert validate_sources(captured, repo, evidence_bundle) == []
    code, open_gaps = cli(repo, "write", bundle=str(evidence_bundle))
    assert code == 0, open_gaps
    assert open_gaps["result"]["status"] == "incomplete"
    assert open_gaps["result"]["gaps"] == [
        {"document": str(gapped.resolve()), "line": 5, "missing": "safe drain timeout", "owner": "operations lead"}
    ]
    assert len(open_gaps["result"]["documents"]) == 4
    assert str(errors_doc.resolve()) in [item["path"] for item in open_gaps["result"]["documents"]]

    gapped.write_text(
        gapped.read_text(encoding="utf-8").replace("[GAP: safe drain timeout; owner: operations lead]", "[GAP: safe drain timeout]"),
        encoding="utf-8",
    )
    errors_doc.write_text('MESSAGE = "Drain later."\n', encoding="utf-8")
    code, unmarked = cli(repo, "write", bundle=str(evidence_bundle))
    assert code == 3, unmarked
    assert "malformed_gap" in codes(unmarked)
    assert any(
        item["code"] == "missing_required_fact" and Path(item["document"]) == errors_doc.resolve()
        for item in unmarked["diagnostics"]
    )

    for replacement, checked_bundle in (
        (str(runbook.resolve()), evidence_bundle),
        (str(evidence_bundle.resolve()), evidence_bundle),
        (str((repo / "source.txt").resolve()), repo.parent / "document-bundle.json"),
    ):
        unsafe = copy.deepcopy(captured)
        unsafe["sources"][1]["path"] = replacement
        unsafe["sources"][1]["sha256"] = hashlib.sha256(Path(replacement).read_bytes()).hexdigest()
        assert "unsafe_source_path" in source_types(unsafe, repo, checked_bundle)

    bundle_path.write_text("[" * 50000 + "]" * 50000, encoding="utf-8")
    code, malformed = cli(repo, "write", bundle=str(bundle_path))
    assert code == 3, malformed
    assert codes(malformed) == ["invalid_input"]

    if os.name == "nt":
        with pytest.raises(WorkspaceError) as reserved:
            prepare_workspace(repo, "nul")
        assert reserved.value.code == "invalid_slug"
    with pytest.raises(WorkspaceError, match="choose a shorter or different slug") as long_slug:
        prepare_workspace(repo, "a" * 300)
    assert long_slug.value.code == "invalid_slug"
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as key:
                long_paths = bool(winreg.QueryValueEx(key, "LongPathsEnabled")[0])
        except OSError:
            long_paths = False
        fitting = 245 - len(str(repo.resolve() / ".first-four-hours" / "scribes")) - 1
        if not long_paths and fitting > 0:
            with pytest.raises(WorkspaceError, match="choose a shorter or different slug") as unusable_report:
                prepare_workspace(repo, "c" * fitting)
            assert unusable_report.value.code == "invalid_slug"
    (repo / "sub").mkdir()
    with pytest.raises(WorkspaceError, match="Git worktree root"):
        prepare_workspace(repo / "sub", "runbook")
    tracked = repo.parent / "tracked"
    seed_git(tracked, {".first-four-hours/scribes/notes.md": "tracked\n"})
    with pytest.raises(WorkspaceError, match="tracked project files"):
        prepare_workspace(tracked, "runbook")
    exclude = repo / ".git" / "info" / "exclude"
    exclude.unlink()
    exclude.mkdir()
    with pytest.raises(WorkspaceError, match="linked or not a regular file"):
        prepare_workspace(repo, "runbook")
    exclude.rmdir()
    exclude.write_text("", encoding="utf-8")
    moved_info = repo.parent / "info-target"
    exclude.parent.rename(moved_info)
    link_directory(moved_info, exclude.parent)
    with pytest.raises(WorkspaceError, match="linked or not a regular file"):
        prepare_workspace(repo, "runbook")


def test_audit_writes_one_report_for_every_listed_document(document_case: tuple[Path, Path, dict[str, Any]]) -> None:
    repo, documents, bundle = document_case
    runbook, reference = documents / "runbook.md", documents / "reference.md"
    add_fact(runbook)
    reference.write_text(
        reference.read_text(encoding="utf-8") + "\n[GAP: restart timeout; owner: operations lead]\n", encoding="utf-8"
    )
    with_fact(bundle)["documents"][1]["reader_findings"] = [
        {
            "location": "Procedure",
            "issue": "No expected result follows the step.",
            "consequence": "The reader cannot tell whether the service started.",
        }
    ]
    bundle_path = write_bundle(repo.parent / "temp", bundle)
    exclude = repo / ".git" / "info" / "exclude"
    seeded = b"# caf\xe9\r\n*.tmp"
    exclude.write_bytes(seeded)
    inputs = [runbook, reference, bundle_path, repo / "source.txt"]
    before = snapshot(*inputs)

    code, audited = cli(repo, "audit", bundle=str(bundle_path), slug="Runbook Audit")
    assert code == 0, audited
    result = audited["result"]
    report_path = repo / ".first-four-hours" / "scribes" / "runbook-audit" / "scribe-audit.md"
    assert Path(result["audit"]) == report_path.resolve()
    assert result["namespace_ignored"] is True
    assert result["material_findings"] is True
    assert [item["path"] for item in result["documents"]] == [str(runbook.resolve()), str(reference.resolve())]
    assert [item["material_findings"] for item in result["documents"]] == [False, True]
    assert {"missing_required_fact", "unresolved_gap"} <= {item["code"] for item in result["documents"][1]["findings"]}
    assert snapshot(*inputs) == before
    assert exclude.read_bytes() == seeded + b"\r\n/.first-four-hours/scribes/\r\n"
    assert ".first-four-hours" not in git_status(repo)
    sections = report_path.read_text(encoding="utf-8").split("\n## ")[1:]
    assert len(sections) == 2
    for section, item in zip(sections, result["documents"], strict=True):
        assert item["path"] in section.splitlines()[0]
        assert item["document_sha256"] in section
    assert "missing_required_fact" in sections[1] and "missing_required_fact" not in sections[0]
    assert "unresolved_gap" in sections[1] and "unresolved_gap" not in sections[0]
    assert "The reader cannot tell whether the service started." in sections[1]
    assert "The reader cannot tell" not in sections[0]

    # A source changed since the bundle bound its hash blocks the audit; it writes no report and keeps the earlier one.
    report = report_path.read_bytes()
    (repo / "source.txt").write_text("The service starts with port 9090.\n", encoding="utf-8")
    stale = snapshot(*inputs)
    for slug in ("runbook-audit", "fresh"):
        code, integrity = cli(repo, "audit", bundle=str(bundle_path), slug=slug)
        assert code == 3, integrity
        assert codes(integrity) == ["source_hash_mismatch"]
        action = integrity["diagnostics"][0]["required_action"]
        assert "Re-extract" in action and "never refresh only the hash" in action
    assert snapshot(*inputs) == stale
    assert report_path.read_bytes() == report
    assert not (report_path.parent.parent / "fresh").exists()

    elsewhere = repo.parent / "elsewhere"
    elsewhere.mkdir()
    link_directory(elsewhere, report_path.parent.parent / "linked")
    with pytest.raises(WorkspaceError, match="not a real directory"):
        prepare_workspace(repo, "linked")
    assert list(elsewhere.iterdir()) == []
    # A linked artifact root is refused before anything is written through it.
    exclude_before = exclude.read_bytes()
    rooted = repo.parent / "rooted"
    rooted_outside = repo.parent / "rooted-outside"
    rooted.mkdir()
    rooted_outside.mkdir()
    link_directory(rooted_outside, rooted / ".first-four-hours")
    with pytest.raises(WorkspaceError, match="not a real directory") as linked_root:
        prepare_workspace(rooted, "runbook")
    assert linked_root.value.code == "namespace_unsafe"
    assert list(rooted_outside.iterdir()) == []
    assert exclude.read_bytes() == exclude_before

    with pytest.raises(WorkspaceError) as git_dir:
        prepare_workspace(repo / ".git", "runbook")
    assert git_dir.value.code == "namespace_unsafe"
    assert not (repo / ".git" / ".first-four-hours").exists()
    head = repo / ".git" / "HEAD"
    saved_head = head.read_bytes()
    head.write_text("garbage\n", encoding="utf-8")
    try:
        with pytest.raises(WorkspaceError) as broken:
            prepare_workspace(repo, "runbook")
        assert broken.value.code == "namespace_unsafe"
    finally:
        head.write_bytes(saved_head)
    plain = repo.parent / "plain"
    plain.mkdir()
    assert prepare_workspace(plain, "runbook") == (
        plain.resolve() / ".first-four-hours" / "scribes" / "runbook" / "scribe-audit.md",
        False,
    )


STRUCTURED = """# Runbook

## Overview

If the check fails, the runbook ends. The restore window is between 2 and 4. The cable is red. The limit is two hundred requests.

## Prerequisites

- Confirm the backup exists in the `BACKUPS` folder.
- If the backup is missing, stop.

## Rollback

WARNING: The restore replaces the current data.

### Database

1. Stop the worker.
2. If the migration fails, run the restore with
   `restore.sh --db`.
3. Check the **service is
   healthy** message.
4. If the check fails, stop.

```bash
# Restore the database
restore.sh --db
```

5. Verify the worker is *running*.

## Reference

| Command | Effect |
| --- | --- |
| `purge.sh` | Purge the queue. |
| `systemctl stop worker` | The worker is stopped. |
"""
EMPTY_GLOSSARY: dict[str, Any] = {"terms": [], "abbreviations": {}, "action_verbs": [], "phrasal_verbs": [], "hazardous_actions": []}


def types(text: str, spec: dict[str, Any], **options: bool) -> list[str]:
    return sorted(item["type"] for item in validate_document(text, spec, **options))


def test_checks_follow_document_structure() -> None:
    source = ["SRC-1"]
    fact = {"id": "FACT-1", "claim": "Check the service is healthy message.", "source_ids": source, "section": "Database"}
    spec: dict[str, Any] = {
        "required_facts": [
            fact,
            {"id": "FACT-2", "claim": "Verify the worker is running.", "source_ids": source, "section": "Database"},
        ],
        "integrity_literals": [
            {"id": "LIT-1", "kind": "command", "literal": "restore.sh --db", "source_ids": source, "section": "Database"}
        ],
        "procedures": [
            {
                "id": "PROC-1",
                "ordered_markers": ["Stop the worker", "run the restore with restore.sh --db", "Verify the worker is running"],
                "section": "Rollback",
            }
        ],
        "warnings": [
            {
                "id": "WARN-1",
                "warning": "WARNING: The restore replaces the current data.",
                "dangerous_action": "Stop the worker",
                "section": "Rollback",
            }
        ],
        "recovery_steps": [
            {"id": "REC-1", "trigger": "If the migration fails", "step": "run the restore with restore.sh --db", "section": "Database"}
        ],
        "prerequisites": [{"id": "PRE-1", "marker": "Confirm the backup exists", "procedure": "PROC-1"}],
        "branches": [{"id": "BR-1", "condition": "If the check fails", "required_markers": ["stop"], "section": "Database"}],
    }
    # Sections cover subsections and fenced `#` lines; wraps, bold, and italics do not break matching.
    assert validate_document(STRUCTURED, spec) == []

    def variant(field: str, records: list[dict[str, Any]]) -> list[str]:
        changed = copy.deepcopy(spec)
        changed[field] = records
        return types(STRUCTURED, changed)

    recovery = {"id": "REC-1", "section": "Database"}
    assert variant("recovery_steps", [{**recovery, "trigger": "If the check fails", "step": "Stop the worker"}]) == ["recovery_order"]
    assert variant(
        "recovery_steps", [{**recovery, "trigger": "If the disk fills", "step": "run the restore with restore.sh --db"}]
    ) == ["missing_recovery_trigger"]
    assert variant("prerequisites", [{"id": "PRE-1", "marker": "If the check fails, stop", "procedure": "PROC-1"}]) == [
        "prerequisite_order"
    ]
    assert variant("prerequisites", [{"id": "PRE-1", "marker": "Confirm the backup exists", "procedure": "PROC-9"}]) == [
        "unknown_procedure"
    ]
    reordered = {"id": "PROC-1", "ordered_markers": ["Verify the worker is running", "Stop the worker"], "section": "Database"}
    assert variant("procedures", [reordered]) == ["procedure_order"]
    # The overview mentions "If the check fails" first, which first-mention ordering would have accepted.
    overview = {"id": "PROC-2", "ordered_markers": ["If the check fails", "Stop the worker"]}
    assert variant("procedures", [*spec["procedures"], overview]) == ["ambiguous_marker"]
    wrapped = {"id": "LIT-1", "kind": "value", "literal": "run the restore with restore.sh", "source_ids": source, "section": "Database"}
    assert variant("integrity_literals", [wrapped]) == ["missing_value"]

    duplicate = "# Notes\n\n## Steps\n\nRun the job.\n\n## Steps\n\nRun the job.\n"
    assert types(duplicate, {"required_facts": [{**fact, "claim": "Run the job.", "section": "Steps"}]}) == ["ambiguous_section"]
    assert types(STRUCTURED, {"required_facts": [fact]}, prose=False) == ["unsupported_section"]
    mentioned = "## Overview\n\nStop the worker first.\n\n## Steps\n\nWARNING: Stop ends the work.\n\n1. Stop the worker.\n"
    warning = {"id": "WARN-1", "warning": "WARNING: Stop ends the work.", "dangerous_action": "Stop the worker"}
    assert types(mentioned, {"warnings": [warning]}) == ["ambiguous_marker"]

    siblings = "## Steps\n\nWARNING: The stop ends work.\n\nStop the worker.\n\n## Steps\n\nStop the worker.\n"
    sibling_warnings = {item["line"] for item in collect_diagnostics(siblings, "strict", EMPTY_GLOSSARY) if item["rule_id"] == "MTE-WARN-001"}
    assert sibling_warnings == {9}

    found = {(item["rule_id"], item["line"]) for item in collect_diagnostics(STRUCTURED, "strict", EMPTY_GLOSSARY)}
    for absent in (("MTE-ABBR-001", 9), ("MTE-WARN-001", 10), ("MTE-VOICE-001", 5), ("MTE-WARN-001", 18)):
        assert absent not in found, absent
    for present in (("MTE-WARN-001", 36), ("MTE-WARN-001", 37), ("MTE-VOICE-001", 37)):
        assert present in found, present
    assert not {line for _, line in found} & {34, 35}

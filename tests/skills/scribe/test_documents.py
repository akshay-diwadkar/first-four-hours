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
from check_document import validate_document, validate_sources

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


def source_types(bundle: dict[str, Any], repo: Path) -> set[str]:
    return {item["type"] for item in validate_sources(bundle, repo)}


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
    assert source_types(bundle, repo) == set()
    assert validate_document(runbook.read_text(encoding="utf-8"), bundle["documents"][0]) == []
    stale = copy.deepcopy(bundle)
    stale["sources"][0]["sha256"] = "0" * 64
    assert "source_hash_mismatch" in source_types(stale, repo)
    report = copy.deepcopy(bundle)
    report["sources"].append(
        {"id": "SRC-2", "path": ".first-four-hours/scribes/runbook/scribe-audit.md", "sha256": "0" * 64, "authority": "audit report"}
    )
    assert "namespace_source" in source_types(report, repo)
    undeclared = copy.deepcopy(bundle)
    undeclared["documents"][1]["required_facts"] = [
        {"id": "FACT-1", "claim": "Run the service.", "source_ids": ["SRC-1", "SRC-9"]}
    ]
    undeclared["documents"][1]["integrity_literals"] = [
        {"id": "LIT-1", "kind": "value", "literal": "service", "source_ids": ["SRC-1"]}
    ]
    errors = validate_sources(undeclared, repo)
    assert [(item["type"], item["location"]) for item in errors] == [("undeclared_source", "source SRC-9")]

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
    assert "missing_required_fact" in {item["code"] for item in result["documents"][1]["findings"]}
    assert snapshot(*inputs) == before
    assert exclude.read_bytes() == seeded + b"\r\n/.first-four-hours/scribes/\r\n"
    assert ".first-four-hours" not in git_status(repo)
    sections = report_path.read_text(encoding="utf-8").split("\n## ")[1:]
    assert len(sections) == 2
    for section, item in zip(sections, result["documents"], strict=True):
        assert item["path"] in section.splitlines()[0]
        assert item["document_sha256"] in section
    assert "missing_required_fact" in sections[1] and "missing_required_fact" not in sections[0]
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

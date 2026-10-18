from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from bundle_workspace import WorkspaceError, locate_bundle, prepare_workspace

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


def snapshot(*paths: Path) -> dict[Path, tuple[bytes, int]]:
    return {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}


def with_fact(bundle: dict[str, Any]) -> str:
    bundle["required_facts"] = [{"id": "FACT-1", "claim": FACT, "source_ids": ["SRC-1"]}]
    return json.dumps(bundle, indent=2) + "\n"


def link_directory(target: Path, link: Path) -> None:
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


def test_write_checks_the_document_without_writing(document_case: tuple[Path, Path, dict[str, Any]]) -> None:
    repo, document, bundle = document_case
    code, prepared = cli(repo, "prepare", slug="Runbook")
    assert code == 0, prepared
    bundle_path = repo / ".first-four-hours" / "document-bundles" / "runbook" / "document-bundle.json"
    assert Path(prepared["result"]["bundle"]) == bundle_path
    assert prepared["result"]["namespace_ignored"] is True
    assert bundle_path.parent.is_dir() and not bundle_path.exists()
    bundle_path.write_text(with_fact(bundle), encoding="utf-8")
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo, capture_output=True, text=True, check=True
    )
    assert ".first-four-hours" not in status.stdout
    before = snapshot(document, bundle_path)

    code, blocked = cli(repo, "write", slug="runbook", document=str(document))
    assert code == 3, blocked
    assert blocked["status"] == "blocked"
    missing = [item for item in blocked["diagnostics"] if item["code"] == "missing_required_fact"]
    assert missing and missing[0]["required_action"] and missing[0]["valid_repairs"]
    assert snapshot(document, bundle_path) == before

    document.write_text(document.read_text(encoding="utf-8") + "\n" + FACT + "\n", encoding="utf-8")
    after_repair = snapshot(document, bundle_path)
    code, complete = cli(repo, "write", slug="runbook", document=str(document))
    assert code == 0, complete
    assert complete["status"] == "complete"
    assert complete["result"]["status"] == "complete"
    assert complete["result"]["document_sha256"] == "sha256:" + hashlib.sha256(document.read_bytes()).hexdigest()
    assert after_repair[bundle_path] == before[bundle_path]
    assert snapshot(document, bundle_path) == after_repair

    bundle_path.write_text("[" * 50000 + "]" * 50000, encoding="utf-8")
    code, malformed = cli(repo, "write", slug="runbook", document=str(document))
    assert code == 3, malformed
    assert [item["code"] for item in malformed["diagnostics"]] == ["invalid_input"]

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
        fitting = 245 - len(str(repo.resolve() / ".first-four-hours" / "document-bundles")) - 1
        if not long_paths and fitting > 0:
            with pytest.raises(WorkspaceError, match="choose a shorter or different slug") as unusable_bundle:
                prepare_workspace(repo, "c" * fitting)
            assert unusable_bundle.value.code == "invalid_slug"
    (repo / "sub").mkdir()
    with pytest.raises(WorkspaceError, match="Git worktree root"):
        prepare_workspace(repo / "sub", "runbook")
    tracked = repo.parent / "tracked"
    seed_git(tracked, {".first-four-hours/document-bundles/notes.md": "tracked\n"})
    with pytest.raises(WorkspaceError, match="tracked project files"):
        prepare_workspace(tracked, "runbook")
    exclude = repo / ".git" / "info" / "exclude"
    exclude.unlink()
    exclude.mkdir()
    with pytest.raises(WorkspaceError, match="linked or not a regular file"):
        locate_bundle(repo, "runbook")
    exclude.rmdir()
    exclude.write_text("", encoding="utf-8")
    moved_info = repo.parent / "info-target"
    exclude.parent.rename(moved_info)
    link_directory(moved_info, exclude.parent)
    with pytest.raises(WorkspaceError, match="linked or not a regular file"):
        locate_bundle(repo, "runbook")


def test_audit_is_read_only_and_refuses_an_unignored_bundle(
    document_case: tuple[Path, Path, dict[str, Any]],
) -> None:
    repo, document, bundle = document_case
    bundle_path = repo / ".first-four-hours" / "document-bundles" / "runbook" / "document-bundle.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_text = with_fact(bundle)
    bundle_path.write_text(bundle_text, encoding="utf-8")
    exclude = repo / ".git" / "info" / "exclude"
    exclude_before = exclude.read_bytes() if exclude.exists() else None

    code, refused = cli(repo, "audit", slug="runbook", document=str(document))
    assert code == 3, refused
    assert [item["code"] for item in refused["diagnostics"]] == ["namespace_not_ignored"]
    assert (exclude.read_bytes() if exclude.exists() else None) == exclude_before

    elsewhere = repo.parent / "elsewhere"
    elsewhere.mkdir()
    linked = repo / ".first-four-hours" / "document-bundles" / "linked"
    link_directory(elsewhere, linked)
    with pytest.raises(WorkspaceError, match="not a real directory"):
        locate_bundle(repo, "linked")
    with pytest.raises(WorkspaceError, match="not a real directory"):
        prepare_workspace(repo, "linked")
    # A linked artifact root is refused before anything is written through it.
    rooted = repo.parent / "rooted"
    rooted_outside = repo.parent / "rooted-outside"
    rooted.mkdir()
    rooted_outside.mkdir()
    link_directory(rooted_outside, rooted / ".first-four-hours")
    with pytest.raises(WorkspaceError, match="not a real directory") as linked_root:
        prepare_workspace(rooted, "runbook")
    assert linked_root.value.code == "namespace_unsafe"
    assert list(rooted_outside.iterdir()) == []
    assert (exclude.read_bytes() if exclude.exists() else None) == exclude_before

    seeded = b"# caf\xe9\r\n*.tmp"
    exclude.write_bytes(seeded)
    code, prepared = cli(repo, "prepare", slug="runbook")
    assert code == 0, prepared
    assert exclude.read_bytes() == seeded + b"\r\n/.first-four-hours/document-bundles/\r\n"
    assert bundle_path.read_text(encoding="utf-8") == bundle_text
    inputs = [document, bundle_path, repo / "source.txt"]
    before = snapshot(*inputs)
    code, audited = cli(repo, "audit", slug="runbook", document=str(document))
    assert code == 0, audited
    report = audited["result"]
    assert report["status"] == "complete"
    assert report["material_findings"] is True
    assert "missing_required_fact" in {item["code"] for item in report["findings"]}
    assert set(report) == {"status", "document_sha256", "material_findings", "findings", "namespace_ignored"}
    assert report["document_sha256"] == "sha256:" + hashlib.sha256(document.read_bytes()).hexdigest()
    assert snapshot(*inputs) == before

    with pytest.raises(WorkspaceError) as git_dir:
        prepare_workspace(repo / ".git", "runbook")
    assert git_dir.value.code == "namespace_unsafe"
    assert not (repo / ".git" / ".first-four-hours").exists()
    head = repo / ".git" / "HEAD"
    saved_head = head.read_bytes()
    head.write_text("garbage\n", encoding="utf-8")
    try:
        with pytest.raises(WorkspaceError) as broken:
            locate_bundle(repo, "runbook")
        assert broken.value.code == "namespace_unsafe"
    finally:
        head.write_bytes(saved_head)
    plain = repo.parent / "plain"
    plain.mkdir()
    assert prepare_workspace(plain, "runbook") == (
        plain.resolve() / ".first-four-hours" / "document-bundles" / "runbook" / "document-bundle.json",
        False,
    )

    import audit_document
    import seal_document

    misplaced = bundle_path.parent / "document.md"
    misplaced.write_bytes(document.read_bytes())
    for operation in (seal_document.check, audit_document.audit):
        with pytest.raises(WorkspaceError) as inside:
            operation(repo, "runbook", misplaced)
        assert inside.value.code == "namespace_document"

    # A source changed since the bundle bound its hash blocks the audit; it is not a finding.
    (repo / "source.txt").write_text("The service starts with port 9090.\n", encoding="utf-8")
    stale = snapshot(*inputs)
    code, integrity = audit_document.audit(repo, "runbook", document)
    assert code == 1
    assert integrity["status"] == "blocked"
    assert [item["code"] for item in integrity["diagnostics"]] == ["source_hash_mismatch"]
    action = integrity["diagnostics"][0]["required_action"]
    assert "Re-extract" in action and "never refresh only the hash" in action
    assert integrity["diagnostics"][0]["valid_repairs"] == [action]
    assert "findings" not in integrity
    assert snapshot(*inputs) == stale
    # A fact citing an undeclared source blocks the audit the same way.
    (repo / "source.txt").write_text("The service starts with port 8080.\n", encoding="utf-8")
    cited = json.loads(bundle_text)
    cited["required_facts"][0]["source_ids"] = ["SRC-9"]
    bundle_path.write_text(json.dumps(cited), encoding="utf-8")
    code, undeclared = audit_document.audit(repo, "runbook", document)
    assert code == 1
    assert [item["code"] for item in undeclared["diagnostics"]] == ["undeclared_source"]
    assert "findings" not in undeclared

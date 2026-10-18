from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import shutil
import pytest
import sys
from pathlib import Path


from tools.validation.git_test_support import seed_git
from tools.validation.python_test_support import run_python

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills" / "workbench" / "assess"
CLI = SKILL / "scripts" / "cli.py"
sys.path.insert(0, str(SKILL / "scripts"))

contract = importlib.import_module("assess_contract")
AssessError = contract.AssessError
parse_result = contract.parse_result
prepare_assessment_workspace = contract.prepare_assessment_workspace
validate_bundle = contract.validate_bundle


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


@pytest.fixture(scope="session")
def assessment_seed(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str, str]:
    repo = tmp_path_factory.mktemp("assessment-seed")
    source = repo / "service.py"
    source.write_text("value = 1\n", encoding="utf-8")
    base = seed_git(repo)
    _git(repo, "branch", "assess-base", base)
    source.write_text("value = 2\n", encoding="utf-8")
    _git(repo, "commit", "-am", "head")
    head = _git(repo, "rev-parse", "HEAD")
    return repo, base, head



def _repository(tmp_path: Path, seed: tuple[Path, str, str]) -> tuple[Path, str, str]:
    original, base, head = seed
    repo = tmp_path / "repo"
    shutil.copytree(original, repo)
    return repo, base, head


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run_python(
        [sys.executable, str(CLI), "--repo-root", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _snapshot(tmp_path: Path, name: str = "issue-382.md", text: str = "# Issue 382\nCurrent acceptance.\n") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _assessed_source(path: Path, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "issue-382",
        "role": "authority",
        "locator": "https://github.com/akshay-diwadkar/first-four-hours/issues/382",
        "path": str(path),
    }
    payload.update(overrides)
    return payload


def _static_bundle(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0.0",
        "target": "local assessment",
        "base_ref": "assess-base",
        "head_ref": "HEAD",
        "assessed_sources": [],
        "result": "clear",
        "examined": [{"kind": "head-file", "path": "service.py", "start_line": 1, "end_line": 1}],
        "findings": [],
        "limitations": [],
    }
    payload.update(overrides)
    return payload


def _bundle(tmp_path: Path, **overrides: object) -> dict[str, object]:
    payload = _static_bundle()
    payload.update(overrides)
    return payload


def _seal(
    repo: Path, tmp_path: Path, payload: dict[str, object], output: Path | None = None
) -> tuple[subprocess.CompletedProcess[str], Path]:
    bundle = tmp_path / "assessment-bundle.json"
    result = output or prepare_assessment_workspace(repo, "case").output_path
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    return (
        _run(
            repo,
            "--input",
            f"bundle={bundle}",
            "--input",
            f"output={result}",
            "--format",
            "json",
            "run",
        ),
        result,
    )


def test_findings_result_binds_file_and_assessed_source_locators(tmp_path: Path, assessment_seed: tuple[Path, str, str]) -> None:
    repo, _base, head = _repository(tmp_path, assessment_seed)
    snapshot = _snapshot(tmp_path)
    finding = {
        "severity": "P1",
        "defect": "The changed value violates the governing requirement.",
        "locators": [
            {"kind": "base-file", "path": "service.py", "start_line": 1, "end_line": 1},
            {"kind": "head-file", "path": "service.py", "start_line": 1, "end_line": 1},
            {"kind": "source", "source_id": "issue-382"},
        ],
        "consequence": "The proposed change cannot proceed without restoring the requirement.",
        "required_truth": "The committed value must satisfy the governing requirement.",
        "basis": "reasoned",
    }
    sources = [_assessed_source(snapshot)]
    missing = {key: value for key, value in finding.items() if key != "severity"}
    unsupported = [{**finding, "severity": value} for value in ("high", "merge blocking", "p1", "P1 ", "P4", None)]
    for candidate in [*unsupported, missing]:
        with pytest.raises(AssessError) as refused:
            validate_bundle(_bundle(tmp_path, assessed_sources=sources, result="findings", findings=[candidate]))
        assert refused.value.code == "finding.severity_invalid"
        assert "findings[0].severity" in refused.value.message
        assert "P0, P1, P2, P3" in refused.value.message
    output = prepare_assessment_workspace(repo, "case").output_path
    high = _bundle(tmp_path, assessed_sources=sources, result="findings", findings=[unsupported[0]])
    refused_seal, _ = _seal(repo, tmp_path, high, output)
    assert refused_seal.returncode != 0
    severity_diagnostic = json.loads(refused_seal.stdout)["diagnostics"][0]
    assert severity_diagnostic["code"] == "finding.severity_invalid"
    assert severity_diagnostic["path"] == "assessment.md"
    assert not output.exists()
    sealed, _ = _seal(
        repo,
        tmp_path,
        _bundle(tmp_path, assessed_sources=sources, result="findings", findings=[finding]),
        output,
    )
    assert sealed.returncode == 0, sealed.stdout + sealed.stderr
    artifact = output.read_text(encoding="utf-8")
    assert [line for line in artifact.splitlines() if line.startswith("#")] == [
        "# Assessment",
        "## Result",
        "## Findings",
        "### Finding 1",
        "## Limitations",
        "## Changed paths not examined",
        "## Target",
        "## Assessed snapshots",
        "## Examined",
    ]
    assert artifact.startswith("# Assessment\n")
    receipt = artifact.splitlines()[-1]
    assert receipt.startswith("<!-- assessment-result: 1.0.0; sha256: ")
    assert "`findings`" in artifact
    assert '- Severity: "P1"' in artifact
    assert f"{head}:service.py#L1-L1" in artifact
    assert "source_id" in artifact and "issue-382" in artifact
    assert "implementation_plan" not in artifact
    assert '- Basis: "reasoned"' in artifact
    current = _run(repo, "--input", f"output={output}", "--format", "json", "check")
    assert current.returncode == 0, current.stdout + current.stderr
    body = artifact.removesuffix("\n").rpartition("\n")[0] + "\n"
    title, *sections = body.split("\n## ")
    by_heading = {section.split("\n", 1)[0]: section for section in sections}
    old_order = ["Target", "Assessed snapshots", "Result", "Examined", "Changed paths not examined", "Findings", "Limitations"]
    reordered = "\n## ".join([title, *(by_heading[name] for name in old_order)]).rstrip("\n") + "\n"
    reordered_digest = hashlib.sha256(reordered.encode("utf-8")).hexdigest()
    with pytest.raises(AssessError) as refused_order:
        parse_result(f"{reordered}<!-- assessment-result: 1.0.0; sha256: {reordered_digest} -->\n")
    assert refused_order.value.code == "artifact.shape_invalid"
    assert "headings are not canonical" in refused_order.value.message
    blocked = body.replace("\n`findings`\n", "\n`blocked`\n", 1)
    blocked_digest = hashlib.sha256(blocked.encode("utf-8")).hexdigest()
    with pytest.raises(AssessError) as refused_blocked:
        parse_result(f"{blocked}<!-- assessment-result: 1.0.0; sha256: {blocked_digest} -->\n")
    assert refused_blocked.value.code == "artifact.shape_invalid"
    assert "requires a material limitation" in refused_blocked.value.message
    legacy = artifact.replace("<!-- assessment-result: 1.0.0; ", "<!-- assessment-result: 2.0.0; ", 1)
    output.write_text(legacy, encoding="utf-8")
    checked = _run(repo, "--input", f"output={output}", "--format", "json", "check")
    assert checked.returncode != 0
    retired = json.loads(checked.stdout)["diagnostics"][0]
    assert retired["code"] == "artifact.version_unsupported"
    assert retired["category"] == "stale_evidence"
    assert output.read_text(encoding="utf-8") == legacy
    # A receipt that leads the document instead of ending it is refused.
    output.write_text(receipt + "\n" + body, encoding="utf-8")
    displaced = _run(repo, "--input", f"output={output}", "--format", "json", "check")
    assert displaced.returncode != 0
    assert json.loads(displaced.stdout)["diagnostics"][0]["code"] == "artifact.receipt_invalid"

def test_unsupported_coverage_claims_are_rejected(tmp_path: Path, assessment_seed: tuple[Path, str, str]) -> None:
    repo, _, _ = _repository(tmp_path, assessment_seed)
    sealed, output = _seal(repo, tmp_path, _bundle(tmp_path, examined=[]))
    assert sealed.returncode != 0
    assert json.loads(sealed.stdout)["diagnostics"][0]["code"] == "result.coverage_missing"
    assert not output.exists()
    (repo / "gen").mkdir()
    (repo / "extra.py").write_text("extra = 1\n", encoding="utf-8")
    (repo / "gen" / "extra.py").write_text("extra = 2\n", encoding="utf-8")
    (repo / "old extra.py").write_text("extra = 3\n", encoding="utf-8")
    (repo / "extra.py~").write_text("extra = 4\n", encoding="utf-8")
    _git(repo, "add", "extra.py", "gen/extra.py", "old extra.py", "extra.py~")
    _git(repo, "commit", "-qm", "add unexamined paths")
    unrelated_bundle = _bundle(tmp_path, limitations=["No fresh-context delegate was available."])
    unrelated, _ = _seal(repo, tmp_path, unrelated_bundle, output)
    assert unrelated.returncode != 0
    diagnostic = json.loads(unrelated.stdout)["diagnostics"][0]
    assert diagnostic["code"] == "result.unexamined_undisclosed"
    assert diagnostic["supporting_evidence"] == ["extra.py", "extra.py~", "gen/extra.py", "old extra.py"]
    assert not output.exists()
    collision = [
        "Generated gen/extra.py, old extra.py, and extra.py~ were not examined.",
        "Neither my_extra.py, extra.pyc, nor extra.py.bak was examined.",
    ]
    colliding, _ = _seal(repo, tmp_path, _bundle(tmp_path, limitations=collision), output)
    assert colliding.returncode != 0
    diagnostic = json.loads(colliding.stdout)["diagnostics"][0]
    assert diagnostic["code"] == "result.unexamined_undisclosed"
    assert diagnostic["supporting_evidence"] == ["extra.py"]
    assert not output.exists()
    naming = ["Generated files not examined: gen/extra.py, old extra.py, extra.py.", "Backup extra.py~ was not examined."]
    named_bundle = _bundle(tmp_path, limitations=naming)
    named, _ = _seal(repo, tmp_path, named_bundle, output)
    assert named.returncode == 0, named.stdout + named.stderr
    assert output.is_file()


def test_prepared_assessment_lifecycle_rejects_wrong_name_and_tampering(tmp_path: Path, assessment_seed: tuple[Path, str, str]) -> None:
    repo, _base, _head = _repository(tmp_path, assessment_seed)
    prepared = _run(repo, "--input", "slug=Rename Check", "--format", "json", "prepare")
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr
    workspace = json.loads(prepared.stdout)["result"]
    assert workspace["relative_output_path"] == ".first-four-hours/assessments/rename-check/assessment.md"
    output = Path(workspace["output_path"])
    assert output.parent == repo / ".first-four-hours" / "assessments" / "rename-check"
    assert "/.first-four-hours/assessments/" in (repo / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()
    wrong, _ = _seal(repo, tmp_path, _bundle(tmp_path), output.parent / "review.md")
    assert wrong.returncode != 0
    assert json.loads(wrong.stdout)["diagnostics"][0]["code"] == "output.name_invalid"
    assert list(output.parent.iterdir()) == []
    outside = tmp_path / "outside" / "assessment.md"
    outside.parent.mkdir()
    for refused_output in (outside, repo / ".first-four-hours" / "assessments" / "assessment.md"):
        refused, _ = _seal(repo, tmp_path, _bundle(tmp_path), refused_output)
        assert refused.returncode != 0
        assert json.loads(refused.stdout)["diagnostics"][0]["code"] == "output.outside_workspace"
        assert not refused_output.exists()
    alias = repo / ".first-four-hours" / "assessments" / "alias"
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(outside.parent), str(alias))
    else:
        alias.symlink_to(outside.parent, target_is_directory=True)
    linked, _ = _seal(repo, tmp_path, _bundle(tmp_path), alias / "assessment.md")
    assert linked.returncode != 0
    assert json.loads(linked.stdout)["diagnostics"][0]["code"] == "output.outside_workspace"
    assert list(outside.parent.iterdir()) == []
    assert list(output.parent.iterdir()) == []
    # A linked artifact root is refused before any exclude write or directory creation.
    rooted = tmp_path / "rooted"
    seed_git(rooted, {"seed.txt": "seed\n"})
    rooted_outside = tmp_path / "rooted-outside"
    rooted_outside.mkdir()
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(rooted_outside), str(rooted / ".first-four-hours"))
    else:
        (rooted / ".first-four-hours").symlink_to(rooted_outside, target_is_directory=True)
    rooted_prepare = _run(rooted, "--input", "slug=Rooted", "--format", "json", "prepare")
    assert rooted_prepare.returncode != 0
    assert json.loads(rooted_prepare.stdout)["diagnostics"][0]["code"] == "workspace.namespace_unsafe"
    assert list(rooted_outside.iterdir()) == []
    rooted_exclude = rooted / ".git" / "info" / "exclude"
    assert not rooted_exclude.exists() or "/.first-four-hours/assessments/" not in rooted_exclude.read_text(encoding="utf-8")
    # A linked namespace inside a real artifact root is refused the same way.
    if sys.platform == "win32":
        (rooted / ".first-four-hours").rmdir()
    else:
        (rooted / ".first-four-hours").unlink()
    namespace = rooted / ".first-four-hours" / "assessments"
    namespace.parent.mkdir()
    if sys.platform == "win32":
        _winapi.CreateJunction(str(rooted_outside), str(namespace))
    else:
        namespace.symlink_to(rooted_outside, target_is_directory=True)
    namespace_prepare = _run(rooted, "--input", "slug=Rooted", "--format", "json", "prepare")
    assert namespace_prepare.returncode != 0
    assert json.loads(namespace_prepare.stdout)["diagnostics"][0]["code"] == "workspace.namespace_unsafe"
    assert list(rooted_outside.iterdir()) == []
    assert not rooted_exclude.exists() or "/.first-four-hours/assessments/" not in rooted_exclude.read_text(encoding="utf-8")
    sealed, _ = _seal(repo, tmp_path, _bundle(tmp_path), output)
    assert sealed.returncode == 0, sealed.stdout + sealed.stderr
    assert _git(repo, "status", "--porcelain") == ""
    assert _run(repo, "--input", f"output={output}", "--format", "json", "check").returncode == 0
    output.write_text(output.read_text(encoding="utf-8").replace("`clear`", "`blocked`"), encoding="utf-8")
    before = output.read_bytes()
    checked = _run(repo, "--input", f"output={output}", "--format", "json", "check")
    assert checked.returncode != 0
    assert json.loads(checked.stdout)["diagnostics"][0]["code"] == "artifact.integrity_stale"
    assert output.read_bytes() == before
    (repo / ".first-four-hours" / "assessments" / "tracked.md").write_text("tracked\n", encoding="utf-8")
    _git(repo, "add", "-f", ".first-four-hours/assessments/tracked.md")
    resealed, _ = _seal(repo, tmp_path, _bundle(tmp_path), output)
    assert resealed.returncode != 0
    assert json.loads(resealed.stdout)["diagnostics"][0]["code"] == "workspace.namespace_tracked"
    assert output.read_bytes() == before
    reprepared = _run(repo, "--input", "slug=Other Check", "--format", "json", "prepare")
    assert reprepared.returncode != 0
    assert json.loads(reprepared.stdout)["diagnostics"][0]["code"] == "workspace.namespace_tracked"
    assert not (repo / ".first-four-hours" / "assessments" / "other-check").exists()
    _git(repo, "commit", "-qm", "track the assessment namespace")
    _git(repo, "rm", "-q", "--cached", ".first-four-hours/assessments/tracked.md")
    assert _git(repo, "ls-files", "--", ".first-four-hours/assessments") == ""
    staged, _ = _seal(repo, tmp_path, _bundle(tmp_path, limitations=["tracked.md removal not examined"]), output)
    assert staged.returncode != 0
    assert json.loads(staged.stdout)["diagnostics"][0]["code"] == "workspace.namespace_tracked"
    assert output.read_bytes() == before
    head_prepared = _run(repo, "--input", "slug=Third Check", "--format", "json", "prepare")
    assert head_prepared.returncode != 0
    assert json.loads(head_prepared.stdout)["diagnostics"][0]["code"] == "workspace.namespace_tracked"
    assert not (repo / ".first-four-hours" / "assessments" / "third-check").exists()
    (repo / ".git" / _git(repo, "symbolic-ref", "HEAD")).write_text("garbage\n", encoding="utf-8")
    broken = _run(repo, "--input", "slug=Third Check", "--format", "json", "prepare")
    assert broken.returncode != 0
    assert json.loads(broken.stdout)["diagnostics"][0]["code"] == "workspace.git.tracked_check"
    assert not (repo / ".first-four-hours" / "assessments" / "third-check").exists()

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


def test_findings_result_binds_file_and_assessed_source_locators(
    tmp_path: Path, assessment_seed: tuple[Path, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, base, head = _repository(tmp_path, assessment_seed)
    snapshot = _snapshot(tmp_path)
    finding = {
        "severity": "P1",
        "defect": "The changed value violates the governing requirement.",
        "scenario": [
            "A caller reads the changed value in service.py.",
            "The value breaks the rule issue-382 sets, which the base value met.",
        ],
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
    unexplained = {key: value for key, value in finding.items() if key != "scenario"}
    for candidate, code, label in (
        (unexplained, "bundle.field_missing", "scenario"),
        ({**finding, "scenario": []}, "finding.scenario_missing", "findings[0].scenario"),
        ({**finding, "scenario": ["   "]}, "bundle.string_invalid", "findings[0].scenario[0]"),
    ):
        with pytest.raises(AssessError) as refused:
            validate_bundle(_bundle(tmp_path, assessed_sources=sources, result="findings", findings=[candidate]))
        assert refused.value.code == code
        assert "findings[0]" in refused.value.message and label in refused.value.message
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
    assert receipt.startswith(f"<!-- assessment-result: {contract.CONTRACT_VERSION}; sha256: ")
    assert "`findings`" in artifact
    assert '- Severity: "P1"' in artifact
    assert f"{head}:service.py#L1-L1" in artifact
    assert "source_id" in artifact and "issue-382" in artifact
    assert "implementation_plan" not in artifact
    assert '- Basis: "reasoned"' in artifact
    assert (
        '- Defect: "The changed value violates the governing requirement."\n'
        "- Scenario:\n"
        '  - "A caller reads the changed value in service.py."\n'
        '  - "The value breaks the rule issue-382 sets, which the base value met."\n'
        "- Evidence / authority:\n"
    ) in artifact
    current = _run(repo, "--input", f"output={output}", "--format", "json", "check")
    assert current.returncode == 0, current.stdout + current.stderr
    # Only a checked findings assessment of a pull request whose live head is the assessed head is posted.
    local_bytes = output.read_bytes()
    not_pull = _run(repo, "--input", f"output={output}", "--format", "json", "publish")
    assert not_pull.returncode != 0
    assert json.loads(not_pull.stdout)["diagnostics"][0]["code"] == "publish.target_not_pull_request"
    assert output.read_bytes() == local_bytes
    target = "https://github.com/acme/widget/pull/7"
    resealed, _ = _seal(
        repo,
        tmp_path,
        _bundle(tmp_path, target=target, assessed_sources=sources, result="findings", findings=[finding]),
        output,
    )
    assert resealed.returncode == 0, resealed.stdout + resealed.stderr
    sealed_bytes = output.read_bytes()
    calls: list[tuple[list[str], str | None]] = []
    live_head = head

    def fake_gh(argv: list[str], cwd: Path, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        calls.append((argv, stdin))
        if argv[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(argv, 0, json.dumps({"url": target, "headRefOid": live_head}), "")
        assert argv[:3] == ["gh", "pr", "comment"]
        return subprocess.CompletedProcess(argv, 0, "https://github.com/acme/widget/pull/7#issuecomment-1\n", "")

    monkeypatch.setattr(contract, "run_gh", fake_gh)
    preview = contract.publish_findings(repo, output, None)
    comment = preview["body"]
    digest = preview["body_sha256"]
    assert preview["status"] == "preview" and preview["posted"] is False
    assert digest == hashlib.sha256(comment.encode("utf-8")).hexdigest()
    assert calls == [(["gh", "pr", "view", target, "--json", "url,headRefOid"], None)]
    for expected in (
        f"head commit `{head}`",
        f"base commit `{base}`",
        "found 1 finding.",
        "It is not an approval, a change request, or a statement that this pull request is ready to merge.",
        "### Finding 1: P1",
        "**Defect:** The changed value violates the governing requirement.",
        "1. A caller reads the changed value in service.py.\n"
        "2. The value breaks the rule issue-382 sets, which the base value met.",
        f"(https://github.com/acme/widget/blob/{head}/service.py#L1-L1)",
        f"(https://github.com/acme/widget/blob/{base}/service.py#L1-L1)",
        "Source `issue-382` (authority): https://github.com/akshay-diwadkar/first-four-hours/issues/382",
        "**Consequence:** The proposed change cannot proceed without restoring the requirement.",
        "**Truth to restore:** The committed value must satisfy the governing requirement.",
    ):
        assert expected in comment
    assert str(tmp_path) not in comment and "Limitations" not in comment
    sealed_text = sealed_bytes.decode("utf-8")
    parsed = contract._parse_findings(sealed_text.removesuffix("\n").rpartition("\n")[0] + "\n")[0]
    local_evidence = [
        {**item, "locator": str(snapshot)} if item["kind"] == "source" else item for item in parsed["evidence"]
    ]
    local_comment = contract.render_comment(
        ("github.com", "acme", "widget"), base, head, [{**parsed, "evidence": local_evidence}]
    )
    assert "Source `issue-382` (authority)\n" in local_comment and str(snapshot) not in local_comment
    with pytest.raises(AssessError) as unconfirmed:
        contract.publish_findings(repo, output, "0" * 64)
    assert unconfirmed.value.code == "publish.unconfirmed" and len(calls) == 1
    live_head = "f" * 40
    with pytest.raises(AssessError) as moved:
        contract.publish_findings(repo, output, digest)
    assert moved.value.code == "publish.head_moved"
    assert not [argv for argv, _ in calls if argv[:3] == ["gh", "pr", "comment"]]
    live_head = head
    posted = contract.publish_findings(repo, output, digest)
    assert posted["status"] == "posted"
    assert posted["comment_url"] == "https://github.com/acme/widget/pull/7#issuecomment-1"
    assert calls[-1] == (["gh", "pr", "comment", target, "--body-file", "-"], comment)
    assert output.read_bytes() == sealed_bytes
    recorded = len(calls)
    clear_output = prepare_assessment_workspace(repo, "clear-case").output_path
    clear_sealed, _ = _seal(repo, tmp_path, _bundle(tmp_path, target=target), clear_output)
    assert clear_sealed.returncode == 0, clear_sealed.stdout + clear_sealed.stderr
    with pytest.raises(AssessError) as not_findings:
        contract.publish_findings(repo, clear_output, None)
    assert not_findings.value.code == "publish.result_not_findings" and len(calls) == recorded
    output.write_bytes(sealed_bytes.replace(b'- Severity: "P1"', b'- Severity: "P3"', 1))
    with pytest.raises(AssessError) as tampered:
        contract.publish_findings(repo, output, digest)
    assert tampered.value.code == "artifact.integrity_stale" and len(calls) == recorded
    output.write_bytes(sealed_bytes)
    snapshot_bytes = snapshot.read_bytes()
    snapshot.write_text("# Issue 382\nChanged acceptance.\n", encoding="utf-8")
    with pytest.raises(AssessError) as changed_source:
        contract.publish_findings(repo, output, digest)
    assert changed_source.value.code == "result.stale" and len(calls) == recorded
    snapshot.write_bytes(snapshot_bytes)
    # A moved base alone still posts the same confirmed text, naming the base it reviewed; a moved head does not.
    _git(repo, "update-ref", "refs/heads/assess-base", head)
    rebased = contract.publish_findings(repo, output, digest)
    assert rebased["status"] == "posted" and calls[-1] == (["gh", "pr", "comment", target, "--body-file", "-"], comment)
    recorded = len(calls)
    _git(repo, "update-ref", "HEAD", base)
    with pytest.raises(AssessError) as both_moved:
        contract.publish_findings(repo, output, digest)
    assert both_moved.value.code == "result.target_moved" and len(calls) == recorded
    _git(repo, "update-ref", "HEAD", head)
    _git(repo, "update-ref", "refs/heads/assess-base", base)
    assert output.read_bytes() == sealed_bytes
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
    legacy = artifact.replace(f"<!-- assessment-result: {contract.CONTRACT_VERSION}; ","<!-- assessment-result: 2.0.0; ", 1)
    output.write_text(legacy, encoding="utf-8")
    checked = _run(repo, "--input", f"output={output}", "--format", "json", "check")
    assert checked.returncode != 0
    retired = json.loads(checked.stdout)["diagnostics"][0]
    assert retired["code"] == "artifact.version_unsupported"
    assert retired["category"] == "stale_evidence"
    assert output.read_text(encoding="utf-8") == legacy
    # An assessment sealed before findings carried a scenario still checks.
    lines = body.splitlines(keepends=True)
    start = lines.index("- Scenario:\n")
    unscripted = "".join(lines[:start] + lines[start + 3 :])
    unscripted_digest = hashlib.sha256(unscripted.encode("utf-8")).hexdigest()
    output.write_text(f"{unscripted}<!-- assessment-result: 1.4.0; sha256: {unscripted_digest} -->\n", encoding="utf-8")
    earlier = _run(repo, "--input", f"output={output}", "--format", "json", "check")
    assert earlier.returncode == 0, earlier.stdout + earlier.stderr
    # A receipt that leads the document instead of ending it is refused.
    output.write_text(receipt + "\n" + body, encoding="utf-8")
    displaced = _run(repo, "--input", f"output={output}", "--format", "json", "check")
    assert displaced.returncode != 0
    assert json.loads(displaced.stdout)["diagnostics"][0]["code"] == "artifact.receipt_invalid"

def test_unsupported_coverage_claims_are_rejected(tmp_path: Path, assessment_seed: tuple[Path, str, str]) -> None:
    repo, _, _ = _repository(tmp_path, assessment_seed)
    beyond_end = {
        "severity": "P2",
        "defect": "The cited range does not exist in the reviewed file.",
        "scenario": [
            "The finding cites lines 1-5 of service.py.",
            "The reviewed file has fewer lines, so the range cannot be bound.",
        ],
        "locators": [{"kind": "head-file", "path": "service.py", "start_line": 1, "end_line": 5}],
        "consequence": "The finding cannot be bound to reviewed text.",
        "required_truth": "Every cited range must exist in the reviewed file.",
        "basis": "reasoned",
    }
    bad_locators = _bundle(
        tmp_path,
        result="findings",
        findings=[beyond_end],
        examined=[{"kind": "head-file", "path": "service.py", "start_line": 2, "end_line": 3}],
    )
    refused, output = _seal(repo, tmp_path, bad_locators)
    assert refused.returncode != 0
    locator_diagnostic = json.loads(refused.stdout)["diagnostics"][0]
    assert locator_diagnostic["code"] == "locator.range_invalid"
    evidence = locator_diagnostic["supporting_evidence"]
    assert len(evidence) == 2
    assert any("findings[0].locators[0]" in item for item in evidence)
    assert any("examined[0]" in item for item in evidence)
    assert not output.exists()
    sealed, _ = _seal(repo, tmp_path, _bundle(tmp_path, examined=[]), output)
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
    repo, base, head = _repository(tmp_path, assessment_seed)
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
    # A PR head present only in a checkout-less fetched repository seals and checks.
    _git(repo, "update-ref", "refs/pull/7/head", head)
    fetched = tmp_path / "pr-repo"
    _git(tmp_path, "init", "-q", str(fetched))
    _git(
        fetched,
        "fetch",
        "-q",
        "--no-tags",
        str(repo),
        "+refs/pull/7/head:refs/first-four-hours/pr/7/head",
        "+refs/heads/assess-base:refs/first-four-hours/pr/7/base",
    )
    pr_prepared = _run(fetched, "--input", "slug=PR 7", "--format", "json", "prepare")
    assert pr_prepared.returncode == 0, pr_prepared.stdout + pr_prepared.stderr
    pr_output = Path(json.loads(pr_prepared.stdout)["result"]["output_path"])
    pr_sealed, _ = _seal(
        fetched,
        tmp_path,
        _bundle(tmp_path, base_ref="refs/first-four-hours/pr/7/base", head_ref="refs/first-four-hours/pr/7/head"),
        pr_output,
    )
    assert pr_sealed.returncode == 0, pr_sealed.stdout + pr_sealed.stderr
    pr_check = _run(fetched, "--input", f"output={pr_output}", "--format", "json", "check")
    assert pr_check.returncode == 0, pr_check.stdout + pr_check.stderr
    pr_result = parse_result(pr_output.read_text(encoding="utf-8"))
    assert pr_result["base_revision"] == base
    assert pr_result["head_revision"] == head
    assert _git(fetched, "status", "--porcelain") == ""
    # Replay a delta review on the template's own refs.
    template = json.loads((SKILL / "templates" / "assessment-bundle.json").read_text(encoding="utf-8"))
    default_refs = {"base_ref": template["base_ref"], "head_ref": template["head_ref"]}
    _git(repo, "update-ref", default_refs["base_ref"], base)
    snapshot = _snapshot(tmp_path)
    snapshot_bytes = snapshot.read_bytes()
    sources = [_assessed_source(snapshot)]
    earlier_seal, _ = _seal(repo, tmp_path, _bundle(tmp_path, assessed_sources=sources, **default_refs), output)
    assert earlier_seal.returncode == 0, earlier_seal.stdout + earlier_seal.stderr
    earlier_check = _run(repo, "--input", f"output={output}", "--format", "json", "check")
    assert earlier_check.returncode == 0, earlier_check.stdout + earlier_check.stderr
    earlier_head = _git(repo, "rev-parse", "HEAD")
    (repo / "delta.py").write_text("delta = 1\n", encoding="utf-8")
    _git(repo, "add", "delta.py")
    _git(repo, "commit", "-qm", "rework")
    earlier_artifact = output.read_bytes()
    moved_head = _run(repo, "--input", f"output={output}", "--format", "json", "check")
    assert moved_head.returncode != 0
    moved_head_diagnostic = json.loads(moved_head.stdout)["diagnostics"][0]
    assert moved_head_diagnostic["code"] == "result.target_moved"
    assert "review the delta" in moved_head_diagnostic["required_action"]
    assert any("head_revision" in item for item in moved_head_diagnostic["supporting_evidence"])
    assert output.read_bytes() == earlier_artifact
    assert parse_result(output.read_text(encoding="utf-8"))["head_revision"] == earlier_head
    _git(repo, "merge-base", "--is-ancestor", earlier_head, _git(repo, "rev-parse", "HEAD"))
    _git(repo, "update-ref", default_refs["base_ref"], earlier_head)
    moved_both = _run(repo, "--input", f"output={output}", "--format", "json", "check")
    assert moved_both.returncode != 0
    moved_both_diagnostic = json.loads(moved_both.stdout)["diagnostics"][0]
    assert moved_both_diagnostic["code"] == "result.target_moved"
    for field in ("base_revision", "head_revision"):
        assert any(field in item for item in moved_both_diagnostic["supporting_evidence"])
    _git(repo, "update-ref", default_refs["base_ref"], base)
    delta_bundle = _bundle(
        tmp_path,
        assessed_sources=sources,
        examined=[{"kind": "head-file", "path": "delta.py", "start_line": 1, "end_line": 1}],
        limitations=[f"Delta on {earlier_head}: service.py was not re-inspected."],
        **default_refs,
    )
    delta_seal, _ = _seal(repo, tmp_path, delta_bundle, output)
    assert delta_seal.returncode == 0, delta_seal.stdout + delta_seal.stderr
    assert json.loads(delta_seal.stdout)["result"]["unexamined_changed_paths"] == ["service.py"]
    delta_check = _run(repo, "--input", f"output={output}", "--format", "json", "check")
    assert delta_check.returncode == 0, delta_check.stdout + delta_check.stderr
    _git(repo, "update-ref", default_refs["base_ref"], _git(repo, "rev-parse", "HEAD"))
    moved_base = _run(repo, "--input", f"output={output}", "--format", "json", "check")
    assert moved_base.returncode != 0
    moved_base_diagnostic = json.loads(moved_base.stdout)["diagnostics"][0]
    assert moved_base_diagnostic["code"] == "result.target_moved"
    assert any("base_revision" in item for item in moved_base_diagnostic["supporting_evidence"])
    snapshot.write_text("# Issue 382\nChanged acceptance.\n", encoding="utf-8")
    changed_source = _run(repo, "--input", f"output={output}", "--format", "json", "check")
    assert changed_source.returncode != 0
    changed_source_diagnostic = json.loads(changed_source.stdout)["diagnostics"][0]
    assert changed_source_diagnostic["code"] == "result.stale"
    assert "review the delta" not in changed_source_diagnostic["required_action"]
    snapshot.write_bytes(snapshot_bytes)
    relocated = tmp_path / "relocated"
    shutil.copytree(repo, relocated)
    relocated_output = relocated / output.relative_to(repo)
    relocated_check = _run(relocated, "--input", f"output={relocated_output}", "--format", "json", "check")
    assert relocated_check.returncode != 0
    assert json.loads(relocated_check.stdout)["diagnostics"][0]["code"] == "result.stale"
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

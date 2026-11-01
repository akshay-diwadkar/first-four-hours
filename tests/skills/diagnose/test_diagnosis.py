from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tools.validation.python_test_support import run_python

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "workbench" / "diagnose" / "scripts"
TEMPLATE = ROOT / "skills" / "workbench" / "diagnose" / "templates" / "diagnosis-bundle.json"
sys.path.insert(0, str(SCRIPTS))

import diagnosis_workspace  # noqa: E402


def bundle() -> dict[str, Any]:
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


def _fixture_repo(root: Path) -> None:
    (root / "app").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "app" / "jobs.py").write_text(
        "value = 1\n" * 17 + "retries = retries or DEFAULT_RETRIES\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_jobs.py").write_text("value = 1\n" * 22, encoding="utf-8")


def _bind_to_repo(raw: dict[str, Any], repo: Path) -> None:
    raw["diagnosis_context"]["snapshot"] = {
        "kind": "filesystem",
        "project_root": str(repo.resolve()),
    }
    # Span digests are omitted, so the sealer must compute and record them.
    raw["diagnosis_context"]["material_surfaces"] = [
        {"path": "tests/test_jobs.py", "start_line": 1, "end_line": 2}
    ]


def _bound_bundle(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    _fixture_repo(repo)
    raw = bundle()
    _bind_to_repo(raw, repo)
    source = tmp_path / "bundle.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    return repo, source


def _link_dir(link: Path, target: Path) -> None:
    """Create a directory link: a junction on Windows (no privilege needed), else a symlink."""
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=True)
    else:
        link.symlink_to(target, target_is_directory=True)


def _run_cli(repo: Path, source: Path, slug: str = "example", *extra: str):
    return run_python(
        [
            sys.executable,
            str(SCRIPTS / "cli.py"),
            "--repo-root",
            str(repo),
            "--input",
            f"bundle={source}",
            "--input",
            f"slug={slug}",
            "--format",
            "json",
            *extra,
            "run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_integrated_cli_run_seals_one_artifact_with_path_only_result(tmp_path: Path) -> None:
    repo, source = _bound_bundle(tmp_path)
    output = repo / ".first-four-hours" / "diagnoses" / "example"

    result = _run_cli(repo, source, "Example")

    assert result.returncode == 0, result.stdout + result.stderr
    response = json.loads(result.stdout)
    destination = (output / "diagnosis.md").resolve()
    assert response["status"] == "complete"
    assert response["result"] == {"path": str(destination), "git_ignored": False}
    rendered = destination.read_text(encoding="utf-8")
    # Findings open the diagnosis; its context and the receipt follow the substantive content.
    assert rendered.startswith("# Diagnosis\n\n## Finding ")
    assert rendered.index("## Finding zero-retry-replaced") < rendered.index("## Diagnosis Context")
    assert rendered.index("- Limitations: ") < rendered.index("- Snapshot: ")
    body, _, receipt = rendered.removesuffix("\n").rpartition("\n")
    digest = hashlib.sha256((body + "\n").encode("utf-8")).hexdigest()
    assert receipt == f"<!-- diagnosis: 1.0.3; sha256: {digest} -->"
    evidence_digest = hashlib.sha256(b"retries = retries or DEFAULT_RETRIES\n").hexdigest()
    surface_digest = hashlib.sha256(b"value = 1\nvalue = 1\n").hexdigest()
    assert f'"sha256":"{evidence_digest}"' in rendered
    assert f'"sha256":"{surface_digest}"' in rendered
    assert sorted(path.name for path in output.iterdir()) == ["diagnosis.md"]
    assert not list(tmp_path.rglob(".skill-cli-state.json"))

    # A linked slug directory is refused, so the handoff never lands outside the repository.
    outside = tmp_path / "outside"
    outside.mkdir()
    _link_dir(repo / ".first-four-hours" / "diagnoses" / "linked", outside)
    refused = _run_cli(repo, source, "linked")
    assert refused.returncode != 0, refused.stdout
    assert "is not a real directory" in refused.stdout
    assert list(outside.iterdir()) == []
    # A linked artifact root is refused before anything is written through it.
    rooted = tmp_path / "rooted"
    rooted_outside = tmp_path / "rooted-outside"
    rooted.mkdir()
    rooted_outside.mkdir()
    _link_dir(rooted / ".first-four-hours", rooted_outside)
    with pytest.raises(diagnosis_workspace.WorkspaceError, match="is not a real directory"):
        diagnosis_workspace.prepare_workspace(rooted, "rooted")
    assert list(rooted_outside.iterdir()) == []

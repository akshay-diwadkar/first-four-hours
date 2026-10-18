from __future__ import annotations

import json
import sys
from pathlib import Path

from tools.validation.git_test_support import seed_git

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "workbench" / "construct" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import blueprint_runtime  # noqa: E402
import run_verification as runner  # noqa: E402

DRAFT = """<!-- blueprint-contract: 1.0.0 -->
# Blueprint: {name}

## Goal
Make absent names normalize predictably.

## Current State
The seam returns raw input.
**Source:** `src/names.py:1`

## Implementation

### 1. Normalize absent names
**Location:** `src/names.py::normalize`
**State:** existing

Return the requested empty value for an absent name and preserve present names.

### 2. Add the focused regression
**Location:** `tests/test_names.py`
**State:** new

Add the absent-name case next to the existing normalization tests.

## Verification

### After implementation
Run: `python tests/test_names.py`
Expect: exit 0 and the absent-name case passes.

## Completion Conditions
- Absent names normalize to the requested empty value.
- Present names and unrelated callers are unchanged.
"""


def _init_git(repo: Path, tracked: dict[str, str] | None = None) -> None:
    seed_git(repo, tracked or {"seed.txt": "seed\n"})


def _seal(repo: Path, name: str, draft: str) -> Path:
    blueprint = repo / ".first-four-hours" / "blueprints" / name / "blueprint.md"
    blueprint.parent.mkdir(parents=True)
    request = blueprint.with_name("request.md")
    request.write_text("Normalize absent names.\n", encoding="utf-8")
    blueprint.write_text(draft, encoding="utf-8")
    sealed = blueprint_runtime.seal_blueprint(repo, request, blueprint)
    blueprint.write_text(sealed.text, encoding="utf-8")
    return blueprint


def _repo(tmp_path: Path, name: str = "repo", tracked: dict[str, str] | None = None) -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _init_git(repo, tracked or {"src/names.py": "def normalize(value):\n    return value\n"})
    return repo


def _run_phase(capsys: pytest.CaptureFixture[str], repo: Path, blueprint: Path, phase: str) -> tuple[int, dict]:
    code = runner.main(["--repo-root", str(repo), "--blueprint", str(blueprint), "--phase", phase])
    captured = capsys.readouterr()
    return code, json.loads(captured.out)


def _tmp_json_files(tmp_path: Path) -> list[Path]:
    return [path for path in tmp_path.rglob("*") if path.is_file() and path.suffix == ".json"]


def test_tampered_seal_receipt_fails_closed(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path)
    blueprint = _seal(repo, "tampered", DRAFT.format(name="tampered"))
    before = blueprint.read_bytes()
    with monkeypatch.context() as environment:
        environment.setenv("PATH", "")
        code, payload = _run_phase(capsys, repo, blueprint, "before")
    diagnostic = payload["diagnostics"][0]
    assert (code, diagnostic["code"], diagnostic["category"]) == (3, "workspace.git_failed", "unsafe_state")
    assert blueprint.read_bytes() == before
    lines = blueprint.read_text(encoding="utf-8").splitlines()
    assert lines[-2].startswith("<!-- " "blueprint-proof: ")
    tampered = lines[-2].replace("repository_id", "repository_ID", 1)
    blueprint.write_text("\n".join([*lines[:-2], tampered, lines[-1]]) + "\n", encoding="utf-8")
    code, payload = _run_phase(capsys, repo, blueprint, "before")
    assert code == 3
    assert payload["diagnostics"][0]["code"] == "blueprint.invalid"
    assert _tmp_json_files(tmp_path) == []
    # An older sealed contract is named precisely before any receipt check.
    blueprint.write_text("\n".join(["<!-- blueprint-contract: 5 -->", *lines[1:]]), encoding="utf-8")
    code, payload = _run_phase(capsys, repo, blueprint, "after")
    assert (code, payload["diagnostics"][0]["code"]) == (3, "contract.unsupported")
    assert "contract 5" in payload["diagnostics"][0]["message"]
    # A sealed contract of another major is named the same way.
    blueprint.write_text("\n".join(["<!-- " "blueprint-contract: 2.0.0 -->", *lines[1:]]), encoding="utf-8")
    code, payload = _run_phase(capsys, repo, blueprint, "after")
    assert (code, payload["diagnostics"][0]["code"]) == (3, "contract.unsupported")
    assert "contract 2.0.0 " in payload["diagnostics"][0]["message"]
    # A sealed plan from another minor of the same Blueprint major passes Construct verification, but a draft must carry exactly this runtime's marker.
    minor_repo = _repo(tmp_path, "minor")
    minor_draft = DRAFT.format(name="minor").replace("blueprint-contract: 1.0.0 -->", "blueprint-contract: 1.4.0 -->", 1)
    with monkeypatch.context() as producer:
        producer.setattr(blueprint_runtime, "CONTRACT_VERSION", "1.4.0")
        producer.setattr(blueprint_runtime, "CONTRACT_MARKER", "<!-- " "blueprint-contract: 1.4.0 -->")
        minor = _seal(minor_repo, "minor", minor_draft)
    assert blueprint_runtime.CONTRACT_VERSION == "1.0.0"
    minor_lines = minor.read_text(encoding="utf-8").splitlines()
    assert minor_lines[0] == "<!-- " "blueprint-contract: 1.4.0 -->"
    assert json.loads(minor_lines[-2].removeprefix("<!-- " "blueprint-proof: ").removesuffix(" -->"))["version"] == "1.4.0"
    assert minor_lines[-1].startswith("<!-- " "blueprint-validation: 1.4.0; ")
    code, payload = _run_phase(capsys, minor_repo, minor, "before")
    assert (code, payload["verification"]["results"]) == (0, []), payload
    future = DRAFT.format(name="future").replace("blueprint-contract: 1.0.0 -->", "blueprint-contract: 1.4.0 -->", 1)
    assert future != DRAFT.format(name="future")
    with pytest.raises(ValueError):
        _seal(repo, "future", future)

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "tools" / "skill_cli.py"
RESPONSE_SCHEMA = json.loads((ROOT / "tools" / "skill_protocol" / "response.schema.json").read_text())


def create_skill(tmp_path: Path, payload: dict[str, Any]) -> Path:
    skill = tmp_path / "fixture-skill"
    scripts = skill / "scripts"
    scripts.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: fixture-skill\ndescription: Fixture.\nversion: 1.0.0\n---\n",
        encoding="utf-8",
    )
    (skill / "skill-protocol.json").write_text(json.dumps(payload), encoding="utf-8")
    return skill


def invoke(skill: Path, repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--skill-dir",
            str(skill),
            "--repo-root",
            str(repo),
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def json_result(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert result.stderr == ""
    assert result.stdout.endswith("\n")
    assert result.stdout.count("\n") == 1
    payload = json.loads(result.stdout)
    jsonschema.validate(payload, RESPONSE_SCHEMA)
    return payload


def test_stateless_run_returns_inline_result_without_state(tmp_path: Path) -> None:
    payload = {
        "protocol_version": "1.0.0",
        "mode": "stateless",
        "skill": "fixture-skill",
        "minimum_python": "3.11",
        "run_dir_policy": "outside_skill",
        "requirements": [],
        "inputs": [
            {
                "name": "request",
                "kind": "string",
                "required": True,
                "repeatable": False,
                "description": "Request.",
                "choices": [],
            }
        ],
        "artifacts": [],
        "phases": {},
        "commands": {
            "run": {
                "allowed_phases": [],
                "success_phase": None,
                "steps": [
                    {
                        "argv": ["{python}", "{skill_dir}/scripts/workflow.py", "{input.request}"],
                        "repeat": [],
                        "capture_stdout": None,
                        "diagnostics_json": False,
                        "failure": "blocked",
                    }
                ],
            }
        },
    }
    skill = create_skill(tmp_path, payload)
    (skill / "scripts" / "workflow.py").write_text(
        "import json, sys\nprint(json.dumps({'request': sys.argv[1]}))\n",
        encoding="utf-8",
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    result = invoke(skill, repo, "--input", "request=route me", "--format", "json", "run")
    response = json_result(result)
    assert result.returncode == 0
    assert response["status"] == "complete"
    assert response["result"] == {"request": "route me"}
    assert not list(tmp_path.rglob(".skill-cli-state.json"))

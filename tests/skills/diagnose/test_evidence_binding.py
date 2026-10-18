from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any



ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "workbench" / "diagnose" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import diagnosis_bundle  # noqa: E402


def _normalized_span(payload: bytes, start: int, end: int) -> bytes:
    text = payload.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    if not text:
        lines: list[str] = []
    else:
        parts = text.split("\n")
        lines = [part + "\n" for part in parts[:-1]]
        if parts[-1]:
            lines.append(parts[-1])
    return "".join(lines[start - 1 : end]).encode("utf-8")


def _digest(payload: bytes, start: int = 1, end: int = 1) -> str:
    return hashlib.sha256(_normalized_span(payload, start, end)).hexdigest()


def _fixture_repo(repo: Path) -> None:
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "service.py").write_bytes(b"first\r\nsecond\r\nthird\r\n")


def _snapshot(repo: Path) -> dict[str, str]:
    return {"kind": "filesystem", "project_root": str(repo.resolve())}


def _bundle(repo: Path, *, snapshot: dict[str, str] | None = None) -> dict[str, Any]:
    source = (repo / "src" / "service.py").read_bytes()
    return {
        "schema_version": "1.0.0",
        "diagnosis_context": {
            "target": "fixture-service",
            "snapshot": snapshot or _snapshot(repo),
            "evidence_root": None,
            "material_surfaces": [],
            "limitations": [],
            "ruled_out": [],
            "open_probes": [],
        },
        "findings": [
            {
                "id": "second-line",
                "title": "Second line is material",
                "summary": "The second line demonstrates the fixture behavior.",
                "cause_or_boundary": "The fixture deliberately exposes the line.",
                "impact": "A stale line would invalidate the observation.",
                "cause_status": "inferred",
                "evidence": [
                    {
                        "kind": "source",
                        "path": "src/service.py",
                        "start_line": 2,
                        "end_line": 2,
                        "sha256": _digest(source, 2, 2),
                        "observation": "The normalized second line is current.",
                    }
                ],
            }
        ],
    }


def _bind(bundle: dict[str, Any], repo: Path):
    errors, proof = diagnosis_bundle.validate_diagnosis_bindings(bundle, repo)
    return errors, proof


def test_authored_digest_drift_is_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _fixture_repo(repo)
    captures = tmp_path / "evidence"
    captures.mkdir()
    capture = captures / "timings.txt"
    capture.write_bytes(b"stage predict 240 min\r\nstage load 2 min\r\n")
    bundle = _bundle(repo)
    bundle["diagnosis_context"]["evidence_root"] = str(captures.resolve())
    bundle["findings"][0]["evidence"].append(
        {
            "kind": "capture",
            "path": "timings.txt",
            "sha256": hashlib.sha256(capture.read_bytes()).hexdigest(),
            "provenance": "user-supplied",
            "origin": "user-run timing probe",
            "observation": "Predict owns the runtime gap.",
        }
    )
    bundle["findings"][0]["evidence"].append(
        {
            "kind": "capture",
            "path": "timings.txt",
            "start_line": 2,
            "end_line": 2,
            "sha256": _digest(capture.read_bytes(), 2, 2),
            "provenance": "user-supplied",
            "origin": "user-run timing probe",
            "observation": "Model load is not the gap.",
        }
    )

    errors, _proof = _bind(bundle, repo)
    assert errors == []

    # An authored span digest is checked, never overwritten by the sealer.
    authored = bundle["findings"][0]["evidence"][0]["sha256"]
    bundle["findings"][0]["evidence"][0]["sha256"] = _digest((repo / "src" / "service.py").read_bytes(), 1, 1)
    errors, _proof = _bind(bundle, repo)
    assert errors == ["findings[0].evidence[0].sha256 does not match the normalized declared span"]
    # Only an absent key is derived: an explicit null span digest is malformed.
    bundle["findings"][0]["evidence"][0]["sha256"] = None
    errors, _proof = _bind(bundle, repo)
    assert errors == ["findings[0].evidence[0].sha256 must be a lowercase SHA-256 digest"]
    bundle["findings"][0]["evidence"][0]["sha256"] = authored
    # Capture digests stay authored.
    capture_digest = bundle["findings"][0]["evidence"][1].pop("sha256")
    errors, _proof = _bind(bundle, repo)
    assert errors == ["findings[0].evidence[1].sha256 must be a lowercase SHA-256 digest"]
    bundle["findings"][0]["evidence"][1]["sha256"] = capture_digest

    capture.write_bytes(b"stage predict 60 min\r\nstage load 2 min\r\n")
    errors, _proof = _bind(bundle, repo)
    assert errors == [
        "findings[0].evidence[1].sha256 does not match the declared capture bytes"
    ]

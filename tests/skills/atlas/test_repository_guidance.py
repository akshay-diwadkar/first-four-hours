from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills" / "workbench" / "atlas"
FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(SKILL / "scripts"))

from repository_guidance import apply_guidance, guidance_lines, managed_block  # noqa: E402


def test_setup_spaces_block_and_remove_restores_bytes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "valid-simple", root)
    agents, claude = root / "AGENTS.md", root / "CLAUDE.md"
    agents_original = b"# Rules\nKeep tests small. <!-- ATLASSIAN notes --> <!-- ATLAS 2026 roadmap -->\n"
    claude_original = b"# Rules\r\nNo trailing newline."
    agents.write_bytes(agents_original)
    claude.write_bytes(claude_original)
    lines = guidance_lines(root)

    def apply(operation: str) -> None:
        report, diagnostics = apply_guidance(root, operation)
        assert diagnostics == [], diagnostics
        assert report["status"] == "complete"

    def run() -> tuple[int, dict]:
        result = subprocess.run(
            [sys.executable, "-B", str(SKILL / "scripts" / "structure_state.py"), "--repo-root", str(root)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return result.returncode, json.loads(result.stdout)

    spaced = agents_original + b"\n" + managed_block(b"\n", 1, lines=lines)
    apply("setup")
    assert agents.read_bytes() == spaced
    assert claude.read_bytes() == claude_original + b"\r\n\r\n" + managed_block(b"\r\n", 2, lines=lines)
    landmark = "- [Authentication](.map/auth/LANDMARK.md) — read for request identity and authorization.".encode()
    lead = (
        "Atlas `setup-guidance` copied the rest of this section from `MAP.md`: follow only relevant links, "
        "and search project files directly when none fits. Update affected map pointers when files move or "
        "change meaning, and rerun `setup-guidance` after editing `MAP.md`; run Atlas `check`/`baseline` only "
        "for drift audits."
    ).encode()
    assert landmark in agents.read_bytes() and lead in agents.read_bytes()
    assert b"# Repository Map" not in agents.read_bytes()
    apply("setup")
    assert agents.read_bytes() == spaced

    agents.write_bytes(spaced + b"## Later\n")
    followed = agents_original + b"\n" + managed_block(b"\n", 1, 1, lines=lines) + b"## Later\n"
    apply("setup")
    assert agents.read_bytes() == followed
    apply("setup")
    assert agents.read_bytes() == followed
    apply("remove")
    assert agents.read_bytes() == agents_original + b"## Later\n"
    assert claude.read_bytes() == claude_original

    agents.write_bytes(b"# Rules\n<!-- BEGIN ATLAS prefix=none -->\nold text\n<!-- END ATLAS -->\n")
    apply("setup")
    assert agents.read_bytes() == b"# Rules\n\n" + managed_block(b"\n", 1, lines=lines)
    apply("remove")
    assert agents.read_bytes() == b"# Rules\n"

    agents.write_bytes(
        b"# Rules\n\n<!-- BEGIN ATLAS prefix=crlf suffix=lf -->\nold text\n<!-- END ATLAS -->\n\n## Later\n"
    )
    apply("remove")
    assert agents.read_bytes() == b"# Rules\n## Later\n"

    normalized = b"# Rules\r\n\r\n" + managed_block(b"\r\n", 1, 1, lines=lines) + b"## Later\r\n"
    claude.write_bytes(normalized)
    apply("setup")
    assert claude.read_bytes() == normalized
    apply("remove")
    assert claude.read_bytes() == b"# Rules\r\n## Later\r\n"

    block_free, claude_free = agents.read_bytes(), claude.read_bytes()
    apply("setup")
    assert run()[0] == 0
    map_file = root / "MAP.md"
    original_map = map_file.read_bytes()
    map_file.write_bytes(original_map.replace(b"read for request identity", b"follow for request identity"))
    code, payload = run()
    assert code == 3, payload
    assert [item["code"] for item in payload["diagnostics"]] == ["map.guidance_stale"] * 2, payload
    assert sorted(item["path"] for item in payload["diagnostics"]) == ["AGENTS.md", "CLAUDE.md"], payload
    apply("setup")
    assert run()[0] == 0

    pointer = b"read `MAP.md` and follow only relevant links"
    head = b"# Repository Map\n\n" + landmark + b"\n\n"
    paragraph = b"x" * (2000 - len(landmark) - 2)
    map_file.write_bytes(head + paragraph + b"\n")
    apply("setup")
    assert paragraph in agents.read_bytes()
    map_file.write_bytes(head + paragraph + b"x\n")
    apply("setup")
    assert pointer in agents.read_bytes() and paragraph not in agents.read_bytes()

    map_file.write_bytes(original_map + b"<!-- note -->\n")
    apply("setup")
    assert pointer in agents.read_bytes() and b"<!-- note -->" not in agents.read_bytes()
    apply("remove")
    assert agents.read_bytes() == block_free

    map_file.write_bytes(original_map)
    agents.write_bytes(block_free + b"\n" + managed_block(b"\n", 1))
    claude.write_bytes(claude_free + b"\r\n" + managed_block(b"\r\n", 1))
    assert run()[0] == 0

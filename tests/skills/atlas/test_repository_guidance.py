from __future__ import annotations

import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills" / "workbench" / "atlas"
FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(SKILL / "scripts"))

from repository_guidance import apply_guidance, managed_block  # noqa: E402


def test_setup_spaces_block_and_remove_restores_bytes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "valid-simple", root)
    agents, claude = root / "AGENTS.md", root / "CLAUDE.md"
    agents_original = b"# Rules\nKeep tests small. <!-- ATLASSIAN notes --> <!-- ATLAS 2026 roadmap -->\n"
    claude_original = b"# Rules\r\nNo trailing newline."
    agents.write_bytes(agents_original)
    claude.write_bytes(claude_original)

    def apply(operation: str) -> None:
        report, diagnostics = apply_guidance(root, operation)
        assert diagnostics == [], diagnostics
        assert report["status"] == "complete"

    spaced = agents_original + b"\n" + managed_block(b"\n", 1)
    apply("setup")
    assert agents.read_bytes() == spaced
    assert claude.read_bytes() == claude_original + b"\r\n\r\n" + managed_block(b"\r\n", 2)
    apply("setup")
    assert agents.read_bytes() == spaced

    agents.write_bytes(spaced + b"## Later\n")
    followed = agents_original + b"\n" + managed_block(b"\n", 1, 1) + b"## Later\n"
    apply("setup")
    assert agents.read_bytes() == followed
    apply("setup")
    assert agents.read_bytes() == followed
    apply("remove")
    assert agents.read_bytes() == agents_original + b"## Later\n"
    assert claude.read_bytes() == claude_original

    agents.write_bytes(b"# Rules\n<!-- BEGIN ATLAS prefix=none -->\nold text\n<!-- END ATLAS -->\n")
    apply("setup")
    assert agents.read_bytes() == b"# Rules\n\n" + managed_block(b"\n", 1)
    apply("remove")
    assert agents.read_bytes() == b"# Rules\n"

    agents.write_bytes(
        b"# Rules\n\n<!-- BEGIN ATLAS prefix=crlf suffix=lf -->\nold text\n<!-- END ATLAS -->\n\n## Later\n"
    )
    apply("remove")
    assert agents.read_bytes() == b"# Rules\n## Later\n"

    normalized = b"# Rules\r\n\r\n" + managed_block(b"\r\n", 1, 1) + b"## Later\r\n"
    claude.write_bytes(normalized)
    apply("setup")
    assert claude.read_bytes() == normalized
    apply("remove")
    assert claude.read_bytes() == b"# Rules\r\n## Later\r\n"

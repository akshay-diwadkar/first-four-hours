from __future__ import annotations

import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills" / "workbench" / "atlas"
FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(SKILL / "scripts"))

from repository_guidance import MAP_AUTHORITY, apply_guidance, managed_block, map_lines  # noqa: E402
from structure_state import analyze, run_checks  # noqa: E402


def test_setup_spaces_block_and_remove_restores_bytes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "valid-simple", root)
    agents, claude = root / "AGENTS.md", root / "CLAUDE.md"
    landmark_file = root / ".map/auth/LANDMARK.md"
    agents_original = b"# Rules\nKeep tests small. <!-- ATLASSIAN notes --> <!-- ATLAS 2026 roadmap -->\n"
    claude_original = b"# Rules\r\nNo trailing newline."
    agents.write_bytes(agents_original)
    claude.write_bytes(claude_original)
    landmark_file.write_text(
        "# Authentication\n\nRoute through request identity\nand authorization concepts.\n\n"
        "- [Request authentication](request-auth.md) — read when a request establishes a principal.\n",
        encoding="utf-8",
    )
    lines = map_lines(analyze(root)[1])

    def apply(operation: str) -> None:
        report, diagnostics = apply_guidance(root, operation)
        assert diagnostics == [], diagnostics
        assert report["status"] == "complete"

    def checks() -> list[tuple[str, str]]:
        return [(str(item["code"]), str(item["path"])) for item in run_checks(root)[1]]

    spaced = agents_original + b"\n" + managed_block(b"\n", 1, 0, lines)
    apply("setup")
    assert agents.read_bytes() == spaced
    assert claude.read_bytes() == claude_original + b"\r\n\r\n" + managed_block(b"\r\n", 2, 0, lines)
    entry = b"- [Authentication](.map/auth/LANDMARK.md): Route through request identity and authorization concepts."
    assert entry in agents.read_bytes() and MAP_AUTHORITY.encode() in agents.read_bytes()
    apply("setup")
    assert agents.read_bytes() == spaced

    agents.write_bytes(spaced + b"## Later\n")
    followed = agents_original + b"\n" + managed_block(b"\n", 1, 1, lines) + b"## Later\n"
    apply("setup")
    assert agents.read_bytes() == followed
    apply("setup")
    assert agents.read_bytes() == followed
    apply("remove")
    assert agents.read_bytes() == agents_original + b"## Later\n"
    assert claude.read_bytes() == claude_original

    agents.write_bytes(b"# Rules\n<!-- BEGIN ATLAS prefix=none -->\nold text\n<!-- END ATLAS -->\n")
    apply("setup")
    assert agents.read_bytes() == b"# Rules\n\n" + managed_block(b"\n", 1, 0, lines)
    apply("remove")
    assert agents.read_bytes() == b"# Rules\n"

    agents.write_bytes(
        b"# Rules\n\n<!-- BEGIN ATLAS prefix=crlf suffix=lf -->\nold text\n<!-- END ATLAS -->\n\n## Later\n"
    )
    apply("remove")
    assert agents.read_bytes() == b"# Rules\n## Later\n"

    normalized = b"# Rules\r\n\r\n" + managed_block(b"\r\n", 1, 1, lines) + b"## Later\r\n"
    claude.write_bytes(normalized)
    apply("setup")
    assert claude.read_bytes() == normalized
    apply("remove")
    assert claude.read_bytes() == b"# Rules\r\n## Later\r\n"

    block_free, claude_free = agents.read_bytes(), claude.read_bytes()
    apply("setup")
    assert checks() == []

    # Spacing around the block and newline style inside it are not Map drift, though setup rewrites both.
    agents.write_bytes(agents.read_bytes() + b"## Later\n")
    claude_payload = claude.read_bytes()
    begin, end = claude_payload.index(b"<!-- ATLAS"), claude_payload.index(b"<!-- /ATLAS -->")
    claude.write_bytes(claude_payload[:begin] + claude_payload[begin:end].replace(b"\r\n", b"\n") + claude_payload[end:])
    respaced, renormalized = agents.read_bytes(), claude.read_bytes()
    assert checks() == []
    apply("setup")
    assert agents.read_bytes() != respaced and claude.read_bytes() != renormalized

    landmark_file.write_text(
        landmark_file.read_text(encoding="utf-8").replace("Route through", "Follow for"), encoding="utf-8"
    )
    assert sorted(checks()) == [("map.map_stale", "AGENTS.md"), ("map.map_stale", "CLAUDE.md")]
    apply("setup")
    assert checks() == []
    lines = map_lines(analyze(root)[1])
    agents.write_bytes(block_free + b"\n" + managed_block(b"\n", 1, 0, lines[:-1]))
    assert checks() == [("map.map_stale", "AGENTS.md")]
    # Atlas 1.0.0's pointer block is rejection evidence: it gets no exemption.
    pointer = (
        "## Atlas",
        "",
        "Before project work, read `MAP.md` and follow only relevant links; project files are authoritative, "
        "so search directly when no link fits. Update affected map pointers when files move or change meaning; "
        "run Atlas `check`/`baseline` only for drift audits.",
    )
    agents.write_bytes(block_free + b"\n" + managed_block(b"\n", 1, 0, pointer))
    assert checks() == [("map.map_stale", "AGENTS.md")]
    apply("setup")

    claude.unlink()
    assert checks() == [("map.map_missing", "CLAUDE.md")]
    claude.write_bytes(b"# Rules\n<!-- OPT-OUT ATLAS -->\n")
    assert checks() == []
    agents.write_bytes(agents.read_bytes() + b"<!-- ATLAS -->\n")
    assert checks() == [("map.map_unreadable", "AGENTS.md")]

    agents.write_bytes(block_free)
    apply("setup")
    landmark_file.write_text(
        landmark_file.read_text(encoding="utf-8").replace("Follow for", "[x](x.md) Follow for"), encoding="utf-8"
    )
    before = agents.read_bytes(), claude.read_bytes()
    _report, diagnostics = apply_guidance(root, "setup")
    assert [item["code"] for item in diagnostics] == ["map.guidance_setup_requires_valid_map"], diagnostics
    assert (agents.read_bytes(), claude.read_bytes()) == before

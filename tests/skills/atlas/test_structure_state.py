from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills" / "workbench" / "atlas"
sys.path.insert(0, str(SKILL / "scripts"))

from freshness_state import assess, scan_repository  # noqa: E402
from structure_state import validate  # noqa: E402


def _write(root: Path, files: dict[str, str]) -> Path:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _codes(root: Path) -> list[str]:
    return [str(item["code"]) for item in validate(root)[1]]


def _directory_link(link: Path, target: Path) -> None:
    if sys.platform == "win32":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    else:
        link.symlink_to(target, target_is_directory=True)


def test_project_boundaries_are_refused(tmp_path: Path) -> None:
    outside = _write(tmp_path / "outside/auth", {"LANDMARK.md": "# External\n", "sessions.md": "# External\n"})
    root = _write(
        tmp_path / "repo",
        {
            "MAP.md": "[Auth](.map/auth/LANDMARK.md)\n[Code](.map/code/LANDMARK.md)\n",
            ".map/code/LANDMARK.md": "# Code\n\n- [Sources](sources.md) — read for application entrypoints.\n",
            ".map/code/sources.md": "# Sources\n\n- [Source tree](../../src/) — application code.\n",
            "src/app.py": "print('app')\n",
        },
    )
    _directory_link(root / ".map/auth", outside)
    codes = _codes(root)
    assert "map.path_outside_repository" in codes
    assert "map.source_link_directory_unsupported" in codes

    _directory_link(root / "linked", outside)
    manifest, _excluded, diagnostics = scan_repository(root.resolve(), [])
    assert not [path for path in manifest if path.startswith("linked/")], manifest
    assert "map.freshness_symlink_unsafe" in [str(item["code"]) for item in diagnostics]

    _directory_link(root / "inner", root / "src")
    manifest, _excluded, diagnostics = scan_repository(root.resolve(), [])
    assert "src/app.py" in manifest
    assert not [path for path in manifest if path.startswith("inner/")], manifest
    assert "map.freshness_directory_symlink_unsupported" in [str(item["code"]) for item in diagnostics]
    _report, diagnostics = assess(root)
    assert "map.source_link_directory_unsupported" in [str(item["code"]) for item in diagnostics]

    entry = _write(
        tmp_path / "entry",
        {
            "MAP.md": "[Docs](.map/docs/LANDMARK.md)\n",
            ".map/docs/LANDMARK.md": "# Docs\n\n- [Entry](entry.md) — read for entry points.\n",
            ".map/docs/entry.md": (
                "# Entry\n\n"
                "- [Start](../../docs/guide.md#start-here) — emphasized heading.\n"
                "- [Steps](../../docs/guide.md#steps-1) — repeated heading.\n"
                "- [Owned](../../docs/guide.md#_owned) — code-span heading.\n"
                "- [Fenced](../../docs/guide.md#fenced) — heading only inside a fence.\n"
                "- [`authenticate` entry](../../src/app.py) — present symbol.\n"
                "- [`authorize` check](../../src/app.py) — substring only.\n"
                "- [App](../../src/app.py) — starts at `authorise_all`.\n"
                "- [App again](../../src/app.py) and [guide](../../docs/guide.md) mention `absent_name`.\n"
            ),
            "docs/guide.md": (
                "# Guide\n\n## Start _here_\n\n## Steps\n\n## Steps\n\n## `_owned`\n\n"
                "```text\n## Fenced\n```\n"
            ),
            "src/app.py": "def authenticate():\n    return 'authorized'\n",
        },
    )
    diagnostics = validate(entry)[1]
    fragments = [str(item["message"]) for item in diagnostics if item["code"] == "map.link_fragment_missing"]
    symbols = [str(item["message"]) for item in diagnostics if item["code"] == "map.cue_symbol_missing"]
    assert len(fragments) == 1 and "#fenced" in fragments[0], diagnostics
    assert len(symbols) == 2, diagnostics
    assert any("`authorize`" in message for message in symbols), symbols
    assert any("`authorise_all`" in message for message in symbols), symbols

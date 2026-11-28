from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from tools.validation.python_test_support import run_python

REPO_ROOT = Path(__file__).resolve().parents[3]
CLI = REPO_ROOT / "skills" / "workbench" / "canon" / "scripts" / "cli.py"

PARTS: list[tuple[str, list[str]]] = [
    ("Character", ["Thesis", "Personality", "Voice"]),
    ("Media", ["Website", "App", "Document", "Slide deck"]),
    ("System", ["Type", "Colour", "Spacing", "Components", "Motion", "Imagery"]),
    ("Viewing contexts", []),
    ("States", ["Empty", "Error", "Loading", "Dense data", "Long tables", "Charts", "Footnotes"]),
    ("Banned", []),
    ("Samples", []),
    ("Governs", []),
    ("Change log", []),
]
LEAF_BODIES = {
    "Samples": "- ![home](samples/home.png)\n",
    "Governs": "- `site/**`\n",
    "Change log": "- 2026-11-28: first canon Reason: approved direction\n",
}
RULE_MESSAGE = '{path}: entry 1 must state a rule and then "Reason: why"'
SAMPLES = "Samples: entry {n} must be one relative link to a file inside the canon folder"
GOVERNS = "Governs: entry {n} must be one relative path or glob in backticks"
CHANGES = 'Change log: entry {n} must read "YYYY-MM-DD: what changed Reason: why"'


def _paths() -> list[str]:
    paths: list[str] = []
    for section, children in PARTS:
        paths.extend(f"{section} > {child}" for child in children) if children else paths.append(section)
    return paths


def _body(path: str, mode: str) -> str:
    name = path.rsplit(" > ", 1)[-1]
    if mode == "hollow":
        return ""
    if name == "Thesis":
        return "Quiet, exact, warm.\n"
    if mode == "bare":
        return "- x\n"
    if name == "Personality":
        return "- calm\n"
    if name == "Voice":
        return "- Voice rule.\n  Reason: Voice reason.\n"
    if name in LEAF_BODIES:
        return LEAF_BODIES[name]
    body = f"- {name} rule. Reason: {name} reason.\n"
    if name == "Components":
        body += "\n```text\n## Banned\n- no reason here\n```\n"
    return body


def _canon(mode: str = "complete") -> str:
    lines = ["# Shop canon\n"]
    for section, children in PARTS:
        lines.append(f"\n## {section}\n")
        for path in [f"{section} > {child}" for child in children] or [section]:
            if children:
                lines.append(f"\n### {path.rsplit(' > ', 1)[-1]}\n")
            body = _body(path, mode)
            if body:
                lines.append("\n" + body)
    if mode == "complete":
        lines.append("\n## Notes\n\nFree text.\n")
    return "".join(lines)


def _files(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def _check(root: Path, canon: Path, content: str | bytes) -> tuple[int, dict[str, Any]]:
    if isinstance(content, bytes):
        canon.write_bytes(content)
    else:
        canon.write_text(content, encoding="utf-8")
    before = _files(root)
    argv = [sys.executable, str(CLI), "--repo-root", str(root), "--input", f"canon={canon}", "--format", "json", "check"]
    done = run_python(argv, capture_output=True, text=True, check=False)
    assert _files(root) == before
    return done.returncode, json.loads(done.stdout)


def _assert_blocked(result: tuple[int, dict[str, Any]], expected: list[str]) -> None:
    code, envelope = result
    assert code == 3 and envelope["status"] == "blocked", envelope
    lines = envelope["diagnostics"][0]["message"].splitlines()
    assert len(lines) == len(expected) and set(lines) == set(expected), lines


def test_check_accepts_a_complete_canon_and_names_each_missing_or_malformed_part(tmp_path: Path) -> None:
    folder = tmp_path / ".canon" / "shop"
    (folder / "samples").mkdir(parents=True)
    (folder / "samples" / "home.png").write_bytes(b"png")
    (tmp_path / ".canon" / "outside.png").write_bytes(b"png")
    canon = folder / "canon.md"
    complete = _canon()

    code, envelope = _check(tmp_path, canon, complete)
    assert code == 0 and envelope["status"] == "complete", envelope
    assert envelope["result"] == {"canon": str(canon.resolve()), "valid": True}

    missing = []
    for section, children in PARTS:
        missing.append(f"missing section: {section}")
        missing.extend(f"missing section: {section} > {child}" for child in children)
    assert len(missing) == 29
    _assert_blocked(_check(tmp_path, canon, "# Shop canon\n"), missing)

    hollow = ["Character > Thesis: has no text"] + [f"{path}: has no entries" for path in _paths() if path != "Character > Thesis"]
    assert len(hollow) == 25
    _assert_blocked(_check(tmp_path, canon, _canon("hollow")), hollow)

    rules = [path for path in _paths() if path not in ("Character > Thesis", "Character > Personality", *LEAF_BODIES)]
    assert len(rules) == 20
    bare = [RULE_MESSAGE.format(path=path) for path in rules] + [SAMPLES.format(n=1), GOVERNS.format(n=1), CHANGES.format(n=1)]
    _assert_blocked(_check(tmp_path, canon, _canon("bare")), bare)

    malformed = complete
    for old, new in (
        ("Quiet, exact, warm.\n", ""),
        ("- Voice rule.\n  Reason: Voice reason.\n", "- Voice rule.\n"),
        ("- App rule. Reason: App reason.\n", ""),
        ("### Motion\n", "### Motion\n\n### Motion\n"),
        ("\n### Charts\n\n- Charts rule. Reason: Charts reason.\n", ""),
        ("- ![home](samples/home.png)\n", "- [up](../outside.png)\n- [gone](samples/missing.png)\n"),
        ("- `site/**`\n", "- `/site/**`\n- `site\\**`\n- `c:site/**`\n- `site/../x`\n- ` `\n- `site/**` and `docs/**`\n"),
        (
            LEAF_BODIES["Change log"],
            "- added colour Reason: approved\n"
            "- 20261128: compact date Reason: approved\n"
            "- 2026-02-30: impossible date Reason: approved\n"
            "- 2026-11-28:  Reason: approved\n"
            "- 2026-11-28: blank reason Reason:\n",
        ),
        ("- calm\n", "- \n"),
        ("- Type rule. Reason: Type reason.\n", "- Type rule. Reason:\n"),
        ("- Colour rule. Reason: Colour reason.\n", "- Reason: Colour reason.\n"),
    ):
        assert malformed.count(old) == 1, old
        malformed = malformed.replace(old, new)
    malformed += "\n## Banned\n\n- no reason here\n"
    _assert_blocked(
        _check(tmp_path, canon, malformed),
        [
            "Character > Thesis: has no text",
            "Character > Personality: entry 1 has no text",
            RULE_MESSAGE.format(path="Character > Voice"),
            RULE_MESSAGE.format(path="System > Type"),
            RULE_MESSAGE.format(path="System > Colour"),
            "Media > App: has no entries",
            "duplicate section: System > Motion",
            "missing section: States > Charts",
            SAMPLES.format(n=1),
            SAMPLES.format(n=2),
            *[GOVERNS.format(n=n) for n in range(1, 7)],
            *[CHANGES.format(n=n) for n in range(1, 6)],
            "duplicate section: Banned",
        ],
    )
    _assert_blocked(
        _check(tmp_path, canon, b"\xff\xfe# Shop canon\n"),
        [f"canon must be a UTF-8 text file: {canon.resolve()}"],
    )

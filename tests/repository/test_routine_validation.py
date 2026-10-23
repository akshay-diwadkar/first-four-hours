from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "validation"))

import validate_repository as validator  # noqa: E402
from context_tokenizer import count_tokens  # noqa: E402
from instruction_rules import INVENTORY, inventory_errors  # noqa: E402

SKILL = "skills/workbench/blueprint"


def _draft(*blocks: tuple[str, str, tuple[str, ...]]) -> str:
    # One instruction whose Locations each carry an Exact block: a new file's
    # whole text, or the replaced text then its replacement.
    lines = ["# Budget probe", "", "## Implementation", "", "### 1. Edit guidance"]
    for path, state, texts in blocks:
        lines += ["", f"**Location:** `{path}`", f"**State:** {state}", "", f"**Exact:** `{path}`"]
        for position, text in enumerate(texts):
            lines += ["", "**With:**"] if position else []
            lines += ["", "```text", text, "```"]
    return "\n".join(lines) + "\n"


def test_live_repository_metadata(tmp_path: Path) -> None:
    # Call the validator directly: one contained pytest process, with package,
    # reference, protocol, projection, and guidance checks on every routine run.
    assert validator.main() == 0
    # Retired identities stay detected in any letter case, through backslash paths,
    # and as executable compatibility mappings; unrelated words are not hits.
    (tmp_path / "skills").mkdir()
    samples = {
        "upper.md": "Use the `Think` skill.\n",
        "path.md": "See skills\\routing for history.\n",
        "mapping.py": "LEGACY = {'map-codebase': 'atlas'}\n",
        "clean.md": "Nothing retired here; skills route through the router.\n",
    }
    for name, text in samples.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    assert validator.validate_canonical_convergence(tmp_path, [tmp_path / name for name in samples]) == [
        "upper.md: retired active surface remains: retired reasoning identity",
        "path.md: retired active surface remains: skills/routing",
        "mapping.py: retired compatibility mapping remains: map-codebase -> atlas",
    ]
    assert inventory_errors(json.loads(INVENTORY.read_text(encoding="utf-8"))) == []
    # Examiner's paper runtime is refused when it reaches outside its own file.
    runtime = tmp_path / "paper-runtime.html"
    runtime.write_text('<script>fetch("https://example.org/answers")</script>\n', encoding="utf-8")
    refused = validator.validate_paper_runtime(runtime)
    assert any(error.endswith(": network API") for error in refused)
    assert any(error.endswith(": absolute URL") for error in refused)
    runtime.write_text("<script>document.createElement('link').href = 'x.css';</script>\n", encoding="utf-8")
    assert validator.validate_paper_runtime(runtime)[0].endswith(": script-created resource")
    for sample, name in (
            ('make("img", { src: "logo.png" });', "helper-created resource"),
            ("node.setAttribute('src', 'a.png');", "source attribute"),
            ("new Audio('x.mp3').play();", "media load"),
            ("document.createElement('meta').httpEquiv = 'refresh';", "script-created resource"),
            ("p.style.cssText = 'image-set(a.png 1x)';", "CSS resource"),
            ("location.search = '?a=1';", "page navigation"),
            ("location['href'] = 'x.html';", "page navigation"),
            ("location.href += '?a=1';", "page navigation"),
            ("open('x.html');", "page navigation"),
            ('const w = window; w.open("collect.html");', "page navigation"),
            ('doc.defaultView.open("collect.html");', "page navigation"),
            ('w.open?.("collect.html");', "page navigation"),
            ('w.open.call(w, "collect.html");', "page navigation"),
            ('w["open"]("collect.html");', "page navigation"),
            ('navigation.navigate("collect.html");', "page navigation"),
            ("navigation.back();", "page navigation"),
            ("history.back();", "page navigation"),
            ("history.go(-1);", "page navigation"),
            ("form.setAttribute('action', 'collect.html');", "page navigation"),
            ("form.action = 'collect.html';", "page navigation"),
            ('make("p").innerHTML = \'<meta http-equiv="refresh" content="0">\';', "page navigation"),
            ("document.createElement('form');", "script-created resource"),
            ('ui.make("object", { data: "collect.html" });', "helper-created resource"),
            ('<button formaction="collect.html">', "URL attribute"),
            ('button.formAction = "collect.html";', "URL attribute"),
            ('<td background="bg.png">', "URL attribute"),
            ("document.body.background = 'bg.png';", "URL attribute"),
            ("a.setAttribute('ping', 'collect');", "URL attribute"),
            ('make("a", { ping: "collect" });', "URL attribute"),
            ('make("a", { href: "collect.html" }).click();', "link target"),
            ("make('a', { href: target }).click();", "link target"),
            ('make("a", { href }).click();', "link target"),
            ("link.href = base + 'collect.html';", "link target"),
            ("link.href += 'collect.html';", "link target"),
            ("link.href ||= 'collect.html';", "link target"),
            ("use.setAttribute('xlink:href', 'sprite.svg#a');", "link target"),
            ("a.setAttributeNS(null, 'href', 'collect.html');", "link target"),
            ("fetchLater('collect');", "network API")):
        runtime.write_text(f"<script>{sample}</script>\n", encoding="utf-8")
        assert any(error.endswith(f": {name}") for error in validator.validate_paper_runtime(runtime)), sample
    # In-file code that reaches nothing outside the paper is not refused.
    runtime.write_text("<script>control.closest('form'); node.getAttribute('style'); details.open = true;"
                       " make('a', { href: '#top' }); make('a', { href: url = URL.createObjectURL(blob) });"
                       " link.setAttribute('href', URL.createObjectURL(blob)); link.getAttribute('href');"
                       " URL.revokeObjectURL(link.href); document.querySelector('a[href]');"
                       " node.classList.add('source'); const fetched = 1; localStorage.getItem('form');"
                       " if (action === 'save') { p.style.background = 'none'; const here = location.href; }"
                       " const href = link.getAttribute('href'); items.forEach(action => run(action));"
                       " let ping = performance.now();</script>\n", encoding="utf-8")
    assert validator.validate_paper_runtime(runtime) == []
    # The size cap counts line endings as LF, so a CRLF checkout of the same text passes.
    runtime.write_text("a\n" * 14000, encoding="utf-8", newline="\r\n")
    assert validator.validate_paper_runtime(runtime) == []
    runtime.write_text("a" * 40001, encoding="utf-8")
    assert validator.validate_paper_runtime(runtime)[0].endswith("larger than 40000 bytes")
    runtime.write_text("<style>p { color: #222; }</style>\n<script>localStorage.getItem('k');</script>\n",
                       encoding="utf-8")
    assert validator.validate_paper_runtime(runtime) == []
    assert validator.validate_paper_runtime(tmp_path / "absent.html")[0].endswith("paper runtime is missing")
    # A draft's Exact blocks on agent-loaded guidance estimate measured minus
    # replaced plus drafted tokens; a new reference adds its whole text, and an
    # Exact block on any other path is not counted.
    from measure_context_load import estimate_draft, measure

    old, new, added = "Old guidance line.", "New guidance line with several more words.", "Probe reference text."
    rows = estimate_draft(_draft(
        (f"{SKILL}/SKILL.md", "existing", (old, new)),
        (f"{SKILL}/references/budget-probe.md", "new", (added,)),
        (f"{SKILL}/README.md", "existing", ("Unbudgeted line.", "Unbudgeted replacement that is not counted.")),
    ))["skills"]
    measured = measure(ROOT)["blueprint"]
    assert set(rows) == {"blueprint"}
    top, references = rows["blueprint"]["top_level"], rows["blueprint"]["references"]
    assert top["delta"] == count_tokens(new + "\n") - count_tokens(old + "\n")
    assert references["delta"] == count_tokens(added + "\n")
    assert (top["spans"], references["spans"]) == (1, 1)
    for metric, row in (("top_level", top), ("references", references)):
        assert row["estimated"] == measured[metric] + row["delta"]
        assert row["headroom"] == row["limit"] - row["estimated"]
        assert row["fits"] is (row["headroom"] >= 4)
    # An estimate over the limit does not fit, and a skill without a recorded
    # budget is refused rather than skipped.
    oversized = estimate_draft(_draft((f"{SKILL}/references/budget-probe.md", "new", ("budget " * 12000,))))
    assert oversized["skills"]["blueprint"]["references"]["fits"] is False
    with pytest.raises(ValueError):
        estimate_draft(_draft(("skills/workbench/unbudgeted-probe/SKILL.md", "new", ("Probe.",))))

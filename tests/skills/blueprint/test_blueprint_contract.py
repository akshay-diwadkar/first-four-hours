from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "workbench" / "blueprint" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load_module(name: str, path: Path) -> Any:
    """Load a Blueprint script under a unique module name.

    Blueprint owns ``blueprint_runtime.py`` and Construct owns a different module of
    the same file name. Loading under a unique name keeps the shared
    ``sys.modules["blueprint_runtime"]`` key clear so Construct tests can import their
    own runtime without first popping a Blueprint-cached copy.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load_module("blueprint_blueprint_runtime", SCRIPTS / "blueprint_runtime.py")


@pytest.fixture(autouse=True)
def _default_evidence_source(tmp_path: Path) -> None:
    source = tmp_path / "src" / "names.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        source.write_text("def normalize(value):\n    return value.strip()\n    # evidence\n", encoding="utf-8")


def draft(*, risks: bool = False, source: str = "src/names.py:1-3") -> str:
    blocks = [
        runtime.CONTRACT_MARKER,
        "# Blueprint: predictable names",
        "",
        "## Goal",
        "Make absent names normalize predictably for the caller.",
        "",
        "## Current State",
        "The caller receives inconsistent absent-name behavior from the owning seam.",
        f"**Source:** `{source}`",
        "",
        "## Implementation",
        "",
        "### 1. Normalize absent names",
        "**Location:** `src/names.py::normalize`",
        "**State:** existing",
        "",
        "Return the requested empty value for an absent name and preserve present names.",
        "",
        "```python",
        "def normalize(value):",
        '    return value.strip() if value else ""',
        "```",
        "",
        "Use:",
        "- the existing normalization seam",
        "",
        "Preserve:",
        "- present-name behavior and unrelated callers",
        "",
        "Do not:",
        "- add a second normalization path",
        "",
        "### 2. Add the focused regression",
        "**Location:** `tests/test_names.py`",
        "**State:** new",
        "",
        "Add the absent-name case next to the existing normalization tests.",
    ]
    blocks.extend(
        [
            "",
            "## Verification",
            "",
            "### After implementation",
            "Run: `python -m pytest -q tests/test_names.py`",
            "Expect: exit 0 and the absent-name case passes.",
            "",
            "## Completion Conditions",
            "- The absent name normalizes to the requested empty value.",
            "- Present names and unrelated callers are unchanged.",
        ]
    )
    if risks:
        blocks.extend(
            [
                "",
                "## Risks / Recovery",
                "If the public adapter starts dropping names, revert the seam edit and reseal from evidence.",
            ]
        )
    return "\n".join(blocks) + "\n"


def codes(text: str, repo: Path) -> set[str]:
    return {item.code for item in runtime.validate_draft(text, repo).diagnostics}


def write_request_and_draft(tmp_path: Path, text: str) -> tuple[Path, Path]:
    source = tmp_path / "src" / "names.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        source.write_text("def normalize(value):\n    return value.strip()\n    # evidence\n", encoding="utf-8")
    draft_file = tmp_path / ".first-four-hours" / "blueprints" / "test-task" / "blueprint.md"
    draft_file.parent.mkdir(parents=True)
    request = draft_file.parent / "request.md"
    request.write_text("Normalize names without changing unrelated callers.\n", encoding="utf-8")
    draft_file.write_text(text, encoding="utf-8")
    return request, draft_file


def _sealed_proof(sealed: str) -> dict[str, Any]:
    match = runtime.PROOF_RE.search(sealed)
    assert match is not None
    return json.loads(match.group("json"))


STEP_ONE_STATE = "**State:** existing\n"
EXACT_REPLACE = (
    "**Exact:** `src/names.py`\n```python\n    return value.strip()\n```\n"
    '**With:**\n```python\n    return value.strip() if value else ""\n```\n'
)
FROZEN_PROOF = (
    '**State:** new\n**Location:** `tests/names_cases.txt`\n**State:** new\n\n'
    '**Frozen:** `tests/names_cases.txt`\n```text\nabsent -> ""\n```\n\n'
    "**Proof run:** `python -m pytest -q tests/test_names.py`\n"
    "Red: AssertionError for the absent name\nExpect: 1 passed.\n"
)


DELETION = (
    "**Exact:** `src/names.py`\n```python\n    return value.strip()\n    # evidence\n```\n"
    "**With:**\n```python\n    return value.strip()\n```\n"
)


def with_step_proof(text: str, exact: str = EXACT_REPLACE) -> str:
    text = text.replace(STEP_ONE_STATE, STEP_ONE_STATE + "\n" + exact, 1)
    return text.replace("**State:** new\n", FROZEN_PROOF, 1)


def replace_block(old: str, new: str) -> str:
    return f"**Exact:** `src/seq.txt`\n```text\n{old}```\n**With:**\n```text\n{new}```\n"


def sequence_codes(tmp_path: Path, content: bytes, *steps: str, alias_step: int | None = None) -> set[str]:
    """Seal-check a plan whose instructions edit one existing file through declared text."""
    (tmp_path / "src" / "seq.txt").write_bytes(content)
    body = "".join(
        f"### {number}. Edit step {number}\n**Location:** `{'./' if number == alias_step else ''}src/seq.txt`\n**State:** existing\n\n{blocks}\n"
        for number, blocks in enumerate(steps, start=1)
    )
    plan = draft().split("## Implementation\n", 1)[0] + "## Implementation\n\n" + body + "## Verification" + draft().split("## Verification", 1)[1]
    return codes(plan, tmp_path)


def test_unexecutable_declarations_are_rejected_at_seal(tmp_path: Path) -> None:
    text = draft().replace("Run: `python -m pytest -q tests/test_names.py`", "Run: `git commit -m done`", 1)
    assert "verification.git.mutation" in codes(text, tmp_path)
    # Each draft below is an independent refusal with its own input and code.
    # The next instruction's closer must not turn an unclosed block into one large file.
    swallowed = draft().split("## Implementation\n", 1)[0] + "## Implementation\n\n" + (
        "### 1. First file\n**Location:** `src/a.txt`\n**State:** new\n**Exact:** `src/a.txt`\n```text\nA\n"
        "### 2. Second file\n**Location:** `src/b.txt`\n**State:** new\n**Exact:** `src/b.txt`\n```text\nB\n```\n\n"
    ) + "## Verification" + draft().split("## Verification", 1)[1]
    assert "block.shape" in codes(swallowed, tmp_path)
    # A stray Red line would silently drop the red-before-green requirement.
    stray = draft().replace(STEP_ONE_STATE, STEP_ONE_STATE + "\nRed: AssertionError for the absent name\n", 1)
    assert "proof.displaced" in codes(stray, tmp_path)
    # One Proof run per instruction, and one Timeout and one Red per chain, so nothing is silently overridden.
    proved = with_step_proof(draft())
    second = proved.replace("Expect: 1 passed.\n", "Expect: 1 passed.\n\n**Proof run:** `python -m pytest -q tests/test_names.py`\nExpect: 1 passed.\n", 1)
    assert "proof.duplicate" in codes(second, tmp_path)
    assert "proof.duplicate" in codes(proved.replace("Red: AssertionError", "Timeout: 5\nTimeout: 9\nRed: AssertionError", 1), tmp_path)
    assert "proof.duplicate" in codes(proved.replace("Red: AssertionError", "Red: first defect\nRed: AssertionError", 1), tmp_path)
    # Plans carry decisions, not code: declared text on an executable file is refused unless it is an anchored replacement changing at most two lines.
    assert runtime.validate_draft(proved, tmp_path).valid
    replacement = '**With:**\n```python\n    return value.strip() if value else ""\n```'
    at_limit = proved.replace(replacement, '**With:**\n```python\n    if value:\n        return value.strip()\n```', 1)
    assert runtime.validate_draft(at_limit, tmp_path).valid
    over_limit = proved.replace(replacement, '**With:**\n```python\n    if value:\n        return value.strip()\n    return ""\n```', 1)
    assert "block.code" in codes(over_limit, tmp_path)
    whole_test = draft().replace("**State:** new\n", "**State:** new\n\n**Frozen:** `tests/test_names.py`\n```python\nassert normalize(None) == \"\"\n```\n\n"
                                 "**Proof run:** `python -m pytest -q tests/test_names.py`\nExpect: 1 passed.\n", 1)
    assert codes(whole_test, tmp_path) == {"block.code"}
    assert "block.code" not in {item.code for item in runtime.parse_blueprint(whole_test)[1]}
    # Frozen proof needs a Proof run, and a Proof run passes only on exit 0.
    frozen_only = draft().replace("**State:** new\n", "**State:** new\n\n**Frozen:** `tests/test_names.py`\n```python\nassert 1\n```\n", 1)
    assert "frozen.proof_missing" in codes(frozen_only, tmp_path)
    assert "verification.expect.nonzero_exit" in codes(proved.replace("Expect: 1 passed.\n", "Expect: exit code 2.\n", 1), tmp_path)
    # A near-miss spelling of a reserved label would otherwise be silently ignored.
    assert "declaration.malformed" in codes(draft().replace(STEP_ONE_STATE, STEP_ONE_STATE + "\n**Exact**: `src/names.py`\n", 1), tmp_path)
    bold_red = proved.replace("Red: AssertionError for the absent name\nExpect: 1 passed.\n",
                              "Expect: 1 passed.\n**Red:** AssertionError for the absent name\n", 1)
    assert "declaration.malformed" in codes(bold_red, tmp_path)
    # Whole-file text cannot classify an existing file's unapplied state.
    whole = draft().replace(STEP_ONE_STATE, STEP_ONE_STATE + "\n**Exact:** `src/names.py`\n```python\npass\n```\n", 1)
    assert "block.whole_existing" in codes(whole, tmp_path)
    # A replacement anchor that matches twice cannot bind one location.
    assert "block.anchor" in sequence_codes(tmp_path, b"A\nA\n", replace_block("A\n", "B\n"))
    # Construct checks a phase's blocks together, so a chained anchor is absent at that checkpoint.
    assert "block.anchor" in sequence_codes(tmp_path, b"a\nz\n", replace_block("a\n", "a\nb\n") + replace_block("b\n", "b\nc\n"))
    # A faithful step 1 would leave its replacement twice in the partly edited file.
    assert "block.unprovable" in sequence_codes(tmp_path, b"A\nB\nC\n", replace_block("A\n", "C\n"), replace_block("B\nC\n", "B\nD\n"))
    # A later instruction that consumes earlier declared text leaves the earlier proof unpassable.
    assert "block.consumed" in sequence_codes(tmp_path, b"a\nz\n", replace_block("a\n", "a\nb\n"),
                                             replace_block("a\n", "c\n").replace("src/seq.txt", "./src/seq.txt"), alias_step=2)
    # A target that is not UTF-8 text can never be proven.
    assert "block.target_unreadable" in sequence_codes(tmp_path, b"caf\xe9\n", replace_block("x\n", "y\n"))
    # An anchor that starts mid-line never binds a location.
    assert "block.anchor" in sequence_codes(tmp_path, b"xA\nAB\n", replace_block("A\n", "C\n"))
    # An environmental incomplete outcome binds only to a Verification Run's Expect, once.
    orphan = draft().replace("Run: `python -m pytest", "Incomplete: the final record reports complete false\nRun: `python -m pytest", 1)
    assert "verification.incomplete.orphan" in codes(orphan, tmp_path)
    twice = draft().replace(EXIT_ZERO_EXPECT, EXIT_ZERO_EXPECT + "Incomplete: complete false\nIncomplete: deadline exhausted\n", 1)
    assert "verification.incomplete.duplicate" in codes(twice, tmp_path)
    displaced = draft().replace(STEP_ONE_STATE, STEP_ONE_STATE + "\nIncomplete: the deadline was exhausted\n", 1)
    assert "verification.incomplete.displaced" in codes(displaced, tmp_path)
    # Construct defines the incomplete action only after implementation, so a baseline cannot declare one.
    before = draft().replace("### After implementation\n", "### Before implementation\nRun: `python -m pytest -q tests/test_names.py`\nExpect: exit 0.\nIncomplete: the deadline was exhausted\n\n### After implementation\n", 1)
    assert "verification.incomplete.before" in codes(before, tmp_path)
    # A phase heading ends the earlier Run, so a declaration after it binds to nothing rather than to the baseline.
    crossing = before.replace("Incomplete: the deadline was exhausted\n\n### After implementation\n", "\n### After implementation\nIncomplete: the deadline was exhausted\n", 1)
    assert "verification.incomplete.orphan" in codes(crossing, tmp_path)
    # A heading also ends a Run with no Expect yet, so it is reported instead of sealing in the next phase.
    unbound = before.replace("Expect: exit 0.\nIncomplete: the deadline was exhausted\n\n### After implementation\n", "\n### After implementation\nExpect: exit 0.\n", 1)
    assert "verification.expect.missing" in codes(unbound, tmp_path)
    # A declared Run is last in its phase, so its incomplete outcome cannot hide later checks.
    not_last = draft().replace(EXIT_ZERO_EXPECT, EXIT_ZERO_EXPECT + "Incomplete: deadline exhausted\nRun: `python -m pytest -q tests/test_names.py`\nExpect: exit 0.\n", 1)
    assert "verification.incomplete.not_last" in codes(not_last, tmp_path)
    assert "verification.incomplete.placeholder" in codes(draft().replace(EXIT_ZERO_EXPECT, EXIT_ZERO_EXPECT + "Incomplete: TBD\n", 1), tmp_path)
    assert "declaration.malformed" in codes(draft().replace(EXIT_ZERO_EXPECT, EXIT_ZERO_EXPECT + "**Incomplete:** deadline exhausted\n", 1), tmp_path)
    # Between a Run and its Expect there is no bound step yet, so the declaration is an orphan
    # rather than binding to the earlier Run.
    between = draft().replace(EXIT_ZERO_EXPECT, EXIT_ZERO_EXPECT + "Run: `python -m pytest -q tests/test_names.py`\nIncomplete: deadline exhausted\nExpect: exit 0.\n", 1)
    assert "verification.incomplete.orphan" in codes(between, tmp_path)
    # A planned deletion seals against an existing regular file.
    (tmp_path / "src" / "retired.py").write_text("RETIRED = True\n", encoding="utf-8")
    deleted = "**Location:** `src/retired.py`\n**State:** deleted\n"
    deleting = draft().replace("**State:** new\n", "**State:** new\n" + deleted, 1)
    assert runtime.validate_draft(deleting, tmp_path).valid
    # The deletion is that path's only Location, an absent path cannot be deleted, and no other spelling binds.
    assert "location.deleted.conflict" in codes(deleting.replace(deleted, deleted + "**Location:** `./src/retired.py`\n**State:** existing\n", 1), tmp_path)
    assert "location.target.missing" in codes(deleting.replace("src/retired.py", "src/absent.py", 1), tmp_path)
    assert "state.unsupported" in codes(deleting.replace("**State:** deleted", "**State:** removed", 1), tmp_path)
    assert "location.deleted.symbol" in codes(deleting.replace("`src/retired.py`\n", "`src/retired.py::RETIRED`\n", 1), tmp_path)
    # A plan never cites as Source a file its own step deletes, even through an alias spelling;
    # the seal, which check shares, names that path.
    cited = deleting.replace("**Source:** `src/names.py:1-3`\n", "**Source:** `src/names.py:1-3`\n**Source:** `./src/retired.py`\n", 1)
    request, draft_file = write_request_and_draft(tmp_path, cited)
    with pytest.raises(ValueError) as refused:
        runtime.seal_blueprint(tmp_path, request, draft_file)
    named = [item for item in getattr(refused.value, "diagnostics", ()) if item.code == "source.deleted"]
    assert len(named) == 1 and named[0].path == "./src/retired.py" and "./src/retired.py" in named[0].message
    # A Source reaching the deleted file through a directory link is the same file and is refused too.
    alias = tmp_path / "alias"
    if sys.platform == "win32":
        linked = subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(tmp_path / "src")], capture_output=True, text=True, check=False)
        assert linked.returncode == 0, linked.stdout + linked.stderr
    else:
        alias.symlink_to(tmp_path / "src", target_is_directory=True)
    try:
        linked_source = deleting.replace("**Source:** `src/names.py:1-3`\n", "**Source:** `src/names.py:1-3`\n**Source:** `alias/retired.py`\n", 1)
        assert "source.deleted" in codes(linked_source, tmp_path)
        # A second Location reaching the deleted file through the link is the same path declared again.
        linked_location = deleting.replace(deleted, deleted + "**Location:** `alias/retired.py`\n**State:** existing\n", 1)
        assert "location.deleted.conflict" in codes(linked_location, tmp_path)
        # A deletion spelled through the link fails the seal: removing the link alone would make
        # that spelling absent while the sealed file survives.
        linked_deletion = deleting.replace(deleted, "**Location:** `alias/retired.py`\n**State:** deleted\n", 1)
        assert "location.deleted.link" in codes(linked_deletion, tmp_path)
    finally:
        if sys.platform == "win32":
            alias.rmdir()
        else:
            alias.unlink()
    # A hardlinked twin is a separate directory entry that survives the deletion, so it stays citable.
    (tmp_path / "src" / "twin.py").hardlink_to(tmp_path / "src" / "retired.py")
    twin_source = deleting.replace("**Source:** `src/names.py:1-3`\n", "**Source:** `src/names.py:1-3`\n**Source:** `src/twin.py`\n", 1)
    assert runtime.validate_draft(twin_source, tmp_path).valid


EXIT_ZERO_EXPECT = "Expect: exit 0 and the absent-name case passes.\n"


def _expecting(expect: str) -> str:
    return draft().replace(EXIT_ZERO_EXPECT, f"Expect: {expect}\n", 1)


def test_prepare_seal_and_readback(tmp_path: Path) -> None:
    # The deletion idiom keeps a neighbouring line in both blocks and must seal.
    plain = with_step_proof(_expecting("exit 0 and the absent-name case passes.\nIncomplete: the final record reports complete false"), DELETION)
    literal = 'PAYLOAD = """left\vtab\fform\x85nel\u2028line\u2029paragraph\rreturn\n### 7. Literal heading\n**Exact:** `example.txt`\n```text\nexample\n```\n"""\nassert normalize(None) == ""\n'
    plain = plain.replace('```text\nabsent -> ""\n```', '````text\n' + literal + '````')
    # A corrected authoring operation still refuses an empty replacement.
    assert "block.empty" in codes(plain.replace('**With:**\n```python\n    return value.strip()\n```', '**With:**\n```python\n```', 1), tmp_path)
    assert "Expect: exit 0" in plain
    assert runtime.validate_draft(plain, tmp_path).valid
    incoming = tmp_path / "incoming.md"
    incoming.write_text("Normalize names without changing unrelated callers.\n", encoding="utf-8")
    workspace = runtime.prepare_blueprint_workspace(tmp_path, "test-task", incoming)
    request, draft_file = workspace.request_path, workspace.blueprint_path
    # The workspace lives under the one artifact root, never in a top-level folder.
    assert draft_file.resolve().relative_to(tmp_path.resolve()).as_posix() == ".first-four-hours/blueprints/test-task/blueprint.md"
    assert not (tmp_path / "blueprints").exists()
    # A linked artifact root is refused before anything is written through it.
    linked_repo = tmp_path / "linked-repo"
    outside = tmp_path / "outside"
    linked_repo.mkdir()
    outside.mkdir()
    if sys.platform == "win32":
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(linked_repo / ".first-four-hours"), str(outside)], capture_output=True, text=True, check=False)
        assert made.returncode == 0, made.stdout + made.stderr
    else:
        (linked_repo / ".first-four-hours").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError) as linked_root:
        runtime.prepare_blueprint_workspace(linked_repo, "test-task", incoming)
    assert [item.code for item in getattr(linked_root.value, "diagnostics", ())] == ["workspace.namespace.symlink"]
    assert list(outside.iterdir()) == []
    # A linked namespace inside a real artifact root is refused before the task folder or request is written.
    namespace_repo = tmp_path / "linked-namespace-repo"
    namespace_outside = tmp_path / "namespace-outside"
    (namespace_repo / ".first-four-hours").mkdir(parents=True)
    namespace_outside.mkdir()
    namespace = namespace_repo / ".first-four-hours" / "blueprints"
    if sys.platform == "win32":
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(namespace), str(namespace_outside)], capture_output=True, text=True, check=False)
        assert made.returncode == 0, made.stdout + made.stderr
    else:
        namespace.symlink_to(namespace_outside, target_is_directory=True)
    with pytest.raises(ValueError) as linked_namespace:
        runtime.prepare_blueprint_workspace(namespace_repo, "test-task", incoming)
    assert [item.code for item in getattr(linked_namespace.value, "diagnostics", ())] == ["workspace.namespace.symlink"]
    assert list(namespace_outside.iterdir()) == []
    assert request.read_bytes() == incoming.read_bytes()
    cli = [sys.executable, str(SCRIPTS / "cli.py"), "--repo-root", str(tmp_path), "--input",
           f"request_file={request}", "--input", f"draft_file={draft_file}", "--format", "json"]
    broken = plain.replace('**With:**\n```python\n    return value.strip()\n```', '**With:**\n```python\n```', 1)
    draft_file.write_bytes(broken.encode("utf-8"))
    refused = subprocess.run([*cli, "check"], capture_output=True, text=True, check=False)
    assert refused.returncode != 0 and "block.empty" in json.loads(refused.stdout)["blocking_reasons"]
    assert draft_file.read_bytes() == broken.encode("utf-8")
    draft_file.write_bytes(plain.encode("utf-8"))
    checked = subprocess.run([*cli, "check"], capture_output=True, text=True, check=False)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    envelope = json.loads(checked.stdout)
    assert envelope["result"]["check_only"] is True and envelope["artifacts"] == []
    assert draft_file.read_bytes() == plain.encode("utf-8")
    sealed_run = subprocess.run([*cli, "run"], capture_output=True, text=True, check=False)
    assert sealed_run.returncode == 0, sealed_run.stdout + sealed_run.stderr
    envelope = json.loads(sealed_run.stdout)
    assert envelope["artifacts"] == [] and "check_only" not in envelope["result"]
    assert Path(envelope["result"]["blueprint_path"]).resolve() == draft_file.resolve()
    sealed = draft_file.read_bytes().decode("utf-8")
    assert runtime.canonical_body(sealed) == plain
    # The plan opens with its title; the generated receipts form the final two lines.
    sealed_lines = sealed.splitlines()
    assert sealed_lines[1] == plain.splitlines()[1] and sealed_lines[1].startswith("# ")
    assert runtime.PROOF_RE.fullmatch(sealed_lines[-2]) and runtime.VALIDATION_RE.fullmatch(sealed_lines[-1])
    displaced = "\n".join([sealed_lines[0], *sealed_lines[-2:], *sealed_lines[1:-2]]) + "\n"
    _displaced, displaced_diagnostics, _view = runtime.verify_sealed_blueprint(displaced, tmp_path, request_bytes=request.read_bytes())
    assert [item.code for item in displaced_diagnostics] == ["receipt.displaced"]
    # A typed handoff is read from its final-line receipt; leading or trailed receipts never pass as generic requests.
    diagnosis_body = "# Diagnosis\n\n## Finding retry-default\n\n- Title: \"Retries\"\n"
    diagnosis = diagnosis_body + f"<!-- diagnosis: 1.0.0; sha256: {runtime._sha256(diagnosis_body.encode('utf-8'))} -->\n"
    assert runtime.detect_request_source(diagnosis.encode("utf-8"))["kind"] == "diagnosis"
    # Another minor of the same Diagnose major is accepted; another major or an old integer version is refused.
    newer_minor = diagnosis.replace("<!-- diagnosis: 1.0.0; ", "<!-- diagnosis: 1.3.0; ", 1)
    assert runtime.detect_request_source(newer_minor.encode("utf-8"))["contract_version"] == "1.3.0"
    for unsupported in ("2.0.0", "4"):
        with pytest.raises(ValueError) as refused_version:
            runtime.detect_request_source(diagnosis.replace("<!-- diagnosis: 1.0.0; ", f"<!-- diagnosis: {unsupported}; ", 1).encode("utf-8"))
        assert [item.code for item in getattr(refused_version.value, "diagnostics", ())] == ["handoff.version.unsupported"]
    for variant in (diagnosis + "note\n", diagnosis.splitlines(keepends=True)[-1] + diagnosis_body):
        with pytest.raises(ValueError) as refused_handoff:
            runtime.detect_request_source(variant.encode("utf-8"))
        assert [item.code for item in getattr(refused_handoff.value, "diagnostics", ())] == ["handoff.receipt.malformed"]
    # Fenced or quoted examples of a receipt in a generic request stay generic input.
    receipt_line = diagnosis.splitlines()[-1]
    for example in (f"# Request\n\nQuote:\n\n```text\n{receipt_line}\n```\n\nThanks.\n", f"# Request\n\n> {receipt_line}\n\nThanks.\n"):
        assert runtime.detect_request_source(example.encode("utf-8"))["kind"] == "generic"
    # Ordinary comment lines after line 1 stay generic as on base; a receipt-shaped final line is still refused.
    for ordinary in ("# Request\n\n<!-- diagnosis notes for later -->\nWork.\n", "# Request\n\nWork.\n<!-- optimization: todo -->\n", "# Request\n\nWork.\n<!-- see handoff below -->\n"):
        assert runtime.detect_request_source(ordinary.encode("utf-8"))["kind"] == "generic"
    for shaped, code in (("<!-- Diagnosis: 4; sha256: abc -->", "handoff.receipt.malformed"), ("<!-- diagnosis: 4 sha256: abc -->", "handoff.receipt.malformed"), (f"<!-- ideation-handoff: 1; sha256: {'0' * 64} -->", "handoff.marker.unsupported")):
        with pytest.raises(ValueError) as refused_shaped:
            runtime.detect_request_source((diagnosis_body + shaped + "\n").encode("utf-8"))
        assert [item.code for item in getattr(refused_shaped.value, "diagnostics", ())] == [code]
    # A sealed handoff with bytes appended stays refused even when an unbalanced fence hides its receipt from the clean view.
    hidden_body = "# Diagnosis\n\n## Finding retry-default\n\n~~~md\n```py\nx\n~~~\n"
    hidden = hidden_body + f"<!-- diagnosis: 1.0.0; sha256: {runtime._sha256(hidden_body.encode('utf-8'))} -->\nnote\n"
    with pytest.raises(ValueError) as refused_hidden:
        runtime.detect_request_source(hidden.encode("utf-8"))
    assert [item.code for item in getattr(refused_hidden.value, "diagnostics", ())] == ["handoff.receipt.malformed"]
    blueprint, diagnostics = runtime.parse_blueprint(sealed)
    assert diagnostics == []
    assert blueprint is not None
    assert len(blueprint.steps) == 2
    replace, frozen = blueprint.steps[0].blocks[0], blueprint.steps[1].blocks[0]
    assert (replace.old, replace.text) == ("    return value.strip()\n    # evidence\n", "    return value.strip()\n")
    assert (frozen.kind, frozen.old, frozen.text) == ("frozen", None, literal)
    assert blueprint.steps[1].red == "AssertionError for the absent name"
    assert [step.incomplete for step in blueprint.verification] == ["the final record reports complete false"]
    resealed = runtime.render_sealed_blueprint(plain, _sealed_proof(sealed))
    assert resealed == sealed
    verified = subprocess.run([sys.executable, str(SCRIPTS / "verify_blueprint.py"), "--repo-root", str(tmp_path),
                               "--blueprint", str(draft_file)], capture_output=True, text=True, check=False)
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert json.loads(verified.stdout)["valid"] is True


def test_relevant_byte_drift_fails_closed_after_seal(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "src" / "names.py"
    source.parent.mkdir(parents=True)
    source.write_text("def normalize(value):\n    return value\n    # evidence\n", encoding="utf-8")
    request, draft_file = write_request_and_draft(repo, draft())
    sealed = runtime.seal_blueprint(repo, request, draft_file).text
    source.write_text("def normalize(value):\n    return value  # drifted\n    # evidence\n", encoding="utf-8")
    _blueprint, diagnostics, _view = runtime.verify_sealed_blueprint(
        sealed, repo, request_bytes=request.read_bytes()
    )
    assert {"proof.sources.stale", "proof.locations.stale"} <= {item.code for item in diagnostics}

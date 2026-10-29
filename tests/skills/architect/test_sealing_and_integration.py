from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "skills" / "workbench" / "architect" / "scripts"))


from tools.validation.git_test_support import seed_git

from tools.validation.python_test_support import run_python

import pytest

from architecture_handoff import ARCHITECT_VERSION, _snapshot

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills" / "workbench" / "architect"
SEALER = SKILL / "scripts" / "seal_assessment.py"
PREPARE = ROOT / "skills" / "workbench" / "blueprint" / "scripts" / "prepare_blueprint_workspace.py"


def _link_dir(link: Path, target: Path) -> None:
    """Create a directory link: a junction on Windows (no privilege needed), else a symlink."""
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=True)
    else:
        link.symlink_to(target, target_is_directory=True)


def make_repo(root: Path) -> Path:
    (root / "payments").mkdir(parents=True)
    (root / "checkout").mkdir()
    (root / "subscriptions").mkdir()
    (root / "tests").mkdir()
    (root / "payments" / "service.py").write_text(
        "import provider_sdk\n"
        "\n"
        "def charge_payment(amount, currency, token=None):\n"
        "    request = provider_sdk.Request(amount, currency, token)\n"
        "    return provider_sdk.charge(request)\n"
        "\n"
        "PROVIDER_ERRORS = (provider_sdk.ProviderDeclined, provider_sdk.ProviderTimeout)\n",
        encoding="utf-8",
    )
    (root / "checkout" / "process.py").write_text(
        "from payments.service import charge_payment\n"
        "\n"
        "def checkout(amount, token=None):\n"
        "    try:\n"
        "        return charge_payment(amount, 'USD', token)\n"
        "    except TimeoutError:\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_checkout.py").write_text(
        "from checkout.process import checkout\n"
        "\n"
        "def test_checkout_decline():\n"
        "    result = checkout(10)\n"
        "    assert result is not None\n"
        "\n",
        encoding="utf-8",
    )
    (root / "subscriptions" / "renew.py").write_text(
        "from payments.service import charge_payment\n"
        "\n"
        "def renew(amount, payment_token):\n"
        "    return charge_payment(amount, 'USD', payment_token)\n",
        encoding="utf-8",
    )
    return root


def example() -> str:
    return (SKILL / "references" / "worked-examples.md").read_text(encoding="utf-8")


def seal_command(repo: Path, slug: str, draft: Path, *, json_output: bool = False) -> list[str]:
    command = [
        sys.executable,
        str(SEALER),
        "--repo-root",
        str(repo),
        "--slug",
        slug,
    ]
    if json_output:
        command.extend(("--format", "json"))
    command.append(str(draft))
    return command


def init_git(repo: Path) -> str:
    return seed_git(repo)


def proof_snapshot(handoff: Path) -> dict[str, object]:
    proof_line = handoff.read_text(encoding="utf-8").splitlines()[-2]
    match = re.fullmatch(r"<!-- architecture-proof: (.+) -->", proof_line)
    assert match is not None
    return json.loads(match.group(1))["snapshot"]


def prepare_command(repo: Path, request: Path, task: str) -> list[str]:
    return [sys.executable, str(PREPARE), "--repo-root", str(repo), "--request-file", str(request), "--task-name", task]


def test_snapshot_binding_clean_git_success_and_head_mismatch(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    first_head = init_git(repo)
    draft = tmp_path / "draft.md"
    draft.write_text(example(), encoding="utf-8")
    sealed = run_python(seal_command(repo, "Payment Boundary", draft, json_output=True), capture_output=True, text=True, check=True)
    handoff = repo / ".first-four-hours" / "architectures" / "payment-boundary" / "architecture.md"
    result = json.loads(sealed.stdout)
    assert result["git_ignored"] is True
    assert Path(result["path"]) == handoff.resolve()
    assert sorted(path.name for path in handoff.parent.iterdir()) == ["architecture.md"]
    assert "/.first-four-hours/architectures/" in (repo / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()
    status = run_python(["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo, capture_output=True, text=True, check=True)
    assert status.stdout == ""
    snapshot = proof_snapshot(handoff)
    assert snapshot["kind"] == "git"
    assert snapshot["revision"] == first_head
    assert snapshot["dirty"] is False
    assert snapshot["dirty_fingerprint"] is None

    accepted = run_python(prepare_command(repo, handoff, "payment-boundary"), capture_output=True, text=True)
    assert accepted.returncode == 0, accepted.stdout
    # The decision opens the handoff; a handoff whose receipt and proof still lead it is refused, never read as generic.
    sealed_lines = handoff.read_text(encoding="utf-8").splitlines()
    assert sealed_lines[0].startswith("# Architecture Decision: ")
    assert sealed_lines[-1].startswith(f"<!-- architecture: {ARCHITECT_VERSION}; sha256: ")
    legacy = repo / ".first-four-hours" / "architectures" / "legacy" / "architecture.md"
    legacy.parent.mkdir()
    legacy.write_text("\n".join([sealed_lines[-1], sealed_lines[-2], *sealed_lines[:-2]]) + "\n", encoding="utf-8")
    refused_legacy = run_python(prepare_command(repo, legacy, "legacy"), capture_output=True, text=True)
    assert refused_legacy.returncode == 1
    assert json.loads(refused_legacy.stdout)["diagnostics"][0]["code"] == "handoff.receipt.malformed"
    legacy.unlink()
    legacy.parent.rmdir()
    stray = repo / ".first-four-hours" / "architectures" / "architecture.md"
    external = tmp_path / "external" / "architecture.md"
    for copy in (external, stray):
        copy.parent.mkdir(exist_ok=True)
        copy.write_bytes(handoff.read_bytes())
        refused = run_python(prepare_command(repo, copy, "refused"), capture_output=True, text=True)
        assert refused.returncode == 1
        diagnostic = json.loads(refused.stdout)["diagnostics"][0]
        assert diagnostic["code"] == "handoff.architecture.identity"
        assert ".first-four-hours/architectures/<slug>/architecture.md" in diagnostic["message"]
    stray.unlink()

    # An unrelated untracked file in the artifact root leaves a fresh handoff current for Blueprint.
    notes = repo / ".first-four-hours" / "notes.txt"
    notes.write_text("user notes\n", encoding="utf-8")
    noted = run_python(seal_command(repo, "noted", draft, json_output=True), capture_output=True, text=True, check=True)
    noted_handoff = Path(json.loads(noted.stdout)["path"])
    noted_prepare = run_python(prepare_command(repo, noted_handoff, "noted"), capture_output=True, text=True)
    assert noted_prepare.returncode == 0, noted_prepare.stdout
    notes.unlink()

    (repo / "unrelated.txt").write_text("new head\n", encoding="utf-8")
    run_python(["git", "add", "."], cwd=repo, capture_output=True, text=True, check=True)
    run_python(["git", "commit", "-m", "second"], cwd=repo, capture_output=True, text=True, check=True)

    stale = run_python(seal_command(repo, "stale", handoff, json_output=True), capture_output=True, text=True)
    assert stale.returncode == 1
    assert "architecture proof snapshot does not match" in stale.stdout
    assert not (repo / ".first-four-hours" / "architectures" / "stale").exists()

    # A non-Git root binds a filesystem snapshot that must not count the sealed handoff itself.
    plain = make_repo(tmp_path / "plain")
    sealed_plain = run_python(seal_command(plain, "payment-boundary", draft, json_output=True), capture_output=True, text=True, check=True)
    plain_handoff = plain / ".first-four-hours" / "architectures" / "payment-boundary" / "architecture.md"
    assert json.loads(sealed_plain.stdout)["git_ignored"] is False
    assert proof_snapshot(plain_handoff)["kind"] == "filesystem"
    accepted_plain = run_python(prepare_command(plain, plain_handoff, "payment-boundary"), capture_output=True, text=True)
    assert accepted_plain.returncode == 0, accepted_plain.stdout

    # Without a HEAD commit the snapshot binds only tracked and non-ignored untracked files.
    unborn = make_repo(tmp_path / "unborn")
    run_python(["git", "init", "-q", "-b", "main"], cwd=unborn, capture_output=True, text=True, check=True)
    (unborn / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    run_python(seal_command(unborn, "payment-boundary", draft, json_output=True), capture_output=True, text=True, check=True)
    unborn_handoff = unborn / ".first-four-hours" / "architectures" / "payment-boundary" / "architecture.md"
    unborn_snapshot = proof_snapshot(unborn_handoff)
    assert unborn_snapshot["kind"] == "filesystem"
    cache = unborn / "node_modules" / ".vite" / "results.json"
    cache.parent.mkdir(parents=True)
    cache.write_text("{}\n", encoding="utf-8")
    cached = run_python(prepare_command(unborn, unborn_handoff, "cached"), capture_output=True, text=True)
    assert cached.returncode == 0, cached.stdout

    # The no-HEAD snapshot neither walks the tree nor reads ignored output.
    walked: list[Path] = []
    read: list[Path] = []
    real_rglob, real_read_bytes = Path.rglob, Path.read_bytes
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "rglob", lambda self, pattern, *args, **kwargs: walked.append(self) or real_rglob(self, pattern, *args, **kwargs))
        patch.setattr(Path, "read_bytes", lambda self: read.append(self) or real_read_bytes(self))
        assert _snapshot(unborn)["fingerprint"] == unborn_snapshot["fingerprint"]
    assert walked == []
    assert [path for path in read if "node_modules" in path.parts] == []

    def forge_pre_scope(handoff: Path) -> Path:
        lines = handoff.read_text(encoding="utf-8").splitlines()
        snapshot = {**proof_snapshot(handoff), "scope_version": "1.0.0", "fingerprint": "0" * 64}
        proof = json.dumps({"snapshot": snapshot}, sort_keys=True, separators=(",", ":"))
        with_proof = "\n".join(lines[:-2]) + f"\n<!-- architecture-proof: {proof} -->\n"
        digest = hashlib.sha256(with_proof.encode("utf-8")).hexdigest()
        forged = handoff.parent.parent / "pre-scope" / "architecture.md"
        forged.parent.mkdir()
        forged.write_bytes((with_proof + f"<!-- architecture: 1.0.0; sha256: {digest} -->\n").encode("utf-8"))
        return forged

    # A stale pre-1.0.1 handoff in a Git worktree names its older scope and the reseal step; outside Git it stays generic.
    refused_old = run_python(prepare_command(unborn, forge_pre_scope(unborn_handoff), "pre-scope"), capture_output=True, text=True)
    assert refused_old.returncode == 1
    old_diagnostic = json.loads(refused_old.stdout)["diagnostics"][0]
    assert old_diagnostic["code"] == "handoff.architecture.invalid"
    assert "sealed before Architect 1.0.1" in old_diagnostic["message"]
    refused_plain = run_python(prepare_command(plain, forge_pre_scope(plain_handoff), "pre-scope"), capture_output=True, text=True)
    assert refused_plain.returncode == 1
    assert json.loads(refused_plain.stdout)["diagnostics"][0]["message"] == "architecture proof snapshot does not match the current repository"

    # A non-ignored file written after sealing, even with a non-ASCII name, still stales the no-HEAD handoff.
    (unborn / "scaffold-é.txt").write_text("new source\n", encoding="utf-8")
    scaffolded = run_python(prepare_command(unborn, unborn_handoff, "scaffolded"), capture_output=True, text=True)
    assert scaffolded.returncode == 1
    scaffold_diagnostic = json.loads(scaffolded.stdout)["diagnostics"][0]
    assert scaffold_diagnostic["code"] == "handoff.architecture.invalid"
    assert scaffold_diagnostic["message"] == "architecture proof snapshot does not match the current repository"


def test_git_status_failure_never_seals_a_clean_snapshot(tmp_path: Path) -> None:
    draft = tmp_path / "draft.md"
    draft.write_text(example(), encoding="utf-8")

    tracked = make_repo(tmp_path / "tracked")
    (tracked / ".first-four-hours" / "architectures").mkdir(parents=True)
    (tracked / ".first-four-hours" / "architectures" / "notes.md").write_text("project notes\n", encoding="utf-8")
    init_git(tracked)
    refused = run_python(seal_command(tracked, "payment-boundary", draft, json_output=True), capture_output=True, text=True)
    assert refused.returncode == 1
    assert "workspace.unsafe" in refused.stdout
    assert "already contains tracked project files" in refused.stdout
    assert not (tracked / ".first-four-hours" / "architectures" / "payment-boundary").exists()

    linked_repo = make_repo(tmp_path / "linked")
    init_git(linked_repo)
    outside = tmp_path / "outside"
    outside.mkdir()
    (linked_repo / ".first-four-hours" / "architectures").mkdir(parents=True)
    _link_dir(linked_repo / ".first-four-hours" / "architectures" / "linked", outside)
    linked = run_python(seal_command(linked_repo, "linked", draft, json_output=True), capture_output=True, text=True)
    assert linked.returncode == 1
    assert "workspace.unsafe" in linked.stdout
    assert "is not a real directory" in linked.stdout
    assert list(outside.iterdir()) == []

    root_repo = make_repo(tmp_path / "linked-root")
    init_git(root_repo)
    root_outside = tmp_path / "root-outside"
    root_outside.mkdir()
    _link_dir(root_repo / ".first-four-hours", root_outside)
    linked_root = run_python(seal_command(root_repo, "linked", draft, json_output=True), capture_output=True, text=True)
    assert linked_root.returncode == 1
    assert "workspace.unsafe" in linked_root.stdout
    assert "is not a real directory" in linked_root.stdout
    assert list(root_outside.iterdir()) == []

    repo = make_repo(tmp_path / "repo")
    init_git(repo)
    run_python(["git", "config", "status.relativePaths", "invalid-boolean"], cwd=repo, check=True)
    result = run_python(seal_command(repo, "payment-boundary", draft, json_output=True), capture_output=True, text=True)
    assert result.returncode == 1
    assert "cannot establish Git status" in result.stdout
    assert not (repo / ".first-four-hours" / "architectures" / "payment-boundary" / "architecture.md").exists()

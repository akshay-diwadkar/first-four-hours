from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills" / "workbench" / "architect"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

from architecture_contract import validate_handoff  # noqa: E402


def make_repo(root: Path) -> Path:
    (root / "payments").mkdir()
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


def minimal() -> str:
    return """# Architecture Decision: Use Payment Gateway

## Context

Provider details leak into checkout. `user-request` `payments/service.py:1-7`

## Decision

- Selected architecture: Use a payment gateway boundary. `payments/service.py:1-7`
- Owner / boundary: Payments owns provider translation. `payments/service.py:1-7`
- Invariants / constraints: Checkout keeps charge controls. `checkout/process.py:1-6`
- Consequences: Provider exceptions stop being caller policy. `payments/service.py:1-7`

## Evidence and Uncertainty

Known caller evidence is enough for this targeted decision; full caller inventory is for blueprint. `checkout/process.py:1-6`

## Evidence Ledger

- source: request | locator: user-request | claim: Provider behavior must stop leaking into callers.
- source: code | locator: payments/service.py:1-7 | anchor: charge_payment | claim: Payment service creates provider requests.
- source: code | locator: checkout/process.py:1-6 | anchor: checkout | claim: Checkout is a domain caller.
"""


def codes(text: str, repo: Path) -> set[str]:
    _parsed, diagnostics = validate_handoff(text, repo)
    return {diagnostic.code for diagnostic in diagnostics}


def test_missing_cited_source_is_rejected(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    workspace = repo / ".first-four-hours" / "architectures" / "prior" / "architecture.md"
    workspace.parent.mkdir(parents=True)
    workspace.write_bytes((repo / "payments/service.py").read_bytes())
    assert "evidence.path.planning" in codes(minimal().replace("payments/service.py:1-7", ".first-four-hours/architectures/prior/architecture.md:1-7"), repo)
    (repo / "payments/service.py").unlink()
    assert "evidence.path.missing" in codes(minimal(), repo)

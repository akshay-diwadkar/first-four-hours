# Architecture Decision: Isolate Payment Provider Semantics

## Context

Checkout and subscription behavior depend on provider request fields and provider exception classes, so an SDK change propagates beyond the payment integration owner. The design covers the synchronous charge contract and its caller-visible failures; settlement workflows and provider selection policy are outside this decision. `user-request` `payments/service.py:1-7` `checkout/process.py:1-6`

## Decision

- Selected architecture: Callers submit a domain-owned `ChargeRequest` to `PaymentGateway.charge`; the payment integration owner translates provider requests, results, and exceptions. `payments/service.py:1-7` `checkout/process.py:1-6`
- Owner / boundary: Payments integration owns provider translation and its invariants at the domain payment operations to provider integration boundary. `payments/service.py:1-7` `subscriptions/renew.py:1-4`
- Invariants / constraints: Callers keep amount, currency, payment token, and idempotency controls; provider request construction, timeout policy, and SDK exception taxonomy stay behind the integration boundary. `payments/service.py:1-7` `checkout/process.py:1-6`
- Consequences: The caller-visible error surface shrinks to stable domain payment outcomes while provider-specific distinctions remain observable inside the integration boundary. `payments/service.py:1-7` `tests/test_checkout.py:1-6`
- User-owned policy: The request sets the policy that provider behavior must stop leaking into checkout and subscription callers. `user-request`

## Evidence and Uncertainty

The evidence shows one provider-shaped service seam and two independent domain callers. The architecture is settled for synchronous charge attempts; the exact caller inventory and characterization-test placement remain implementation planning facts for `blueprint`, not architecture decisions. `payments/service.py:1-7` `checkout/process.py:1-6` `subscriptions/renew.py:1-4`

## Alternatives and Tradeoffs

A concrete payment-service function boundary was considered because it would centralize call sites quickly. It was rejected because checkout and subscription orchestration have different lifecycles; the shared structural pressure is provider translation and error mapping, not ownership of domain workflow policy. This ownership discriminator favors the gateway boundary. `checkout/process.py:1-6` `subscriptions/renew.py:1-4`

## View / Contract

Caller contract: `PaymentGateway.charge(request: ChargeRequest) -> PaymentResult`. `ChargeRequest` carries amount, currency, optional payment token, and optional idempotency key. Caller-visible errors are `PaymentDeclined` and `PaymentUnavailable`; `PaymentUnavailable` does not prove the provider declined the charge. These semantics must be visible to callers before implementation. `payments/service.py:1-7` `tests/test_checkout.py:1-6`

## Evidence Ledger

- source: request | locator: user-request | claim: Provider-specific request and failure behavior should stop leaking into checkout and subscription callers.
- source: code | locator: payments/service.py:1-7 | anchor: charge_payment | claim: The payment service constructs provider SDK requests and exposes provider exceptions directly.
- source: code | locator: checkout/process.py:1-6 | anchor: checkout | claim: Checkout supplies provider-specific optional values and handles provider timeout types.
- source: test | locator: tests/test_checkout.py:1-6 | anchor: test_checkout_decline | claim: Current tests assert provider-specific decline behavior at a domain call site.
- source: code | locator: subscriptions/renew.py:1-4 | anchor: renew | claim: Subscription renewal is a second caller of the same payment operation.

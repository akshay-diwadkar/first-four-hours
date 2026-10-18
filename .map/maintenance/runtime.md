# Standalone runtimes and projections

- [Common CLI protocol](../../tools/skill_protocol/README.md): start with command lifecycles, manifests, structured diagnostics, and standalone adapters.
- [Canonical protocol runtime](../../tools/skill_protocol/runtime.py): inspect the implementation behind the shared CLI contract.
- [Runtime synchronization](../../tools/validation/sync_skill_protocol_runtime.py): trace the canonical runtime into each executable package's local fallback.
- [Diagnostic runtime](../../tools/diagnostics/runtime.py): canonical repair-ready diagnostic shape; [its synchronizer](../../tools/validation/sync_diagnostic_runtime.py) projects it into executable skills.
- [Classification runtime](../../tools/classification/runtime.py): canonical deterministic classification; [its synchronizer](../../tools/validation/sync_classification_runtime.py) projects the portable copies.
- [Architecture handoff verifiers](../../tools/validation/sync_architecture_handoff.py): derive the standalone verifiers that consuming skills use for Architect handoffs.
- [Delegation doctrine](../../SKILL_PHILOSOPHY.md): read the shared authority and bounded-labor contract before modifying delegation guidance.
- [Delegation projection](../../tools/validation/sync_delegation_projection.py): trace mechanically derived standalone guidance and disposition validation.
- [Repository validator](../../tools/validation/validate_repository.py): locate the checks that fail when a projection drifts from its source.

Installed packages must operate without this repository's tools directory. Local runtime copies are distribution projections: edit the canonical source under `tools/` and run its synchronizer rather than editing a copy. Blueprint/Construct also share a paired runtime with no synchronizer; consult Planning traps in [versioning policy](../../REPO_VERSIONING.md) before changing either copy.

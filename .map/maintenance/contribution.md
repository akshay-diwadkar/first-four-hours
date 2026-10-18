# Contribution and validation

- [Root agent instructions](../../AGENTS.md): start with repository-specific obligations before changing skills or their supporting machinery.
- [Contributor entry point](../../CONTRIBUTING.md): set up the validation environment and start a policy-directed contribution.
- [Contributor workflow](../../docs/contributing/README.md): locate change ownership, focused and required validation, guidance budgets, package projections, and release maintenance.
- [Documentation rules](../../docs/contributing/documentation.md): read before adding or changing a `docs/` page; it sets the sections, conventions, voice, and where validation policy may be explained.
- [Skill philosophy](../../SKILL_PHILOSOPHY.md): apply the Change Gate and distinguish agent-owned judgment from mechanical guarantees.
- [Versioning and validation](../../REPO_VERSIONING.md): authoritative branch, release, test-cap, timing, and verification policy, including known planning traps.
- [Ownership manifest](../../tools/validation/test-ownership.json): resolve changed paths to their test profiles before modifying or selecting tests.
- [Supervised runner](../../tools/validation/test_ownership.py): trace selection, collection, and required verification behavior.
- [Repository validator](../../tools/validation/validate_repository.py): locate cross-package metadata, synchronization, documentation link, and Atlas hierarchy checks.
- [Context load measurement](../../tools/validation/measure_context_load.py): measure each skill's guidance tokens against [its recorded budget](../../tools/validation/context-load-budgets.json); before editing skill guidance, estimate a Blueprint draft's Exact guidance edits with its `--blueprint` mode (Planning traps in versioning policy).
- [Pinned instruction rules](../../tests/repository/mandatory_skill_rules.json): exact clauses in skill guidance that [the rule checker](../../tools/validation/instruction_rules.py) requires; rewording a pinned clause fails validation.

A skill-guidance edit must fit its recorded budget, keep any pinned clause it touches, and change together with the skill and release version files that versioning policy names. In a delegation protocol, the marked projection region is generated from shared doctrine: edit the doctrine and re-sync, never the region (see [standalone runtimes](runtime.md)).

Verification selection and completion depend on the ownership manifest and supervised runner together. Consult the policy before interpreting a partial or timed-out run; individual passing checks do not establish a complete repository pass.

# Architecture-to-Blueprint handoff

`architect` emits one validated `architecture.md`. Supply that exact file to `blueprint` as settled architecture evidence; `blueprint` writes one separate implementation-complete `blueprint.md` and runs its own stateless sealer.

The public Architect entrypoint is the skill CLI. It validates the draft, binds repository snapshot and evidence bytes, and atomically publishes the sole handoff in one command to the target repository's `.first-four-hours/architectures/<slug>/`, which one worktree-local `.git/info/exclude` rule keeps ignored. No committed `.gitignore` entry is needed. The command fails closed on a non-top-level root, an unsafe exclude path, a tracked or linked namespace, or other files in the slug directory. The workspace is never architecture evidence:

```bash
python /absolute/architect/scripts/cli.py --repo-root /absolute/repo \
  --input draft=/absolute/architecture-draft.md \
  --input slug=payment-boundary --format json run
```

On success the JSON response is complete, its `result.path` is `/absolute/repo/.first-four-hours/architectures/payment-boundary/architecture.md`, and `result.git_ignored` reports whether Git ignores it. Blueprint accepts `architecture.md` only from that namespace:

```bash
python /absolute/blueprint/scripts/prepare_blueprint_workspace.py \
  --repo-root /absolute/repo \
  --request-file /absolute/repo/.first-four-hours/architectures/payment-boundary/architecture.md \
  --task-name payment-boundary
```

Blueprint authors the plan at the returned blueprint_path, then uses the returned sibling paths (including any collision-safe suffix):

```bash
python /absolute/blueprint/scripts/cli.py --repo-root /absolute/repo \
  --input request_file=/absolute/repo/.first-four-hours/blueprints/payment-boundary/request.md \
  --input draft_file=/absolute/repo/.first-four-hours/blueprints/payment-boundary/blueprint.md --format json run
```

The handoff remains architecture evidence and intent, not a repository inventory, implementation plan, or reasoning transcript. Blueprint reuses settled architecture owner/boundary, invariants, constraints, consequences, verified evidence, incorporated user policy, and any earned view or contract before doing its own implementation planning. Blueprint does not replay architecture discovery or re-ask settled architecture decisions merely because reasoning history is absent; a genuine architecture contradiction returns to Architect.

Valid no-design-change results stop without an implementation target. For the consumer's verified reuse and new implementation-question branches, see [Architecture intake](../blueprint/references/architecture-intake.md).

See [blueprint](../blueprint/README.md) and [ticket](../ticket/README.md) for supported planning inputs.

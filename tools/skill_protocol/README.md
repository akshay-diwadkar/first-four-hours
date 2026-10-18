# Common Skill CLI Protocol

This runtime gives executable skills one provider-neutral interface. Stateful
skills use `doctor`, `start`, `status`, `next`, and lifecycle-specific
`validate` or `finalize` transitions. Stateless skills use `doctor` plus one or
more independent manifest-declared commands; `run` remains the conventional
single-action command.
It uses only the Python standard library and invokes existing skill scripts
without a shell.

## Invocation

```text
python /absolute/runtime/tools/skill_cli.py \
  --skill-dir /absolute/installed/skill \
  --repo-root /absolute/target/repository \
  [--run-dir /absolute/external/run] \
  [--input name=value ...] \
  --format <human|json> \
  <manifest-declared command or lifecycle command>
```

An installed skill may expose `scripts/cli.py`, which fixes `--skill-dir` to
that package and passes its own path to the runtime. Responses from such an
adapter keep returning that local CLI in `next_command.argv`. Core skills
carry a synchronized standard-library fallback so this remains operable when
the repository-level `tools/` directory is absent.

`doctor` does not require a run directory. For stateful skills, `start` requires
a new run directory. Every later stateful command requires the directory created by
`start`. A skill may require the run directory to be outside the target
repository. Every skill requires it to be outside the installed skill.

A stateful manifest may declare a deterministic `classification` phase.
For those skills, `start` writes and returns the classification through
`result` without running the existing setup command. The first `next` binds the
recommended typed inputs and runs that setup. A contrary value requires the
manifest's hash-bound override input and current trusted evidence.

Inputs are not a secret store. A manifest should accept a path or environment
variable name instead of a credential value.

## Lifecycle

- `doctor` validates the interpreter, paths, manifest, scripts, and declared
  distributions without writing. For stateful skills it returns a replayable
  `start` command when ready. For stateless skills it prefers `run` when present,
  otherwise the first command in manifest declaration order.
- `start` validates inputs, runs the declared preparation command in a staging
  directory, atomically publishes the run, and records the initial phase.
- `status` reads and verifies state without running a skill command.
- `next` runs exactly one phase-declared transition. A complete run is
  idempotent.
- `validate` runs the declared validator and advances only on success.
- `finalize` is phase-gated and marks the run complete only after every
  declared finalization and post-validation step succeeds.

The runtime treats `skill-protocol.json` as trusted installed-skill metadata,
but still rejects traversal, unknown placeholders, shell strings, undeclared
artifacts, unsafe run paths, and identity changes. Child processes receive
absolute paths, run with `shell=False`, and have stdout and stderr captured.

## Output and exit codes

The response schema is `response.schema.json`. JSON mode writes exactly one
compact JSON object and one newline to stdout and writes nothing to stderr.
Human mode writes a concise summary to stdout and failure diagnostics to
stderr.

Every JSON diagnostic follows `tools/diagnostics/diagnostic.schema.json`.
It names the owning skill, phase, artifact, record, field, and path; explains
why the failure matters; lists only repairs that preserve validation
strictness; includes local supporting evidence; and supplies a replayable
argv command when a safe retry exists. Repair the reported artifact or provide
the unavailable prerequisite. Never bypass, suppress, downgrade, or weaken a
validation gate.

- `0`: a usable response was produced successfully
- `2`: invalid invocation, manifest, input, state identity, or path
- `3`: prerequisites, phase gates, or validation block progress
- `4`: an existing skill command failed operationally
- `70`: an unexpected runtime defect

`next_command.argv` is an argv array, not a shell command. Consumers must
execute it directly with `next_command.cwd`.

Classifier request and repository content is always data. The runtime never
executes embedded commands, follows links, or treats issue text, comments,
generated files, or model output as authority.

Stateless commands do not accept `--run-dir` or write protocol state, and return
wrapped structured output in the optional `result` field. A command that writes
derived repository state declares its exact `allowed_writes`; other repository
writes remain forbidden.

## Manifest contract

The manifest schema is `manifest.schema.json`. Commands contain ordered steps
and may declare exact `allowed_writes` paths.
Each step declares an argv array, optional repeated input expansions, optional
stdout artifact capture, diagnostic JSON handling, and whether failure is a
workflow block or operational error.

Allowed placeholders are `{python}`, `{skill_dir}`, `{repo_root}`, `{run_dir}`,
and `{input.<name>}`. Repeated inputs use the step's `repeat` entries and are
never interpolated into a shell.

`accepted_for` limits an input to named commands; `required_for` additionally
makes it mandatory for those commands.

Stateful phase names are skill-defined except for the required terminal
`complete` phase. `conditional_reads` can add paths for selected declared input
values without exposing unrelated references in other runs. Stateless command
execution does not use protocol phases; each command completes independently.

Stateful manifests require `start`; stateless manifests require at least one
command. Existing stateless `run` manifests retain their behavior.
Skill-defined transition commands are reached through `next`, and command
variants must resolve from declared choice inputs to exactly one branch.
`required_for` inputs may be supplied at later transitions and become
immutable when stored. External artifacts must resolve from declared path inputs, optionally with a
literal filename suffix such as `{input.output_dir}/artifact.md`, and be listed
in a stateful active phase's `allowed_writes` or the applicable stateless
command's `allowed_writes`.

Protocol 1.x may add optional behavior but will not change required response
fields, their types, command meanings, or exit-code categories. Breaking
changes require a new major `protocol_version`. A runtime accepts a manifest
or saved run state whose `protocol_version` shares its own major and refuses
any other value.

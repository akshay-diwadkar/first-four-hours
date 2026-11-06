# Executable contracts

Read this when a command's dispatch, runtime mode, adapter, phase, wrapper, input spelling, or environment can change correctness, or the plan changes tests, fixtures, helpers, or package surfaces, or a Run selects a subset of tests.

Trace the invocation through its public entrypoint and dispatch to the operation, inputs, phase, and observable result; an internal helper is not evidence of the public command. For a gate over uncommitted changes, trace which paths it reads (index, worktree, diff), planned deletions, renames, and new files included. When behavior depends on how an input is written (link, case, encoding, relative path), probe the public command with such input. Distinguish runtime modes, inspect the installed adapters and packaged resources execution uses, and follow every consumer, contract, and verification surface the diff touches; ruling one out needs a source pointer showing no consumer.

## Verification selection

Apply the actual selector's rule to every planned changed surface, both sides of renames and deletes included, and probe each Run's and Proof run's selector on the current tree (dry-run mode when available; a planned target through an existing one in the same form) to show each target exists or is planned and is accepted. A consumer exercising a fixture does not show the selector accepts it, nor owner-profile selection that a target uses a support file; establish that consumer from source or a probe. For an unselectable or ownerless surface, author the exact repair before seal, with Location, State, propagation, and a re-check of every surface; never invent a target, suppress a path, or leave the repair open.

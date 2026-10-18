# Derived Safety and Recovery

At intake, observe repository identity and Git worktree state: `verify` reports HEAD and every dirty or untracked entry. Protected unrelated dirty work is every reported path that is not an authored `**Location:**` target and not the Blueprint workspace. Keep that protected set and HEAD in the working context and re-verify them against the same Git observations before declaring completion. Planned targets that were already dirty when Blueprint sealed them are valid targets: their exact seal-time bytes are bound in the sealed proof.

Protected unrelated dirty work survives byte-for-byte: a protected path is never edited, never attributed to an instruction, and must be unchanged at completion; compare the intake and completion observations for the same paths, including each entry's returned `sha256`/`size`/`mode`/`kind` content identity, so byte changes are detected even when porcelain status is unchanged. A protected-work conflict ends this invocation for the protected work's owner to resolve before a fresh Construct invocation. A concurrent writer or moved HEAD is a `safety-contradiction`: the execution baseline is no longer trustworthy.

Repair forward from the current material state under the execution contract's local-repair boundary. Never reset or restore a whole file/worktree/index/commit/branch automatically, and never use `git stash`, `git checkout --`, `git restore`, or `git reset` as an automatic recovery shortcut.

If HEAD or repository identity changes before completion, stop with `safety-contradiction` and report the expected and observed identity; the execution contract's Stopping section owns recovery.

# Pull requests

Read this when the target is a pull request, given as a URL or `owner/repo#N` (host `github.com` unless named), whose head may be missing from the current repository, such as a fork's PR or one in a repository not cloned here.

Pass each value GitHub returns to a command as one quoted argument.

Work under `<root>`: `<temp>/first-four-hours`, where `<temp>` is Python's `tempfile.gettempdir()`. When `os.name` is `"posix"`, append `-<uid>` (`id -u`), run `mkdir -m 700` on it if absent, then stop `blocked` unless it is a directory, not a link, owned by you, with mode `700`. Keep every snapshot, the bundle, and proof output under `<root>`, outside any repository.

1. Run `gh pr view <N> --repo <host>/<owner>/<repo> --json url,number,state,baseRefOid,headRefOid` and save its output outside every repository as the `target` source, with its `url` as locator. That `url` names the base repository. No other PR field is authority.
2. Let `<dir>` be `<root>/pr-repos/<host>/<owner>/<repo>`. Stop `blocked` when `<temp>` lies inside the current repository or any part of `<dir>` below `<temp>` is a link. Assess owns `<dir>`: when it is absent, or is not a Git worktree root, delete it and run `git init <dir>`.
3. With `GIT_TERMINAL_PROMPT=0`, run `git -c credential.helper= -c "credential.helper=!gh auth git-credential" -C <dir> fetch --no-tags https://<host>/<owner>/<repo>.git +refs/pull/<N>/head:refs/first-four-hours/pr/<N>/head +<baseRefOid>:refs/first-four-hours/pr/<N>/base`; the base repository serves a fork's head too. If the fetched head is not `headRefOid`, repeat steps 1 and 3 once, saving the new snapshot to a new path; a second mismatch means `blocked`.
4. Prepare, seal, and check with `--repo-root <dir>`, the PR `url` as `target`, and those two refs as `base_ref` and `head_ref`. `<dir>` has no checkout: read the change through Git objects, such as `git -C <dir> show <headRefOid>:<path>`.
5. Before any command that executes the PR's code, such as tests or Blueprint Runs, name it and wait for the user's yes. Run an approved one from a fresh worktree: `git -C <dir> worktree remove --force <dir>-heads/<headRefOid>` when it exists, then `git -C <dir> worktree add --detach <dir>-heads/<headRefOid> <headRefOid>`. Record each declined or unrun proof in `limitations`.

When `gh` or the fetch fails, for example a missing tool, failed authentication, an unreadable or deleted PR or repository, or a corrupt `<dir>`, stop unsealed with result `blocked`, as for every `blocked` above: name the PR, the failing command, its error, and `<dir>`. No exact base/head exists to bind, so never substitute guessed revisions. Never change the user's checkout or Git configuration. The temporary folder may be cleared later; once `<dir>` or its assessment is gone, no earlier assessment qualifies for delta review.

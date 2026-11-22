# batch-ops

batch-ops is an optional MCP server that ships inside [`/provision`](../skills/provision.md). It gives your agent three tools, `batch_read`, `batch_run`, and `batch_edit`, that each do in one call what would otherwise take the agent several tool calls: read many files, run several commands, or apply several edits with rollback. Fewer calls can save an agent turns. No First Four Hours skill needs it.

## What each tool does

| Tool | Does in one call | Instead of |
| :--- | :--- | :--- |
| `batch_read` | Reads files, line ranges, outlines, blocks, greps, globs, and git history (`git:diff`, `git:changed`, `git:log`, `git:cochange`). `mode="survey"` maps the repository: its folders, recent commits, hot spots, files usually changed together, and the build and test commands its CI, Makefile, or `package.json` declare. Specs passed with `mode="survey"` are read in the same report, and `focus` paths add their recent commits, the files usually committed with them, and their related tests. | Separate read, search, glob, and git calls. |
| `batch_run` | Runs several commands concurrently, each with its own timeout, and reports failures first. Slices such as `fails`, `tail:30`, or `grep:RE` keep only the output lines you need. | One shell call per command. |
| `batch_edit` | Applies edits, new files, deletes, and renames together, then optionally runs a `verify` command. If verification fails, it restores every file. `dry_run=true` shows the diffs without writing. | Separate edit and write calls, then a test run, then manual undo. |

The full argument syntax is in each tool's description, which your harness shows the agent; you do not need to learn it.

A label on a command, or on a grep or glob read, keeps its full result (a grep's within its max_matches) for about an hour under that name, such as `artifact:tests`, so a later call can read it again without rerunning it, filtered with slices such as `json:`, `sort`, `uniq`, `countby:`, or `cut:`.

## Safeguards

- **Scope.** Reads and edits stay inside the working directory (`cwd`) unless the call sets `allow_outside=true`.
- **Stale edits.** A read prints each file's `sha`. An edit that passes that `sha` as `since` is refused if the file changed after the read.
- **Rollback.** A `batch_edit` whose `verify` command fails restores every file it touched, unless the call sets `rollback_on_failure=false`.
- **Report size.** Each report is capped at about 10,000 tokens. Cut command output is kept as an artifact the agent can read back in ranges with `batch_read`.
- **Timeouts.** A `batch_run` timeout kills the command's process tree and keeps its partial output.

## Set it up

Run `/provision` and answer yes when it offers batch-ops. After your yes, it:

1. installs the `mcp` and `pydantic` packages ([`requirements.txt`](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/provision/assets/batch-ops/requirements.txt)) with the agent's Python;
2. registers a local stdio server that runs that Python on the bundled `batch_ops_server.py`;
3. checks that your harness shows the server connected;
4. offers to add this line to your `CLAUDE.md` or `AGENTS.md`, so the agent prefers the batch-ops tools:

```text
Prefer the batch-ops MCP tools (`batch_read`, `batch_run`, `batch_edit`) over native file reading, search, shell, and edit tools whenever they are connected.
```

Without that line, the agent may still call the tools, but nothing tells it to prefer them.

[Provision](../skills/provision.md) describes the full flow, including update, keep, and remove on a rerun.

## Harness differences

| Harness | Server name | Registered for | Tool names the agent sees | Check it is connected |
| :--- | :--- | :--- | :--- | :--- |
| Claude Code | `batch-ops` | The suite's install scope, private to you | `mcp__batch-ops__batch_read`, and so on | `claude mcp list` shows it `Connected` |
| Codex | `batch_ops` | Your user account, so every project | As Codex lists them | `/mcp` lists it in a new session |
| OpenCode | `batch-ops` | Your user account, so every project | `batch-ops_batch_read`, and so on | `opencode mcp list` shows it `connected` |

On Codex, a tool call ends after `tool_timeout_sec`, 60 seconds by default. Raise that setting for longer `batch_run` calls.

## With First Four Hours subagents

When batch-ops is connected, `/provision` asks which `ffh-` subagents read, search, run commands, and edit only through batch-ops' tools, with all selected by default. [First Four Hours subagents](agents.md) lists the subagents. Changing that choice, or adding or removing batch-ops, takes a `/provision` rerun.

## Keep it working

- The server entry holds absolute paths to the Python and the server script. After you move or update the suite or that Python, run `/provision` again to rewrite the entry.
- The batch-ops version is the `Version:` line in its [README](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/provision/assets/batch-ops/README.md), kept equal to `/provision`'s version. On a rerun, `/provision` compares it with the installed copy and offers an update when they differ.
- Each report's title names a `build` hash of the code actually running, such as `# batch_read (files) build f7d4ca4`.
- To remove batch-ops, run `/provision` and choose **Remove**, or ask it to uninstall. Installed packages stay.

## Sources

- [The batch-ops server's tools](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/provision/assets/batch-ops/batch_ops/server.py)
- [Provision's batch-ops setup](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/provision/references/batch-ops.md)
- Harness notes: [Claude Code](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/provision/references/claude-code.md), [Codex](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/provision/references/codex.md), [OpenCode](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/provision/references/opencode.md)

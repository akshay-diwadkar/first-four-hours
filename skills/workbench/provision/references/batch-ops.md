# batch-ops

batch-ops, in this skill's `assets/batch-ops/`, is an optional MCP server whose tools `batch_read`, `batch_run`, and `batch_edit` batch reads, commands, and edits with rollback into one call. No skill needs it, so offer it on every run and never set it up by default:

> **batch-ops (optional).** An MCP server that batches reads, commands, and edits into one call, which can save an agent turns. It needs the `mcp` and `pydantic` Python packages; no First Four Hours skill needs it. Set it up?

When Provision's entry exists (step 3), ask instead, a version being the `Version:` line of the `README.md` beside that server script, or none:

> **batch-ops <installed> is at <entry's path>; this Provision carries <bundled>.**
> - **Update** (only when version or path differs): steps 2, 3, 5, and 6.
> - **Keep:** steps 5 and 6.
> - **Remove:** step 4.

1. **Harness.** Follow the batch-ops entry in the harness's reference, scope included. When the harness cannot run a local stdio MCP server, or neither its reference nor its official documentation says how to add one, say so, write nothing, and report it skipped.
2. **Packages.** After a yes, install `assets/batch-ops/requirements.txt` as the Requirements step installs, into the Python or virtual environment it used, else the `python` the agent runs. Take that Python's absolute path from `<python> -c "import sys; print(sys.executable)"` and check that `<python> -c "import mcp, pydantic"` succeeds. If the install or the check fails, register nothing and report why.
3. **Register.** The entry is a stdio server named `batch-ops`, or as the reference spells it: its command is that Python's absolute path, and its one argument this skill's absolute `assets/batch-ops/batch_ops_server.py` path. First look for that name in every scope the harness merges. An entry whose argument ends in `/provision/assets/batch-ops/batch_ops_server.py` (either slash) is Provision's; any other is the user's: show it and replace it only after a yes, else skip. To add or replace, remove the existing entry from its scope, then add; if the add fails, report the entry removed.
4. **Decline.** If Provision's entry exists, remove it after the user confirms, and the instructions line and guard too when present. Packages stay.
5. **Instructions line.** Once Provision's entry connects, offer to append this line to the instructions file the harness's reference names for the scope, unless present; say if that creates the file.

   ```text
   Prefer the batch-ops MCP tools (`batch_read`, `batch_run`, `batch_edit`) over native file reading, search, shell, and edit tools whenever they are connected.
   ```

6. **Guard.** Where the reference names a guard, offer it once batch-ops is done as below, unless Provision's is present with this skill's paths; until then, report it not offered, with the step that would confirm the entry:

   > **Enforce batch-ops?** The line only asks. A guard would refuse the main agent's native file and shell tools inside the project while batch-ops is connected, naming the batch-ops tool to use. <The reference's caveat, if any.>

   After a yes, install it as the reference says, with that Python, this skill's absolute `assets/batch-ops/` guard, and, for a hook, this `<launcher>`, which exits 0 once the guard is gone, where Python's missing-file exit 2 would refuse every native tool:

   ```text
   import os, runpy, sys; os.path.isfile(sys.argv[1]) and runpy.run_path(sys.argv[1], run_name='__main__')
   ```

   A hook naming a `/provision/assets/batch-ops/` guard (either slash), or the reference's guard file, is Provision's, to replace or remove. It is done once a native read or shell command in the project is refused. Without a guard, report the line as instruction-only.

batch-ops is done only when the harness shows the entry connected with this command and argument; otherwise report it written but unverified, with the step that would confirm it. Its absolute paths, and the guard's, break when the suite or that Python moves: rerun Provision to rewrite them. That Python runs batch-ops: probe batch-ops with the absolute path in its entry, never another virtual environment or a bare `python`.

# Troubleshooting

Find the symptom you see. Each entry gives the likely cause, a check that changes nothing, and the next step with who takes it. Each skill's page in [the skill index](../skills/README.md) lists all of that skill's results.

## A skill did not start, or another skill ran

- **Likely cause:** the skill is not installed for the agent you use, its name is misspelled or, with the Claude Code plugin, lacks the `first-four-hours:` prefix, or it is `model-invoked` and you named it.
- **Check:** from the project folder, run `ls .claude/skills` for `claude-code`, or `ls .agents/skills` for `codex` and `github-copilot`, and look for the skill's folder. With the Claude Code plugin, run `claude plugin list` and check that `first-four-hours@first-four-hours` shows as enabled. [The reference](../reference/README.md) gives each skill's start mode.
- **Next step:** follow "If installation fails" in [Install First Four Hours](../getting-started/installation.md) and "If the skill did not start" in [Your first run](../getting-started/first-run.md). Ask for a `model-invoked` skill's outcome in plain words; start any other skill by name when you need it to run.

## A skill stops when it runs its Python script

- **Likely cause:** the Python the agent runs is older than the skill needs, or a package the skill declares is missing.
- **Check:** run `python --version`. [The reference](../reference/README.md) gives each skill's minimum Python and links any requirements file.
- **Next step:** install a Python that meets the minimum. For a skill with a requirements file, install its packages into the Python the agent uses with `python -m pip install -r <skill folder>/requirements.txt`, where `<skill folder>` is the installed skill's folder, such as `.claude/skills/scribe`. With the Claude Code plugin, the folder is under its `installPath`, which `claude plugin list --json` reports, for example `<installPath>/skills/sensemaking/scribe`. With a local Cursor plugin, it is under the clone, for example `~/.cursor/plugins/local/first-four-hours/skills/sensemaking/scribe`.

## A skill stopped instead of writing its handoff

- **Likely cause:** the skill's folder under `.first-four-hours/` already holds files tracked by Git, or that folder or `.first-four-hours/` itself is a link or not a directory. The skill refuses to write there rather than mix its files with project content.
- **Check:** run `git ls-files .first-four-hours` to list tracked files there, and `ls -la .first-four-hours` to see whether an entry is a link or a file.
- **Next step:** the owner of those files moves them or stops tracking them; a skill never does. Then start the skill again. [How skills hand work to each other](../concepts/handoffs.md) lists each skill's folder.

## A skill rejects a handoff from an earlier step

- **Likely cause:** the handoff is stale because the files it was sealed against have changed, it belongs to another task, or an older version of the producing skill wrote it.
- **Check:** read the stopping skill's report for the reason and evidence, and confirm that the path you gave is the handoff for this task.
- **Next step:** run the skill that produced the handoff again for the current state; a sealed handoff is never edited. When a Blueprint plan no longer fits the code, Construct stops with `plan-contradiction`: run a new `/blueprint` with the original request and Construct's evidence, then a fresh `/construct`.

## Blueprint did not seal

- **Likely cause:** a question only you can answer is still open, Ideate could only report a research limit for the direction the plan needs, or no separate subagent could run the challenge.
- **Check:** read Blueprint's last message; it names the open question or the limit.
- **Next step:** answer the question, supply the missing evidence or choose another direction, or run Blueprint where a subagent is available. A changed request needs a new plan in a fresh task folder. See [Blueprint](../skills/blueprint.md).

## Construct stopped before completion

- **Likely cause:** the result names it. `plan-contradiction` means the plan is stale, wrong, or incomplete against the code; `verification-incomplete` means a check the plan declared environmental did not finish; `protected-work-conflict` means continuing would overwrite unrelated uncommitted work; `safety-contradiction` means a safety check failed or the baseline moved.
- **Check:** run `git status` and `git diff` to see what Construct applied. Construct keeps no record of its own; the worktree is its only progress.
- **Next step:** follow the table in [Construct](../skills/construct.md). A plan fault goes back to `/blueprint`; Construct never redesigns the plan. An incomplete check is never a pass.

## A skill finished without the result you expected

These results are correct answers, not failures:

| Result | Skill | Next step |
| :--- | :--- | :--- |
| `blocked` | Assess | Supply the authority or evidence it names as missing or contradictory, then run Assess again. |
| `clear` | Assess | No material defect was found. It is not approval; the merge decision stays yours. |
| `needs-info`, `blocked`, `close-candidate`, or `needs-decomposition` | Ticket `select` | Make the missing decision, clear the blocker, close the ticket, or split it. You decide whether to persist replacement tickets. |
| `experiment-first` or `research-limited` | Ideate | Run the named experiment, or accept the research limit and change the goal or the evidence. |
| A `None:` route, or a route that stops early | Router | The current state already meets the target, or the next step depends on a result that does not exist yet. Ask for a fresh route once it does. |
| A finding with missing evidence | Diagnose | Gather the evidence it names, then run Diagnose again. |
| A gap with its next owner | Scribe | The named owner supplies the missing source; then write again. |
| A charter left in `settling` | Charter | Answer the open questions it names, starting with any missing observable success, then run `/charter` again; it resumes the same file. |
| A publication stop such as `charter.umbrella_differs` or `charter.issue_changed` | Charter | The GitHub issue holds text you have not confirmed. Read it, then decide whether to bring the charter to it or replace it. |

## Atlas is missing or out of date

- **Likely cause:** the project has no Atlas wiki, or a file a pointer cites was moved, renamed, or deleted.
- **Check:** a missing wiki blocks nothing; skills read the project files directly. For a stale wiki, start Atlas with `/atlas` or ask the agent in plain words to check the Atlas wiki. Its read-only hierarchy check reports structural, reachability, link-safety, and portability problems.
- **Next step:** whoever changes a cited file updates its pointer in the same work. Construct repairs links to files its plan deletes and lists other affected pointers for the next plan. See [Atlas](../skills/atlas.md).

## Repository validation did not pass

This entry is for contributors running the repository's required validation. [The versioning and validation policy](../../REPO_VERSIONING.md) owns the command, its limits, and how to repair, rerun, and handle a slow run. Read the verdict from the final `validation-budget` record the command prints, not from earlier output.

| Record | Meaning |
| :--- | :--- |
| `valid` is `true` | Passed. When `slow` is also `true`, the run took longer than `advisory_target_seconds`, and the pass still stands. |
| `status` is `failed` | Failed. `failed_cases` names the failed cases; when it is empty, read the output above the record for what failed. |
| `reason` is `verification_already_running` | Incomplete: another validation command in this checkout holds the lock. |
| `reason` is `work_deadline` or `report_deadline` | Incomplete, even when `failed_cases` lists cases: the run reached the `budget_seconds` deadline. `unverified_cases` lists the cases it did not finish. |
| `valid` is `false` with any other `reason` | Not a pass. Read the output above the record for what stopped the run. |

Only `valid` `true` is a pass; a failed or incomplete run never counts as one. For what to do next, follow the versioning and validation policy.

## Still stuck

Open an issue at https://github.com/akshay-diwadkar/first-four-hours/issues with the skill, the request you gave, and its last message.

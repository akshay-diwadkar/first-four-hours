---
name: provision
description: Set up First Four Hours on the harness running it. Installs the installed skills' Python requirements after confirmation and writes ffh-* subagents for the suite's delegated work, each on the model and effort the user chooses from the harness's current list. Use on first install, after a harness or model update to refresh stale choices, or to remove those subagents.
disable-model-invocation: true
metadata:
  version: "1.0.0"
---

# Provision

Set up First Four Hours for the harness running you: install the skills' Python requirements, then write `ffh-*` subagents for the suite's delegated work, each on the model and effort the user chooses. Run it again after a harness update or to refresh stale model choices; ask it to uninstall to remove the subagents.

Write only confirmed package installs, a virtual environment the user confirmed, and agent files named `ffh-<role>` or `ffh_<role>` inside the harness's agent directory for the chosen scope; those agent files belong to Provision. Never edit, move, or delete any other file. Name no model or effort level in this skill or its references: models and effort come from the harness's current list and the user.

## Workflow

1. **Locate.** Identify the harness running you and the scope the suite was installed in: project when its skills sit in the current project, user otherwise, including plugin installs; ask only when that is unclear. Read that harness's reference: [Claude Code](references/claude-code.md), [Codex](references/codex.md), or [OpenCode](references/opencode.md); for any other harness, [Other harnesses](references/other-harnesses.md). Re-check each fact you use against the official pages a reference cites when the installed harness version differs from the version it was checked against, or when the reference says to; follow those pages where they differ.
2. **Requirements.** Find each `requirements.txt` in the installed First Four Hours skill folders. List the files and their packages, ask once whether to install them with the `python` the agent runs, and install only after a yes. On an externally-managed-environment (PEP 668) error, never pass `--break-system-packages`. Instead, offer a virtual environment, created only after a yes at a location the user confirms, and tell the user the agent must run with it active for the skills to find the packages.
3. **Capabilities.** Read [Agents](references/agents.md). If the harness has no custom subagents or no per-agent model setting, write no agents: report that the skills keep their generic subagents, and go to step 6. Map each agent's capabilities onto the harness as its reference says. For each agent with a limit the harness cannot enforce, show this, filled in, and let the user choose, offering no default:

   > **`<agent>` can't be limited to <capabilities> on <harness>.** <What the harness can and cannot block.> That limit would rest only on the agent's instructions, and the agent could still <what stays possible> if it ignored them.
   > - **Skip:** no `<agent>`. The skills keep using a generic subagent, as they do today.
   > - **Accept:** create it with instruction-only enforcement.

4. **Models.** List the models the harness offers now, by its reference's method; when that fails, ask the user instead of guessing. For each agent, recommend the cheapest model and effort likely to give a quality result for its role, with a one-line reason, and offer effort only where the harness and model support it. Show one table: agent, current model and effort (on a re-run, flagging any the harness no longer offers), recommendation, and reason. The user accepts every recommendation, or keeps or overrides per agent.
5. **Write.** Write each chosen agent in the harness's native format and scope, with its name in the harness's spelling and its description, capabilities, and instructions exactly as [Agents](references/agents.md) gives them, plus the chosen model and effort. On a harness without a reference, show the user each file and write it only after a yes. On a re-run, rewrite the locked fields, carry over only the model and effort the user kept, and list what changed. When the user skips an agent that already has a file, or the harness no longer qualifies, delete that agent's file after the user confirms.
6. **Verify and report.** An agent is done only when the harness shows it loaded, with the chosen model and every limit the harness enforces as written; a limit the user accepted as instruction-only counts as accepted, not unverified. Otherwise report the agent as written but unverified, with the step that would confirm it, such as a restart or a new session. Report each agent's state, model, and effort; each skipped, removed, or instruction-only agent; the requirements installed or declined; and any restart needed.

## Uninstall

When asked to uninstall, list the `ffh-<role>` and `ffh_<role>` agent files in the harness's agent directory for the scope, confirm them with the user, and delete only those files. Installed packages stay.

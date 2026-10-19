# Install First Four Hours

Skills are folders your coding agent loads. You add them to a project, or to your user account, with the Skills CLI. On Claude Code, you can instead install them as plugins.

## What you need

- Node.js, for `npx`, which runs the Skills CLI.
- Python 3.11 or later, available as `python`. Many skills run Python scripts that ship with them.
- A coding agent that loads skills. The repository's own install check covers the agent names `claude-code`, `codex`, and `github-copilot`.
- A folder to work in. Workbench skills work on the project folder you start them in, usually a Git repository. The Learning skills, `tutor` and `examiner`, work in any folder.

## Install the whole suite

Run this from your project's root folder:

```bash
npx skills add akshay-diwadkar/first-four-hours --skill '*'
```

If you are unsure what you need, install the whole suite: some skills bring in others while they run.

## Install one skill

```bash
npx skills add akshay-diwadkar/first-four-hours --skill blueprint
```

Replace `blueprint` with the name of the skill you want. For planning, install `blueprint` and `construct` together with `ideate`, which Blueprint uses while it plans, and `reason`, which Ideate consults. Construct needs no other skill.

Many skills, including Diagnose and Tutor, consult `reason` at their judgment points. When you install one of them on its own, install `reason` too. [How skills hand work to each other](../concepts/handoffs.md) lists the skills that consult it.

## Choose the agent and where skills go

To install for one named agent, add `--agent` with `claude-code`, `codex`, or `github-copilot`:

```bash
npx skills add akshay-diwadkar/first-four-hours --skill '*' --agent codex
```

Add `--global` to install for your user account, so every project can use the skills instead of only the current one.

## Install as Claude Code plugins

On Claude Code 2.1.275 or later, you can install the suite as three plugins instead of using the Skills CLI. Each plugin holds one domain: `workbench-skills`, `sensemaking-skills`, and `learning-skills`. Install all three: skills in one domain use skills in another, for example Blueprint uses Ideate, and many skills consult Reason.

Run these in a Claude Code session:

```text
/plugin install workbench-skills --marketplace akshay-diwadkar/first-four-hours
/plugin install sensemaking-skills --marketplace akshay-diwadkar/first-four-hours
/plugin install learning-skills --marketplace akshay-diwadkar/first-four-hours
```

The first command also adds the `first-four-hours` marketplace. The plugins install for your user account, so every project can use them. Claude Code fetches the marketplace with Git, so you need `git` as well as Python 3.11 or later. For Claude Code, use either the plugins or the Skills CLI, not both, or each skill appears twice.

A plugin skill's name starts with its plugin's name. Start Diagnose with `/workbench-skills:diagnose`, Ideate with `/sensemaking-skills:ideate`, and Tutor with `/learning-skills:tutor`. Each skill keeps its start mode.

The plugins follow the repository's latest commit. To update them, run `/plugin marketplace update first-four-hours` in a session, or `claude plugin update <plugin>@first-four-hours` in a terminal, then start a new session.

## Check the installation

A project install puts one folder per skill, each holding a `SKILL.md`, in `.claude/skills/` for `claude-code` and in `.agents/skills/` for `codex` and `github-copilot`. It also writes `skills-lock.json` in the project folder.

From your project folder, run:

```bash
ls .claude/skills
```

For `codex` or `github-copilot`, run `ls .agents/skills` instead.

A `--global` install lives in your user account instead of the project. For the Claude Code plugins, run `claude plugin list` in a terminal: `workbench-skills@first-four-hours`, `sensemaking-skills@first-four-hours`, and `learning-skills@first-four-hours` each show as enabled, and `claude plugin details workbench-skills@first-four-hours` lists that plugin's skills. For any install, the real check is starting a skill: see [Your first run](first-run.md).

## If installation fails

- `npx` is not found: install Node.js, then open a new terminal.
- The skill folders are missing, or are in the other folder: run the install again with the `--agent` name of the agent you use.
- A plugin install cannot fetch the marketplace: check that `git --version` works and that you can reach github.com, then run the install again.
- The agent does not recognize a skill you name: check that the folder from the previous section holds that skill's `SKILL.md`, then start a new agent session from the project folder.
- A skill starts but stops when it runs its Python script: check that `python --version` reports 3.11 or later.
- Anything else: open an issue at https://github.com/akshay-diwadkar/first-four-hours/issues with the command you ran and its output.

## Next

- [Your first run](first-run.md): start one skill on a real problem.
- [Choose a skill](choosing-a-skill.md): find the skill for the problem in front of you.

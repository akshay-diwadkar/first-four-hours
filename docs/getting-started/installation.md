# Install First Four Hours

Skills are folders your coding agent loads. You add them to a project, or to your user account, with the Skills CLI. On Claude Code, you can instead install the whole suite as one plugin.

## What you need

- For the Skills CLI route, Node.js provides `npx`.
- For the Claude Code plugin route, Git fetches the marketplace; Node.js is not required for that route.
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

## Install as a Claude Code plugin

On Claude Code 2.1.275 or later, you can install all 14 skills as one `first-four-hours` plugin instead of using the Skills CLI. Workbench, Sensemaking, and Learning remain categories in the source and documentation; one plugin contains the whole suite.

Run this in a Claude Code session:

```text
/plugin install first-four-hours --marketplace akshay-diwadkar/first-four-hours
```

The command adds the `first-four-hours` marketplace if needed and installs the plugin for your user account, so every project can use it. You need Git and Python 3.11 or later for this route. For Claude Code, choose either the plugin or the Skills CLI to avoid duplicate skills.

Plugin skill names start with `first-four-hours:`. Start Diagnose with `/first-four-hours:diagnose`, Ideate with `/first-four-hours:ideate`, and Tutor with `/first-four-hours:tutor`. Each skill keeps its start mode.

The plugin has no pinned version and follows repository commits. To update it, run `/plugin marketplace update first-four-hours` in a Claude Code session, or `claude plugin update first-four-hours@first-four-hours` in a terminal, then start a new session.

## Replace an earlier plugin installation

If you added the retired `akshay-diwadkar-skills` marketplace, first remove it in a Claude Code session:

```text
/plugin marketplace remove akshay-diwadkar-skills
```

For the three preview plugins under `first-four-hours`, run `claude plugin list` in a terminal and uninstall only the old entries it lists. Use the applicable commands:

```bash
claude plugin uninstall workbench-skills@first-four-hours
claude plugin uninstall sensemaking-skills@first-four-hours
claude plugin uninstall learning-skills@first-four-hours
```

The earlier guide installed at user scope. If you installed an entry at project or local scope instead, append `--scope project` or `--scope local` to its uninstall command. If none of these entries is installed, skip their uninstall commands.

If the `first-four-hours` marketplace is already added, refresh it with `/plugin marketplace update first-four-hours`. Then run the single-plugin install command above. This removes duplicate skill registrations when moving from a partial or complete preview installation.

## Check the installation

A project install puts one folder per skill, each holding a `SKILL.md`, in `.claude/skills/` for `claude-code` and in `.agents/skills/` for `codex` and `github-copilot`. It also writes `skills-lock.json` in the project folder.

From your project folder, run:

```bash
ls .claude/skills
```

For `codex` or `github-copilot`, run `ls .agents/skills` instead.

A `--global` install lives in your user account instead of the project. For the Claude Code plugin, run `claude plugin list` in a terminal: this suite should have only `first-four-hours@first-four-hours` enabled. Run `claude plugin details first-four-hours@first-four-hours` to list its 14 skills. For any install, the real check is starting a skill: see [Your first run](first-run.md).

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

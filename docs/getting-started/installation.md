# Install First Four Hours

Skills are folders your coding agent loads. You add them to a project, or to your user account, with the Skills CLI. On Claude Code or Cursor, you can instead install the whole suite as one plugin.

## What you need

- For the Skills CLI route, Node.js provides `npx`.
- For the Claude Code or Cursor plugin route, Git fetches the plugin; Node.js is not required for those routes.
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

On Claude Code 2.1.275 or later, you can install all 15 skills as one `first-four-hours` plugin instead of using the Skills CLI.

Run this in a Claude Code session:

```text
/plugin install first-four-hours --marketplace akshay-diwadkar/first-four-hours
```

The command adds the `first-four-hours` marketplace if needed and installs the plugin for your user account, so every project can use it. You need Git and Python 3.11 or later for this route. For Claude Code, choose either the plugin or the Skills CLI to avoid duplicate skills.

Plugin skill names start with `first-four-hours:`. Start Diagnose with `/first-four-hours:diagnose`, Ideate with `/first-four-hours:ideate`, and Tutor with `/first-four-hours:tutor`. Each skill keeps its start mode.

The plugin has no pinned version and follows repository commits. To update it, run `/plugin marketplace update first-four-hours` in a Claude Code session, or `claude plugin update first-four-hours@first-four-hours` in a terminal, then start a new session.

## Install as a Cursor plugin

In Cursor, you can install all 15 skills as one `first-four-hours` plugin instead of using the Skills CLI. You need Git and Python 3.11 or later for this route.

To install it for yourself, clone the repository into Cursor's local plugin folder:

```bash
git clone https://github.com/akshay-diwadkar/first-four-hours "$HOME/.cursor/plugins/local/first-four-hours"
```

Then restart Cursor or run **Developer: Reload Window**, and open **Customize** to confirm that the skills appear. On an Enterprise plan, an administrator must first turn on **Allow Local Plugin Imports**. To update the plugin, run `git -C "$HOME/.cursor/plugins/local/first-four-hours" pull`, then reload the window.

On a Teams or Enterprise plan, an administrator can instead add the repository for the whole team: in the Cursor dashboard, open **Plugins & MCPs**, choose **Add Marketplace** under **Team Marketplaces**, choose **Import from Repo**, and paste `https://github.com/akshay-diwadkar/first-four-hours`. Team members then install `first-four-hours` from **Customize**.

Cursor also loads skills from `.agents/skills/` and `.claude/skills/`, in a project or in your user folder, which is where the Skills CLI installs them. Use either the plugin or the Skills CLI to avoid duplicate skills.

Start a skill by typing `/` in the chat and choosing it. Each skill keeps its start mode, except that Cursor has no setting to hide a skill from `/`: it also lists `router`, which the agent starts on its own, so ask for Router's outcome in plain words instead.

## Check the installation

A project install puts one folder per skill, each holding a `SKILL.md`, in `.claude/skills/` for `claude-code` and in `.agents/skills/` for `codex` and `github-copilot`. It also writes `skills-lock.json` in the project folder.

From your project folder, run:

```bash
ls .claude/skills
```

For `codex` or `github-copilot`, run `ls .agents/skills` instead.

A `--global` install lives in your user account instead of the project. For the Claude Code plugin, run `claude plugin list` in a terminal: this suite should have only `first-four-hours@first-four-hours` enabled. Run `claude plugin details first-four-hours@first-four-hours` to list its 15 skills. For any install, the real check is starting a skill: see [Your first run](first-run.md).

## If installation fails

- `npx` is not found: install Node.js, then open a new terminal.
- The skill folders are missing, or are in the other folder: run the install again with the `--agent` name of the agent you use.
- A plugin install cannot fetch the marketplace: check that `git --version` works and that you can reach github.com, then run the install again.
- Cursor does not list the plugin's skills: check that `"$HOME/.cursor/plugins/local/first-four-hours/.cursor-plugin/plugin.json"` exists, reload the window, and on an Enterprise plan ask an administrator to allow local plugin imports.
- The agent does not recognize a skill you name: check that the folder from the previous section holds that skill's `SKILL.md`, then start a new agent session from the project folder.
- A skill starts but stops when it runs its Python script: check that `python --version` reports 3.11 or later.
- Anything else: open an issue at https://github.com/akshay-diwadkar/first-four-hours/issues with the command you ran and its output.

## Next

- [Your first run](first-run.md): start one skill on a real problem.
- [Choose a skill](choosing-a-skill.md): find the skill for the problem in front of you.

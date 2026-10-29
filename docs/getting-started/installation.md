# Install First Four Hours

A skill is a folder of instructions for a coding agent. Install the skills in a project or in your user account with the Skills command-line interface (CLI). On Claude Code or Cursor, you can install the whole suite as one plugin instead.

## What you need

- For the Skills CLI route, Node.js supplies `npx`.
- For the Claude Code or Cursor plugin route, Git fetches the plugin. The plugin routes do not need Node.js.
- Python 3.11 or later, available as `python`. Many skills run Python scripts from their own folders.
- Extra Python packages for Scribe and Ticket. See [Install extra packages](#install-extra-packages).
- A coding agent with skill support. The repository's own install check covers the agent names `claude-code`, `codex`, and `github-copilot`.
- A folder to work in. Workbench skills work on the project folder where you start them, usually a Git repository. The Learning skills, `tutor` and `examiner`, work in any folder.

## Install the whole suite

Run this command from the root folder of your project:

```bash
npx skills add akshay-diwadkar/first-four-hours --skill '*'
```

**Not verified here:** this repository's install check runs Skills CLI 1.5.21 (`skills@1.5.21`) with `--copy` against a local checkout. It does not run the unpinned command above or install from the `akshay-diwadkar/first-four-hours` source name.

If you are unsure about your needs, install the whole suite. Some skills bring in other skills during their work.

## Install one skill

```bash
npx skills add akshay-diwadkar/first-four-hours --skill blueprint
```

Replace `blueprint` with the name of the skill you want. The note in [Install the whole suite](#install-the-whole-suite) also applies to this command.

For planning, install `blueprint`, `construct`, `ideate`, and `reason` together. Blueprint consults Reason and uses Ideate during planning. Ideate consults Reason. Construct needs no other skill.

Many skills, including Diagnose and Tutor, consult `reason` at their judgment points. Each skill with Reason checkpoints also needs `reason`. [How skills hand work to each other](../concepts/handoffs.md) lists the skills with Reason checkpoints.

## Choose the agent and where skills go

Use `--agent` to name one agent: `claude-code`, `codex`, or `github-copilot`.

```bash
npx skills add akshay-diwadkar/first-four-hours --skill '*' --agent codex
```

Add `--global` to install for your user account instead of the current project.

**Not verified here:** this repository does not record where a `--global` install puts the skill folders, and its install check does not run `--global`.

## Install extra packages

Scribe and Ticket need extra Python packages. Each of the two skills lists its packages in its own `requirements.txt` file:

- `scribe`: `jsonschema`.
- `ticket`: `tree-sitter` and its language grammars.

Use the same `python` command as your agent. Run the commands below from your project folder for a `claude-code` project install:

```bash
python -m pip install -r .claude/skills/scribe/requirements.txt
python -m pip install -r .claude/skills/ticket/requirements.txt
```

For `codex` or `github-copilot`, replace `.claude/skills` with `.agents/skills` in each command. Skip the command for a skill you do not use.

For the Claude Code plugin, the skill folders are under the `installPath` value from `claude plugin list --json`. For example, Scribe is in `<installPath>/skills/sensemaking/scribe`. For the local Cursor plugin, Scribe is in `~/.cursor/plugins/local/first-four-hours/skills/sensemaking/scribe`.

## Install as a Claude Code plugin

On Claude Code 2.1.275 or later, you can install all 15 skills as one `first-four-hours` plugin instead of the Skills CLI.

Run this command in a Claude Code session:

```text
/plugin install first-four-hours --marketplace akshay-diwadkar/first-four-hours
```

If necessary, the command adds the `first-four-hours` marketplace. The command installs the plugin for your user account, so every project can use the plugin. The plugin route needs Git and Python 3.11 or later. For Claude Code, use the plugin or the Skills CLI, not both, to prevent duplicate skills.

Plugin skill names start with `first-four-hours:`. For example, start Diagnose with `/first-four-hours:diagnose`, Ideate with `/first-four-hours:ideate`, and Tutor with `/first-four-hours:tutor`. Each skill keeps its start mode.

The plugin has no pinned version and follows repository commits. Run `/plugin marketplace update first-four-hours` in a Claude Code session to update the plugin. Another option is `claude plugin update first-four-hours@first-four-hours` in a terminal. A new session uses the updated plugin.

**Not verified here:** this repository does not confirm the two update commands or that the plugin has no pinned version, and its plugin installation check does not run an update.

## Install as a Cursor plugin

In Cursor, you can install all 15 skills as one `first-four-hours` plugin instead of the Skills CLI. The Cursor route needs Git and Python 3.11 or later.

To install the plugin for yourself, clone the repository into the local plugin folder of Cursor:

```bash
git clone https://github.com/akshay-diwadkar/first-four-hours "$HOME/.cursor/plugins/local/first-four-hours"
```

Restart Cursor. As an alternative, run **Developer: Reload Window**. Open **Customize** and look for the skills. On an Enterprise plan, an administrator must first enable **Allow Local Plugin Imports**.

Run `git -C "$HOME/.cursor/plugins/local/first-four-hours" pull` to update the plugin. After the pull, reload the window.

On a Teams or Enterprise plan, an administrator can add the repository for the whole team:

1. In the Cursor dashboard, open **Plugins & MCPs**.
2. Choose **Add Marketplace** under **Team Marketplaces**.
3. Choose **Import from Repo**.
4. Paste `https://github.com/akshay-diwadkar/first-four-hours`.

Team members can then install `first-four-hours` from **Customize**.

Cursor also loads skills from `.agents/skills/` and `.claude/skills/` in a project or in your user folder. The Skills CLI installs skills into the same folders. Use the plugin or the Skills CLI, not both, to prevent duplicate skills.

Type `/` in the chat to choose a skill. Each skill keeps its start mode. Cursor has no setting to hide a skill from `/`. The `/` list therefore also shows `router`, which the agent starts on its own. Ask for the result of Router in plain words instead.

**Not verified here:** no check in this repository installs the Cursor plugin, and this repository does not confirm these Cursor details:

- the clone URL in the `git clone` command;
- the **Developer: Reload Window** command and the **Customize** view;
- the **Allow Local Plugin Imports** setting;
- the `git pull` update command;
- the dashboard menu names for the team marketplace;
- the extra skill folders of Cursor;
- that restarting Cursor loads the plugin;
- that Cursor has no setting to hide a skill from `/`, so `/` also shows `router`.

## Check the installation

A project install puts one folder per skill in `.claude/skills/` for `claude-code`. Each folder holds a `SKILL.md` file. For `codex` and `github-copilot`, the folders are in `.agents/skills/`. A project install also writes `skills-lock.json` in the project folder.

From your project folder, run this command:

```bash
ls .claude/skills
```

For `codex` or `github-copilot`, run `ls .agents/skills` instead.

For a `--global` install, see the note in [Choose the agent and where skills go](#choose-the-agent-and-where-skills-go).

For the Claude Code plugin, run `claude plugin list` in a terminal. The list must show `first-four-hours@first-four-hours` as enabled. To list the 15 skills of the plugin, run `claude plugin details first-four-hours@first-four-hours`.

Start a skill to verify any install. See [Your first run](first-run.md).

## If installation fails

- `npx` is not available: install Node.js. After the installation, open a new terminal.
- The skill folders are missing or in the other folder: install again with the `--agent` name of your agent.
- A plugin install cannot fetch the marketplace: run `git --version` to verify Git. Verify your access to github.com. Run the install again.
- Cursor does not list the skills of the plugin: verify the file `~/.cursor/plugins/local/first-four-hours/.cursor-plugin/plugin.json`. Reload the window. On an Enterprise plan, ask an administrator to allow local plugin imports.
- The agent does not recognize a skill name: verify the `SKILL.md` file of the skill in the folder from the previous section. Start a new agent session from the project folder.
- A skill fails during a Python script: run `python --version`. The output must show 3.11 or later. For Scribe or Ticket, also install the [extra packages](#install-extra-packages).
- Anything else: open an issue at https://github.com/akshay-diwadkar/first-four-hours/issues with the command and its output.

## Next

- [Your first run](first-run.md): start one skill on a real problem.
- [Choose a skill](choosing-a-skill.md): find the skill for your problem.

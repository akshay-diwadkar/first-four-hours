# Start here

First Four Hours is a set of skills, written instructions with small helper scripts, that guide an AI coding agent to do one job carefully; it is not a program you run yourself, because your agent reads and follows it.

You add the skills to your agent once, then ask it for something in plain words, and a skill shapes how the agent does that work. This page gets you to your first request. [The README](README.md) is the full overview for people who already use a coding agent, and it lists every skill.

## What you need

- A coding agent installed on your own computer, such as Claude Code, Codex, or GitHub Copilot. If you do not have one yet, set it up first by following its maker's instructions.
- Node.js, which provides the `npx` command used below.
- Python 3.11 or later, because many skills run small Python scripts.

The skills only work through an agent installed on your computer. This repository documents no way to use them without that.

## Install the skills

Open a terminal in the folder you want to work in, and run:

```bash
npx skills add akshay-diwadkar/first-four-hours --skill '*'
```

To check that it worked, run this in the same folder:

```bash
ls .claude/skills
```

You should see one folder per skill. For Codex or GitHub Copilot, run `ls .agents/skills` instead. [Install First Four Hours](docs/getting-started/installation.md) covers the Claude Code plugin, installing for every project, and what to do when installation fails.

## Make your first request

Start a new session with your agent in that folder, then type one of these requests. Each one is an illustrative example, not a recorded run: replace the details with your own.

**You want to learn something**, technical or not:

```text
/tutor : Teach me how compound interest works; I am comfortable with basic percentages.
```

**You are preparing for a written examination.** Name the examination as exactly as you can:

```text
/examiner : Write a full mock for AQA GCSE Chemistry Paper 1 for the current specification.
```

**Something in your project goes wrong and you do not know why.** This one reads your project and never edits it:

```text
/diagnose : Find out why the nightly export job sometimes writes an empty file.
```

These pages start a skill with `/name : request`. If your agent names skills another way, use its form. If you installed the Claude Code plugin, put `first-four-hours:` after the slash, as in `/first-four-hours:tutor`. Not sure which fits your situation? [Choose a skill](docs/getting-started/choosing-a-skill.md) starts from the problem in front of you.

## What a first run leaves behind

- An explanation or a tutoring session stays in the conversation and saves nothing unless you ask to keep something. A continuing series of lessons saves ordinary files under `.learning/` in the folder you started in.
- A practice paper is saved under `.learning/` too, with a separate answer key.
- A diagnosis leaves one report, `diagnosis.md`, under `.first-four-hours/diagnoses/`. In a Git repository, Git ignores that folder.

When a skill finishes, you decide what comes next. Each skill's page says what it produces and where to go from there: [Tutor](docs/skills/tutor.md), [Examiner](docs/skills/examiner.md), and [Diagnose](docs/skills/diagnose.md). [Your first run](docs/getting-started/first-run.md) walks through one run in full.

## If a skill does not start

- Run the check under "Install the skills" again and look for the skill's folder. If it is there, start a new agent session from that folder.
- If the folder is missing, or is in the other agent's folder, run the install again with `--agent` and the name of the agent you use, as [Install First Four Hours](docs/getting-started/installation.md) shows.
- With the Claude Code plugin, include the `first-four-hours:` prefix in the name.
- If the agent answered without using the skill, begin your request with the skill's name, as the examples do.
- If a skill starts and then stops when it runs a Python script, check that `python --version` reports 3.11 or later.
- [Troubleshooting](docs/troubleshooting/README.md) lists other symptoms, a check that changes nothing, and the next step.

## Where the full manual lives

[The documentation](docs/README.md) is the full manual: how the suite works, a page for each skill, recipes for recurring problems, and troubleshooting by symptom. First Four Hours makes no promise of time saved; [Why First Four Hours exists](docs/concepts/why-first-four-hours.md) explains what it aims for.

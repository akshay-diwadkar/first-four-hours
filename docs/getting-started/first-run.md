# Your first run

Try one skill on a real problem in your own project. This page uses Diagnose because it reads your project without editing it, starts only when you name it, and leaves a file you can open. Install the skills first: see [Install First Four Hours](installation.md).

## Start Diagnose

You start a skill by name with `/name : request`, the form these pages use. If your agent names skills another way, use its form. With the Claude Code plugin, a skill's name starts with `first-four-hours:`, so Diagnose is `/first-four-hours:diagnose`.

For example (illustrative):

```text
/diagnose : Find out why the nightly export job sometimes writes an empty file.
```

Replace the request with a real problem from your project. Diagnose traces the symptom through the project and runs only probes that change nothing. It asks before using shared or billable resources or production data, and it never edits the project.

## What you get

A sealed `diagnosis.md` in `.first-four-hours/diagnoses/<slug>/`. In a Git repository, Git ignores that folder through a rule the skill writes, so the file does not appear as a change to commit. It holds the symptoms, each finding with how well its cause is established, the limitations, and advisory directions. Advisory directions are leads, not a chosen fix.

To see it, run this from the project folder:

```bash
ls .first-four-hours/diagnoses
```

The run is done when the file is sealed. When the evidence cannot support a finding, Diagnose says what evidence is missing instead of guessing.

## What to do next

Nothing starts on its own; you decide:

- Plan a fix for one finding with Blueprint, then carry out the sealed plan with [Construct](../skills/construct.md). For example (illustrative):

  ```text
  /blueprint : Plan a fix for finding <finding-id> in .first-four-hours/diagnoses/<slug>/diagnosis.md.
  ```

- Explore options first with [Ideate](../skills/ideate.md).
- Stop here.

If you want to learn a subject rather than change code, start with [Tutor](../skills/tutor.md) instead. For example (illustrative):

```text
/tutor : Teach me how Git rebase differs from merge; I already use branches daily.
```

## How skills start

Each skill has a mode that controls whether the agent may start it, recorded in [the invocation policy](../../invocation-policy.json).

| Mode | Skills | How it starts |
| :--- | :--- | :--- |
| `both` | Every other skill | The agent may start it when your request matches its purpose, and you can start it by name. |
| `user-invoked` | `charter`, `diagnose`, `pr`, `ticket` | Only you start it, by name. The agent never starts it on its own. |
| `model-invoked` | `atlas`, `router` | The agent starts it when a task matches. Ask for the outcome in plain words instead of naming it. |

Name a skill when you want to be sure it runs. On Claude Code and GitHub Copilot, the `model-invoked` skills are kept out of the skills you start by name; Codex has no such setting. Each skill's page in [the skill index](../skills/README.md) says how to start it.

## If the skill did not start

- The agent does not recognize the name: recheck [Install First Four Hours](installation.md).
- It is a `model-invoked` skill: ask for the outcome in plain words.
- The agent handled the request without the skill you expected: start the skill by name.

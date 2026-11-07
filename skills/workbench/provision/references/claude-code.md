# Claude Code

Checked 2026-11-05 against Claude Code 2.1.318, https://code.claude.com/docs/en/sub-agents, and https://code.claude.com/docs/en/model-config.

- **Directory:** `.claude/agents/` for a project install; `~/.claude/agents/` for a user install, which includes the plugin.
- **File:** `<name>.md`: YAML frontmatter with `name`, `description`, `tools`, `model`, and `effort` when chosen, then the instructions as the body. Hyphens are allowed in `name`.
- **Capabilities:** `tools` is an enforced allowlist. Read and search: `Read, Grep, Glob`. Shell: add `Bash`. Web: add `WebSearch, WebFetch`. `ffh-constructor`: add `Edit, Write, Bash, Skill`. Leaving out every edit and agent tool blocks file-tool edits, and leaving out `Agent` blocks spawning. A granted `Bash` can still change files, so a read-only agent's no-edit limit needs the user's choice.
- **Models:** `model` takes an alias or a full model ID from the model configuration page, which also lists the effort levels each model supports; the user's `/model` picker shows what their account offers. `effort` takes one of those levels; on a model other than the session's, set it explicitly or leave it out.
- **Loaded:** the agent appears in `/agents`, which shows its model and tools, and among the subagent types the session can launch. Files are picked up within seconds, except that an `agents` directory created during the session needs a restart.

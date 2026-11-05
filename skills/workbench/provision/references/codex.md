# Codex

Checked 2026-11-05 against codex-cli 0.166.0 and https://learn.chatgpt.com/docs/agent-configuration/subagents.md.

- **Directory:** `.codex/agents/` for a project install; `~/.codex/agents/` for a user install.
- **File:** `<name>.toml` with `name`, `description`, and `developer_instructions` (the instructions), plus `model` and `model_reasoning_effort` when chosen. The `name` field, not the filename, identifies the agent.
- **Name:** use `ffh_<role>`; the documentation's examples use underscores and do not establish that hyphens work.
- **Capabilities:** keep the shell for every agent, because Codex agents read and search files through it; turning it off with `features.shell_tool = false` can leave an agent unable to read. An agent file cannot block file edits or spawning, because sandbox and approval settings come from the parent session. So every agent's no-edit and no-spawn limits are instruction-only here and need the user's choice. Per-agent web search is not documented: `ffh-researcher` uses whatever web access the session has, and the report says so.
- **Models:** `codex debug models` prints the model catalog as JSON. Offer only entries without `"visibility": "hide"`, with the effort levels in each entry's `supported_reasoning_levels`. It is a debugging command: when it fails or its shape differs, ask the user.
- **Loaded:** reload behavior is not documented. Ask the user to start a new session and confirm that Codex can name and spawn the agent on the chosen model; until they confirm, it stays written but unverified.

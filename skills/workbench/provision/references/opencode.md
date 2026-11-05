# OpenCode

Checked 2026-11-05 against the documentation only, with no installed version: https://opencode.ai/docs/agents/, https://opencode.ai/docs/permissions/, and https://opencode.ai/docs/cli/. Re-check each fact you use against these pages on every run.

- **Directory:** `.opencode/agents/` for a project install; `~/.config/opencode/agents/` for a user install.
- **File:** `<name>.md`, where the filename is the agent's name: YAML frontmatter with `description`, `mode: subagent`, `model`, and `permission`, then the instructions as the body.
- **Name:** use `ffh_<role>`; the documentation's examples do not establish that hyphens work.
- **Capabilities:** `permission` is enforced, but most permissions default to `allow`, so put `"*": deny` first and allow only what the agent needs after it. Every agent: allow `read`, `glob`, `grep`, and `list`. Allow `bash` for `ffh-challenger` and `ffh-reviewer`, and `webfetch` and `websearch` for `ffh-researcher`. Whether `"*"` covers MCP tools is not documented: say so in the report. An allowed `bash` can still change files, so that limit needs the user's choice.
- **Models:** `opencode models` lists `provider/model` IDs for the user's authenticated providers; add `--refresh` to fetch newly added models. `model` takes one of those IDs.
- **Effort:** there is no general field. Extra frontmatter keys pass to the provider, and the documentation shows an effort key (`reasoningEffort`) for one provider only. Set effort only through a key documented for the chosen provider; otherwise leave it out and say so.
- **Loaded:** ask the user to confirm in a new session that the agent appears in the `@` menu and runs on the chosen model; until they confirm, it stays written but unverified.

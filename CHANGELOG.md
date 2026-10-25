# Changelog

All notable changes to agent-status are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-25

First release.

### Added

- A live dashboard for the tablet or phone on your desk: agent cards and needs-you alerts, served from one Python process
  with no runtime dependencies.
- A dated price table (`agent_status/prices.json`) for Claude and OpenAI/Codex models, with a per-model override in
  `~/.config/agent-status/prices.json`; the Models panel shows the table's date.
- Hook support for Claude Code, Codex CLI, Cursor CLI, Gemini CLI and GitHub Copilot CLI, with normalized lifecycle events
  and a session state file per agent.
- Allow/Deny from the dashboard for Claude Code and Codex permission prompts, with a live per-prompt token, a 60-second
  wait that only runs while a dashboard is open, and no decision on any error.
- Readers for Claude Code transcripts, Codex session logs and the opencode database: models, tokens, context use,
  estimated or real cost, tok/s and plan limits. Omarchy's usage files fill plan limits and the 7-day panel where present.
- An interactive installer that adds hooks idempotently, keeps a one-time `.bak-agent-status` backup, and installs a
  systemd user service or macOS LaunchAgent. `uninstall` reverses it.
- `agent-status doctor` reports hooks that are missing or older than the registry and prints the reinstall command.
- `agent-status serve --demo` serves fictional sessions for screenshots and UI checks, without reading local data.
- The `/status` payload carries `schema: 2` and is documented in [`docs/api.md`](docs/api.md) with a contract test.
- Hook test harness that runs every installed event as a subprocess, checks the folded state and a 300 ms budget, and
  feeds hostile stdin. Stale state files are cleaned on start and hourly.
- `agent-status rotate-key` replaces the access key without a restart, and `/status` / `/decide` are rate-limited per
  client address.

### Changed

- `/status` schema 2 focuses on agents: the top-level `system` object and card `cpu`/`rss` fields are gone.

### Removed

- Machine stats (CPU, GPU, memory, network, disks, temperatures, device batteries) and per-agent CPU/RAM. The dashboard
  now tracks agents and their sessions, not the host.

### Security

- `/status` and `/decide` require the per-install key; `/decide` also requires a JSON body, a same-origin `Origin` and a
  live per-prompt token. The dashboard shows folder names, branches, models, counts and short tool hints, never prompts,
  file contents or tool output.

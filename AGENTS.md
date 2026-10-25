# agent-status: guide for coding agents

A stdlib-only Python service that watches AI coding agents (hooks, transcripts, databases, the process table) and
serves a live dashboard to a tablet or phone on the LAN. **Picking up work or planning a change → read
[`docs/PLAN.md`](docs/PLAN.md) first**: it holds the task list, current state and known issues.

## Layout

| Path | Role |
|---|---|
| `agent_status/agents.py` | registry of supported agents: detection, hook file formats (`nested`, `flat`, `own_file`) |
| `agent_status/hooks.py` | `agent-status hook <agent>`: normalize any agent's payload to Claude Code's shape, fold it in `next_state()`, and for Allow/Deny wait on `decisions/` |
| `agent_status/collect.py` | `Collector.tick()`: builds the snapshot every `INTERVAL` seconds in a thread; HTTP serves the cached JSON |
| `agent_status/claude.py`, `codex.py`, `opencode.py`, `omarchy.py` | readers for each agent's own data |
| `agent_status/prices.json` | dated $/MTok table; `~/.config/agent-status/prices.json` overrides it |
| `agent_status/procs.py`, `system.py`, `gitinfo.py` | process table, machine stats (Linux `/proc`+`/sys`, macOS commands), git status |
| `agent_status/server.py` | static files, `GET /status`, `POST /decide` |
| `agent_status/install.py` | interactive install/uninstall, `doctor`, systemd or launchd service |
| `agent_status/web/` | the dashboard: plain HTML/CSS/JS, no build step |
| `tests/` | `unittest`, fixtures under `tests/fixtures/` |

## Commands

```bash
python -m unittest discover -s tests        # all tests; must stay green on Linux and macOS
python -m agent_status doctor               # check installed hooks against agents.py
python -m agent_status serve                # run from the checkout (port 8787, AGENT_STATUS_PORT to change)
python -m agent_status rotate-key           # replace the access key, print the new links
uv tool install --editable .                # install the CLI from this checkout
python scripts/make_icons.py                # regenerate web/icon-*.png
```

## Invariants

These are the decisions the code depends on. Changing one is a design change: say so in the PR.

- **Zero runtime dependencies**, Python ≥ 3.10. Shell out to tools the OS ships (`ps`, `nvidia-smi`, `git`) rather than adding packages.
- **A hook never harms the agent.** `hook()` swallows every error, prints nothing unless it is answering a permission prompt (Gemini always gets `{}`), and stays fast: it imports only `config`, `procs` and the stdlib. Measure with `time (echo '{}' | agent-status hook claude)`.
- **One shape for events.** New agents map onto Claude Code's event names and fields in `hooks.normalize()`; `next_state()` stays agent-agnostic and pure, which is where state logic gets tested.
- **Readers are incremental.** Track byte offsets (JSONL) or `time_updated` (SQLite) and parse only what changed; a full `tick()` should stay around 50 ms. Open other tools' databases with `mode=ro`.
- **Agent configs are edited only through `agents.py`**: idempotent install, one-time `.bak-agent-status` backup, uninstall that rewrites a file only when it removed something.
- **Privacy boundary.** The dashboard shows folder names, branches, models, counts and short tool hints. Prompts, file contents and tool output stay on the machine. Every data or action endpoint checks the `?k=` key; `/decide` also requires a JSON body, a same-origin `Origin` and a live per-prompt token.
- **Frontend stays build-free and keyed.** Cards are keyed by `id` and only their body is re-rendered through `setHTML()`; re-rendering whole cards restarts their CSS animations.

## Conventions

- Comments explain *why* in one line. A deliberate shortcut gets `# shortcut: <the limit>, <when to upgrade>`.
- New non-trivial logic ships with a test; agent payloads and command output get a fixture.
- Commit messages: imperative subject, wrapped body explaining why.

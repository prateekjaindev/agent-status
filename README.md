# agent-status

**A live dashboard of your AI coding agents, made for the tablet or phone on your desk.**

Glance over and see which agents are working, which one is waiting for your approval, what it's doing right now, how fast tokens are flowing, what today has cost, and how hard your machine is working. An old iPad or Android tablet becomes a status screen for Claude Code, Codex, Cursor, Gemini CLI, Copilot CLI, opencode and more.

- **Needs-you alerts**: an amber banner (and an optional chime) the moment an agent stops for a permission prompt
- **Approve from the tablet**: Allow or Deny a Claude Code or Codex permission prompt with a tap, with the full command shown
- **Per-session cards**: state, current tool, model, tokens/sec, context window use, session cost, prompts and tool calls, git branch with `+added −removed` lines, and the agent's own CPU and memory
- **Today's usage**: tokens and cost per model, cost per hour, an hour-by-hour chart, plan limits (5-hour and weekly windows), and the last 7 days
- **Machine performance**: CPU (per core and temperature), GPU (NVIDIA and AMD: load, VRAM, power, temperature), memory, network, disks, and device batteries (mouse, keyboard, headset). On macOS: CPU per core, memory, network, disks and the laptop battery
- **No dependencies**: Python standard library only, one background service, and a web page that any browser on your network can open

## Supported agents

| Agent | How it's tracked | What you get |
|---|---|---|
| Claude Code | hooks + session logs | live status, needs-you, allow/deny, tok/s, context %, cost (API-price equivalent) |
| Codex CLI | hooks + session logs | live status, needs-you, allow/deny, context %, tokens, plan limits |
| Cursor CLI | hooks | live status |
| Gemini CLI | hooks | live status, needs-you |
| GitHub Copilot CLI | hooks | live status, needs-you |
| opencode | its local database | live status, tok/s, tokens, real cost, lines changed |
| Aider, Amp, Goose, Crush, Qwen Code, Kiro, Factory Droid, Cline, Kimi, Auggie, Grok CLI, Pi, Qoder | process scan | running / busy (from CPU use), CPU and memory |

On [Omarchy](https://omarchy.org), plan limits and 7-day history also come from Omarchy's agent usage panel.

## Install

```bash
uv tool install git+https://github.com/prateekjaindev/agent-status   # or: pipx install git+https://...
agent-status install
```

`install` lists every supported agent, preselects the ones it finds on your machine, and lets you toggle them:

```
Which agents should agent-status track?  (detected ones are preselected)

  [x]  1  Claude Code          live hooks      found claude
  [x]  2  Codex CLI            live hooks      found codex
  [ ]  3  Cursor CLI           live hooks      not found
  ...
Toggle by number (e.g. 3 7), [a]ll found, [n]one, Enter to continue, [q]uit:
```

It then adds hooks to the agents you picked (keeping a `.bak-agent-status` backup of each config file it touches), starts a background service (a systemd user service on Linux, a LaunchAgent in `~/Library/LaunchAgents` on macOS), and prints the link to open. For scripts, use `agent-status install --agents claude,codex,opencode` or `--yes` for "everything detected".

Restart agents that were already running so they load the new hooks. Remove everything with `agent-status uninstall`.

## Open it on a tablet or phone

The tablet must be on the same network. Open the link from `agent-status url`:

```
http://yourcomputer.local:8787/?k=XXXXXXXX   (stable name, mDNS)
http://192.168.1.20:8787/?k=XXXXXXXX         (current IP)
```

- **iPad / iPhone:** Safari → Share → **Add to Home Screen**. It opens full screen like an app. Set Settings → Display & Brightness → Auto-Lock to *Never* to keep it awake.
- **Android:** Chrome → ⋮ → **Add to Home screen**. Use the full-screen button in the header, and raise the screen timeout or turn on *Stay awake* in developer options while charging.
- **Sound:** tap the speaker icon once; browsers only allow audio after a tap. It chimes when an agent needs you, and softly when one finishes.

## Approve or deny from the tablet

When Claude Code or Codex asks permission to run a tool, its card shows the exact command (or file) with **Allow** and **Deny** buttons. A tap answers the prompt in the terminal for you; Deny tells the agent the user refused.

- The terminal prompt stays usable the whole time: answer whichever is closer. If nobody taps within 60 seconds, the hook steps aside and the terminal prompt is the only way to answer.
- The hook only waits while a dashboard is open (one has polled in the last 10 seconds). With no tablet watching, prompts behave exactly as before.
- Any error, timeout or stale tap means "no decision", never an automatic allow. Your deny rules still apply on top of an Allow.
- GitHub Copilot CLI shows the prompt as *needs you* but has no buttons: its `permissionRequest` hook runs before its own rules and session approvals, so waiting there would stall tool calls you had already allowed.
- Upgrading from an earlier version? Run `agent-status doctor`; if it reports stale hooks, run `agent-status install` again, then restart running agents. Codex may ask you to trust the changed hook.

If the page doesn't load, the computer's firewall is the usual cause (`sudo ufw allow 8787/tcp`). If the `.local` name doesn't resolve, use the IP link or reserve the computer's address in your router.

**Optional HTTPS:** with [Tailscale](https://tailscale.com), `tailscale serve --bg 8787` gives you an `https://` address that works anywhere on your tailnet. The browser's *keep screen on* button (Wake Lock) only appears over HTTPS.

## Security

The page itself is public on your network, but the data endpoint needs the key in the link (`?k=…`), which is generated on first run and stored in `~/.local/state/agent-status/token` (mode 600). The dashboard shows folder names, git branches and short tool descriptions (e.g. `Bash: run tests`), never prompts or file contents. A prompt waiting for approval also shows the command or file path being approved.

**Anyone with the link can approve commands** while a prompt is waiting, so treat the link like a password. Approvals go to `POST /decide`, which needs the same key, accepts only a JSON body (a cross-site form can't send one without a CORS preflight, which the server never grants), rejects a foreign `Origin`, and must quote a one-time token that is new for every prompt and expires with it. Over plain LAN HTTP someone sniffing your Wi-Fi can read the key; use Tailscale (below) for HTTPS, or set `AGENT_STATUS_HOST=127.0.0.1` to limit it to one machine.

## Configuration

| Variable | Default | |
|---|---|---|
| `AGENT_STATUS_PORT` | `8787` | port to listen on |
| `AGENT_STATUS_HOST` | `0.0.0.0` | address to bind |
| `AGENT_STATUS_INTERVAL` | `2` | seconds between refreshes |
| `CLAUDE_CONFIG_DIR` | `~/.claude` | where Claude Code keeps settings and transcripts |
| `AGENT_STATUS_OPENCODE_DB` | `~/.local/share/opencode/opencode.db` | opencode database |

Your agent choice is saved in `~/.config/agent-status/config.json`; run `agent-status install` again to change it.

## How it works

```
agents ──hooks──▶ agent-status hook <agent>  ──▶ ~/.local/state/agent-status/sessions/*.json
            ▲                                               │
            └── allow/deny ◀── decisions/<token> ◀── POST /decide (tablet tap)
                                                            │
transcripts, opencode db, /proc, /sys, nvidia-smi ──▶ agent-status serve (refreshes every 2s)
                                                            │
                                     tablet ◀── http://host:8787 (static page + /status JSON)
```

- **Hooks** run on every event, so they're tiny: parse the event, update one JSON file, exit. They never fail the agent; the only one that waits is a permission request while a dashboard is open (at most 60 seconds, polling `decisions/` for a tap).
- **Readers** parse transcripts and databases incrementally: only what was appended since the last refresh.
- **Costs**: Claude costs are what the same tokens would cost on the API (subscriptions bill differently, so they're marked `≈`); opencode costs are what opencode itself recorded. tok/s includes time to first token.

## Development

```bash
git clone https://github.com/prateekjaindev/agent-status && cd agent-status
uv tool install --editable .        # or: python -m agent_status serve
python -m unittest discover -s tests
```

**Adding an agent** is usually one entry in `agent_status/agents.py`: give it a key, the commands and config folders that show it's installed, and either a hook file format (`nested`, `flat` or `own_file`) or just process names. If its hook payload differs from Claude Code's, add an event map in `agent_status/hooks.py`.

The frontend is plain HTML, CSS and JavaScript in `agent_status/web/`, with no build step.

## Roadmap

Planned work (macOS extras, Windows, usage history and budgets, push notifications, more agents' token data, remote machines, themes, packaging) is tracked task by task in [`docs/PLAN.md`](docs/PLAN.md), each with what "done" means. Pick one and open a PR; [`AGENTS.md`](AGENTS.md) has the conventions.

## License

MIT

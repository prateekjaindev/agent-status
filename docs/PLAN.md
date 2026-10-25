# Development plan

How to use this file:

1. Pick the first task in the table whose status is `todo` and whose dependencies are `done`. Tasks marked
   **needs a human** require real hardware or accounts; skip them unless you have that.
2. Read only that task's section. Work on a branch named after the task ID (`t03-hook-harness`), one task per PR.
3. A task is finished when every line of its **Done when** list is true and `python -m unittest discover -s tests`
   passes. Then set its status to `done` in the table, and add anything you learned to *Known issues* or a new task.

Repo conventions and invariants live in [`AGENTS.md`](../AGENTS.md); they apply to every task.

## Status

| ID | Task | Phase | Size | Status | Depends on |
|---|---|---|---|---|---|
| T01 | Fix the macOS smoke test and the `.local.local` link | 0 Stabilize | S | done | |
| T02 | Pin CI actions and add Dependabot | 0 Stabilize | S | done | |
| T03 | Hook test harness: subprocess runs, timing, garbage input | 0 Stabilize | M | done | |
| T04 | Clean up stale state files | 0 Stabilize | S | done | |
| T05 | Real-device and live-agent verification | 0 Stabilize | M | todo, **needs a human** | T01 |
| T06 | `/status` JSON contract: schema doc and version field | 1 Release | S | done | |
| T07 | Demo mode for screenshots | 1 Release | S | done | T06 |
| T08 | Single-source version, CHANGELOG, PyPI release workflow | 1 Release | M | done | T02 |
| T09 | AUR package and Homebrew tap | 1 Release | M | todo, **needs a human** | T08 |
| T10 | Price tables as dated data, plus OpenAI prices | 2 Data | M | done | |
| T11 | Usage history in SQLite (replaces Omarchy for history) | 2 Data | L | todo | T06 |
| T12 | Budgets and limit alerts | 2 Data | M | todo | T11 |
| T13 | Codex tokens/sec | 2 Data | S | todo | |
| T14 | Gemini CLI token usage | 2 Data | M | todo | |
| T15 | Copilot CLI token usage | 2 Data | M | todo | |
| T16 | opencode "needs you" state | 2 Data | M | todo | |
| T17 | Push notifications when nobody is looking | 3 Interaction | M | todo | |
| T18 | Session detail view (timeline of recent events) | 3 Interaction | L | todo | T06 |
| T19 | Key rotation and `/decide` rate limit | 3 Interaction | S | todo | |
| T20 | Agents on other machines report to one dashboard | 4 Platforms | L | todo | T06, T19 |
| T21 | macOS temperatures, GPU and Bluetooth batteries | 4 Platforms | M | todo, **needs a human** | T01 |
| T22 | Windows host support | 4 Platforms | L | todo | T03 |
| T23 | Light theme, wall mode, per-device layout | 4 Platforms | M | todo | |
| T24 | Other clients: terminal UI and ESP32 example | 4 Platforms | M | todo | T06 |

Sizes: S = under half a day, M = about a day, L = several days.

## Current state (2026-10-25)

Working and verified on Linux (Omarchy, Python 3.14) with an iPad on the LAN:

- **Hooks:** Claude Code and Cursor, live. Allow/Deny from the dashboard was tested against a live Claude Code session in a desktop browser.
- **Readers:** Claude transcripts (tokens, cost, tok/s, context), opencode database (state, real cost, tok/s), Codex session logs (tokens, context, rate limits), and Omarchy's usage files (plan limits, 7-day history).
- **Machine stats on Linux:** CPU, GPU (NVIDIA and AMD), memory, network, disks, batteries.
- **API:** `/status` carries `schema: 1`, its full shape is documented in [`docs/api.md`](api.md), and a contract test builds a snapshot from fixtures.
- **Demo mode:** `agent-status serve --demo` serves five fictional sessions with moving sparklines; the README screenshots come from it and the contract test checks it.
- **Prices:** `agent_status/prices.json` is a dated table (Claude and OpenAI), shown in the Models panel; `~/.config/agent-status/prices.json` overrides individual models.
- **Packaging:** the version lives only in `agent_status/__init__.py`, a wheel builds from it, and a tagged release workflow publishes to PyPI once the owner configures trusted publishing.
- **Installer and tests:** the interactive installer works, 67 unit tests pass on Linux, `agent-status doctor` reports hooks that are missing or older than the registry, and stale state files are cleaned on start and hourly.

Built from documentation but **not yet run against the real thing**:

- Codex, Gemini CLI and Copilot CLI hooks (event names and payloads come from their docs; see the links in T05).
- Allow/Deny on Codex, and Allow/Deny tapped on an actual iPad.
- macOS host support. Its fixtures are hand-written, but the unit tests and the server smoke test pass in CI; it still has not run on real hardware (T05).
- Android: the page has a manifest and a phone layout, checked only in emulated viewports.

## Known issues

- **Process-name collisions:** process-only agents with generic command names (`pi`, `amp`, `grok`) can match unrelated programs.
- **No history without Omarchy:** the 7-day chart and plan limits other than Codex come only from Omarchy's files, so the panel is empty on other distros until T11.
- **Approximate tokens/sec:** tok/s includes time to first token. Claude's start time is the preceding `user` line, so a slow tool result that lands right before a response can skew it.
- **Copilot approvals are deliberately off:** Copilot's `permissionRequest` fires before its own allow rules, so waiting there would stall calls that never needed the user (see `DECIDES` in `hooks.py`).
- **PyPI trusted publisher is not configured yet:** `release.yml` builds and checks the tag, but the first `v*` tag fails at publish until the owner adds the pending trusted publisher (`docs/release.md`).

---

## Phase 0: Stabilize

### T01 · Fix the macOS smoke test and the `.local.local` link

**Why.** CI's `test (macos-latest, 3.13)` job passes the unit tests but fails "smoke test the server": the server prints its links, then `curl` to `127.0.0.1:18787` times out (exit 28). Until this is green, macOS support is unproven.

**Where.** `.github/workflows/test.yml`, `agent_status/server.py`, `agent_status/collect.py`, `agent_status/system.py` and `agent_status/procs.py` (the macOS paths).

**Approach.**
1. Reproduce in CI with diagnostics: give curl `--max-time 10`, run the server with output to a log file, and after curl fails, print the log and `lsof -iTCP:18787` (is it listening?). To see where it is stuck, start the server with `faulthandler.register(signal.SIGUSR1)` and send `SIGUSR1` before killing it. Decide whether the socket is never bound, or bound but the handler blocks.
2. Likely suspects: `Collector.start()` or the per-request path blocking on a macOS command (`lsof`, `pmset`, `netstat`) with no timeout; `ThreadingHTTPServer` binding `0.0.0.0` behind the macOS application firewall prompt on the runner; or the readers walking a huge home directory. Every `subprocess.run` in the macOS paths must have a timeout.
3. In `server.urls()`, strip a trailing `.local` from the hostname before appending it.

**Done when.**
- The `macos-latest` job is green on `main`.
- Every subprocess call in `system.py` and `procs.py` passes `timeout=`.
- A unit test covers `urls()` for both `myhost` and `myhost.local`.

### T02 · Pin CI actions and add Dependabot

**Why.** The repo is public; actions referenced by tag (`actions/checkout@v4`) can change under us.

**Where.** `.github/workflows/test.yml`, new `.github/dependabot.yml`.

**Approach.** Replace each `uses:` tag with its full commit SHA plus a `# vX.Y.Z` comment. Add Dependabot for `github-actions`, weekly. Add `permissions: contents: read` at the workflow top.

**Done when.**
- No `uses:` line references a tag or branch.
- `dependabot.yml` exists.
- CI is green.

### T03 · Hook test harness: subprocess runs, timing, garbage input

**Why.** Hooks run inside other people's agents on every tool call. Today they are tested as functions, not as the command the agents actually execute.

**Where.** New `tests/test_hook_process.py`, fixtures under `tests/fixtures/hooks/<agent>/*.json`, and possibly `agent_status/hooks.py`.

**Approach.**
1. Add one real-shaped payload fixture per agent and event: Claude, Codex, Cursor, Gemini, Copilot, using the field names from each vendor's docs.
2. Run `python -m agent_status hook <agent> [event]` as a subprocess with `AGENT_STATUS_STATE` pointing at a temp directory. Feed each fixture and assert exit code 0, the expected stdout (empty, `{}` for Gemini, or a decision), the expected session JSON, and wall time under 300 ms.
3. Feed garbage too: empty stdin, invalid JSON, a 5 MB payload, binary, and a `session_id` with `../`. Each must exit 0 with no traceback and must not write outside the state directory.
4. Add `agent-status doctor`: list each enabled agent and whether its config contains the current hook set (compare against `agents.py`), and print the exact `agent-status install` command when it doesn't. This fixes the "needs a reinstall" known issue.

**Done when.**
- Every agent in `EVENT_MAPS`, plus Claude and Codex, has fixtures for every event it installs.
- The garbage cases pass.
- `agent-status doctor` reports stale hooks, and a test covers that.

### T04 · Clean up stale state files

**Why.** `sessions/`, `decisions/` and `*.tmp` files accumulate when agents crash or hooks are killed mid-write.

**Where.** `agent_status/collect.py`, `agent_status/hooks.py`.

**Approach.** On server start and once an hour in `Collector.run()`, delete `*.tmp` files older than 1 minute, `decisions/*` older than `DECIDE_WAIT` × 2, and session files without a pid older than `STALE`. Unit-test with backdated mtimes (`os.utime`).

**Done when.**
- A test creates stale files of each kind and shows they are removed while fresh ones stay.

### T05 · Real-device and live-agent verification (**needs a human**)

**Why.** Several integrations exist only on paper (see *Current state*).

**Where.** New `docs/compat.md`, plus fixes wherever reality differs.

**Approach.** For each row below, do the action and record the agent or device version and the result in `docs/compat.md`. Capture any real payload that differs from the fixtures into `tests/fixtures/hooks/`.

| Check | Expected |
|---|---|
| Codex CLI: prompt, tool call, approval prompt, stop | card goes working → needs you → working → done |
| Codex CLI: tap Allow on the dashboard | Codex proceeds without the terminal prompt |
| Gemini CLI: prompt, tool, ToolPermission notification | card states as above; Gemini output unaffected by `{}` |
| Copilot CLI: prompt, tool, permission request, agentStop | card states as above |
| Cursor CLI: session with tools | working/done transitions |
| iPad Safari, home-screen app: tap Allow and Deny | the agent receives the decision |
| Android Chrome: add to home screen, full screen button, phone layout | standalone launch, no horizontal scroll |
| macOS host (Apple Silicon): `agent-status install`, dashboard | system panel filled, launchd service survives logout/login |

Vendor docs used so far: [Claude Code hooks](https://code.claude.com/docs/en/hooks), [Codex hooks](https://learn.chatgpt.com/docs/hooks), [Gemini CLI hooks](https://geminicli.com/docs/hooks/reference/), [Copilot hooks](https://docs.github.com/en/copilot/reference/hooks-reference), [Cursor hooks](https://cursor.com/docs/agent/hooks).

**Done when.**
- Every row has a recorded result.
- Every failure has a fix or a new task in this file.

---

## Phase 1: Release

### T06 · `/status` JSON contract: schema doc and version field

**Why.** The frontend, demo mode, history, remote agents and other clients all depend on this payload, and it is currently defined only by `Collector.tick()`.

**Where.** `agent_status/collect.py`, new `docs/api.md`, new `tests/test_contract.py`.

**Approach.** Add `"schema": 1` to the snapshot. Document every field in `docs/api.md`: types, units (bytes, seconds, cost in USD), nullability, and which agents fill which fields. The test builds a snapshot from fixtures and checks that it has exactly the documented keys and types (a small hand-written checker; no `jsonschema` dependency).

**Done when.**
- `docs/api.md` covers every key `tick()` emits.
- The contract test fails if a key is added or removed without updating it.

### T07 · Demo mode for screenshots

**Why.** The README needs a screenshot and a GIF, and real data leaks project names.

**Where.** `agent_status/server.py`, new `agent_status/demo.py`, `README.md`, `docs/screenshot.png`.

**Approach.** `agent-status serve --demo` serves a generated snapshot that follows the T06 contract: four or five fictional sessions across agents, one waiting, plausible usage, moving sparklines, and states rotating every few seconds. Take screenshots at 1366×1024 and 412×915 and add them to the README.

**Done when.**
- `--demo` runs with no agents installed.
- The README shows both screenshots.
- `tests/test_contract.py` also validates the demo snapshot.

### T08 · Single-source version, CHANGELOG, PyPI release workflow

**Where.** `pyproject.toml`, `agent_status/__init__.py`, new `CHANGELOG.md`, new `.github/workflows/release.yml`.

**Approach.** Make `pyproject.toml` read the version dynamically from `agent_status.__version__` (setuptools `dynamic = ["version"]`). Add a workflow that, on a `v*` tag, builds an sdist and wheel and publishes with PyPI trusted publishing (OIDC, no API token in secrets). The PyPI project and trusted publisher must be configured by the repo owner. Start `CHANGELOG.md` at 0.1.0.

**Done when.**
- The version appears once in the repo.
- The workflow is valid (`act` or a dry-run tag on a fork).
- The README install line can switch to `uv tool install agent-status` once the owner has published.

### T09 · AUR package and Homebrew tap (**needs a human**)

**Approach.** An `agent-status` PKGBUILD that builds from the PyPI sdist, and a Homebrew formula in a `homebrew-tap` repo using `virtualenv_install_with_resources`. Both need the owner's AUR and GitHub accounts.

**Done when.**
- `yay -S agent-status` and `brew install prateekjaindev/tap/agent-status` install a working CLI.

---

## Phase 2: Data

### T10 · Price tables as dated data, plus OpenAI prices

**Why.** `PRICES` in `usage.py` is hand-maintained Python with no date, and Codex costs show `—`.

**Where.** `agent_status/usage.py`, new `agent_status/prices.json`, `agent_status/codex.py`, `tests/test_usage.py`.

**Approach.** Move prices to `prices.json`: `{"as_of": "YYYY-MM-DD", "source": url, "models": {prefix: {in, out, cache_read, cache_write_5m?, cache_write_1h?}}}`, keeping longest-prefix matching. Add OpenAI models used by Codex from OpenAI's official pricing page (OpenAI counts cached tokens inside `input_tokens`; Codex rows already split them). Show the `as_of` date in the Models panel note. Let users override with `~/.config/agent-status/prices.json`.

**Done when.**
- Codex rows show an `≈` cost.
- An override file changes a price, and a test covers that.
- Prices are no longer in Python code.

### T11 · Usage history in SQLite

**Why.** History, budgets and cost per project need data beyond today, and today history depends on Omarchy.

**Where.** New `agent_status/history.py`, `agent_status/collect.py`, `agent_status/web/`, `docs/api.md`.

**Approach.**
1. `STATE/history.db` with table `daily(date, agent, model, project, input, output, cache_read, cache_write, cost, PRIMARY KEY(date, agent, model, project))`. `project` is the session's cwd label.
2. The collector upserts today's rows every minute.
3. Backfill on first run: walk all Claude transcripts, Codex logs and the opencode database once, in a background thread, with a progress field in `/status`.
4. Serve `history: {days: [...30 days...], projects: [...top 10 by cost this month...]}` and replace the Omarchy-only 7-day panel. Keep Omarchy as the source for plan limits only.

**Done when.**
- The week panel works with Omarchy's directory absent.
- Backfill of a 1 GB transcript set finishes without blocking `/status`, measured.
- A restart keeps history.
- Tests use fixture transcripts.

### T12 · Budgets and limit alerts

**Depends on.** T11.

**Approach.** Config keys `budget.daily_usd` and `alerts.limit_pct` (default 0.8) in `~/.config/agent-status/config.json`. When today's cost passes the budget, or a plan window passes the threshold, show a banner styled like the needs-you one (a different colour) and chime once per crossing. Expose the active alerts in `/status`.

**Done when.**
- Crossing a threshold shows one banner and one chime, and no repeat on the next poll.
- A test covers the crossing logic.

### T13 · Codex tokens/sec

**Approach.** In `codex.py`, record the timestamp of the last `response_item` with role `user` (or the `task_started` event) before each `token_count`, and use `last_token_usage.output_tokens / (ts - start)` with the existing `tps()` guard. Verify field names against a real rollout first (`~/.codex/sessions/**/rollout-*.jsonl`).

**Done when.**
- Codex cards and model rows show tok/s.
- A fixture test covers it.

### T14 · Gemini CLI token usage

**Approach.** Research first: Gemini CLI stores chats under `~/.gemini/tmp/<project-hash>/chats/` with per-message `tokens` (`input`, `output`, `cached`, `thoughts`, `tool`, `total`) and `model`. Confirm on a real install and record the version. Then write `gemini.py` with the same incremental pattern as `codex.py`, and add Gemini to `KEEP_TRANSCRIPT` if hooks pass a usable `transcript_path`. Note that Antigravity CLI replaced Gemini CLI for free tiers on 2026-06-18; check whether it shares the format.

**Done when.**
- Gemini rows appear in the Models panel from a real-format fixture.
- `docs/compat.md` records the version checked.

### T15 · Copilot CLI token usage

**Approach.** Research where Copilot CLI keeps session logs (`~/.copilot/` session state, or the `transcriptPath` passed to `agentStop`) and whether they contain token counts. If they do, add a reader. If not, document that in `docs/compat.md` and close the task.

**Done when.**
- There is a reader with a fixture test, or a documented "not available".

### T16 · opencode "needs you" state

**Approach.** opencode's database does not record pending permission prompts. Options, in order: (a) an opencode plugin shipped by `agent-status install` that listens for permission events and writes the same session JSON hooks write; (b) a table in the database that does record them (check `session_pending` and `permission` on a newer version). Prefer (a) if opencode's plugin API exposes permission events. Confirm against opencode's plugin docs.

**Done when.**
- An opencode permission prompt turns its card amber, verified live.
- Install and uninstall add and remove the plugin.

---

## Phase 3: Interaction

### T17 · Push notifications when nobody is looking

**Approach.** Config `notify: {"url": "...", "after_s": 30}` supporting ntfy (`POST` text to a topic URL) and a generic webhook (JSON body). When a card has been `waiting` longer than `after_s` and no dashboard has polled in that time (the `SEEN` file's mtime), send one notification per wait. Send from the collector thread with a short timeout. Do this only after an explicit `agent-status install --notify <url>`; nothing leaves the machine by default.

**Done when.**
- A test with a local HTTP server receives exactly one notification per wait.
- Nothing is sent while a dashboard is open.

### T18 · Session detail view

**Approach.** Hooks append compact events (`ts, event, tool_hint`) to a per-session ring buffer of 50 entries inside the session JSON. Add `GET /session/<id>?k=` returning the buffer plus that session's per-message tokens (Claude and opencode readers). In the UI, tapping a card opens a sheet with the event timeline and a tokens-over-time sparkline. Keep the privacy boundary: hints only, never tool output.

**Done when.**
- Tapping a card shows its last 50 events.
- The endpoint checks the key.
- The hook stays under T03's time budget.

### T19 · Key rotation and `/decide` rate limit

**Approach.** `agent-status rotate-key` writes a new token and prints the new links; the server re-reads the token file when it changes. Rate-limit `POST /decide` to 10 requests a minute per client address and `GET /status` to 5 a second, answering 429.

**Done when.**
- After rotation the old link gets 403 without a restart.
- A test covers the limits.

---

## Phase 4: Platforms and displays

### T20 · Agents on other machines report to one dashboard

**Approach.** `agent-status install --report-to http://desk-pc:8787 --key K` installs hooks that, besides local state, `POST /ingest?k=` their session JSON (fire and forget, 1 s timeout, never blocking the agent). The server merges remote sessions into `/status` with a `host` field, and cards show the host. Remote sessions expire when no event has arrived for 10 minutes. Per-machine keys come from `agent-status add-machine <name>`.

**Done when.**
- Two local processes with different state directories simulate two machines, and one dashboard shows both.
- A dead remote expires.
- A hook with the server unreachable still finishes within T03's budget.

### T21 · macOS temperatures, GPU and Bluetooth batteries (**needs a human**)

**Approach.** Use stdlib-callable sources only: `ioreg -r -c AppleSmartBattery` and `ioreg -r -k BatteryPercent` (Bluetooth devices such as Magic Mouse and AirPods report `BatteryPercent`), `powermetrics` needs root so skip it, and the GPU name comes from `system_profiler SPDisplaysDataType -json`, run once and cached. Capture real output into `tests/fixtures/macos/`.

**Done when.**
- On a real Mac the Storage/Devices tile lists Bluetooth batteries.
- The GPU tile shows the chip name.
- Fixtures come from real output.

### T22 · Windows host support

**Approach.** Processes from `tasklist /v /fo csv` or PowerShell `Get-CimInstance Win32_Process` (CommandLine, ParentProcessId); memory and CPU via `ctypes` (`GlobalMemoryStatusEx`, `GetSystemTimes`); service via a Task Scheduler entry created by `schtasks`. Hook commands in agent configs need Windows quoting, and Copilot needs `powershell` instead of `bash` in `own_file`. Add `windows-latest` to CI.

**Done when.**
- CI is green on Windows, including the T03 hook harness.
- `agent-status install` creates a scheduled task that starts the server at logon.

### T23 · Light theme, wall mode, per-device layout

**Approach.** Colour tokens already live in `:root` in `style.css`. Add a light set under `@media (prefers-color-scheme: light)` and a `?theme=dark|light` override. Add `?view=wall` (agents only, large type, for a TV or a far-away tablet) and `?view=compact` (phones). Store the last choice in `localStorage` (wrapped in try/catch, like `store` in `app.js`).

**Done when.**
- Each view has no horizontal overflow at 412, 1024 and 1366 px widths.
- Contrast passes WCAG AA in both themes (check the state colours on their tinted backgrounds).

### T24 · Other clients: terminal UI and ESP32 example

**Approach.** `agent-status tui`: a curses view of `/status` (local or `--url`), stdlib `curses` only. `examples/esp32/`: an Arduino sketch that polls `/status` and shows the needs-you count and a state LED per agent on a small TFT screen. Both consume the T06 contract only.

**Done when.**
- `agent-status tui` runs in an 80×24 terminal.
- The example compiles with arduino-cli in CI, or is documented as untested hardware.

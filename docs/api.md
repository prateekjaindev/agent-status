# `/status` JSON contract

`GET /status?k=<token>` returns one JSON snapshot of every agent, the machine and today's usage. The dashboard, demo
mode, history, remote agents and other clients all read this shape, so it is documented here and checked by
[`tests/test_contract.py`](../tests/test_contract.py).

`schema` is the contract version. Bump it when a key is removed or its type or meaning changes; additive fields keep
the version and update this page. Any change to the keys or types must also update the contract test.

## Top level

| Key | Type | Unit | Description |
|---|---|---|---|
| `schema` | integer | — | Contract version. Currently `1`. |
| `now` | number | seconds | Unix time when the snapshot was built. |
| `interval` | number | seconds | How often the collector refreshes; default `2`. |
| `agents` | array of [cards](#cards) | — | Live sessions from hooks, opencode and the process table. |
| `limits` | array of [limit groups](#limits) | — | Plan windows, from Codex logs and Omarchy's usage files. |
| `week` | array of [days](#week) | — | Up to seven days of activity from Omarchy; empty without it. |
| `system` | [system object](#system) | — | Machine stats and short histories. |
| `today` | [today object](#today) | — | Today's token, cost and hourly usage. |

## Cards

One entry per live session. Keys marked *optional* are omitted when the source does not provide them; `id`, `kind`,
`name`, `state`, `detail`, `since` and `git` are always present.

| Key | Type | Unit | Description |
|---|---|---|---|
| `id` | string | — | Stable card id: the hook state file stem, `oc-<session>` for opencode, or `pid-<pid>` for a process-only agent. |
| `kind` | string | — | Display name, e.g. `Claude Code`, `opencode`, `Aider`. |
| `name` | string | — | Folder label (basename of the working directory, or `~` for home). |
| `state` | string | — | `working`, `waiting`, `done` or `idle`. |
| `detail` | string | — | Short status or tool hint, e.g. `Bash: run tests`. Never prompt text, file contents or tool output. |
| `since` | number | seconds | Unix time the current state began. |
| `git` | object or null | — | `{branch, files, add, rem}` for the working directory, or `null` outside a repository. `branch` is a string or null; `files` is the number of changed files; `add`/`rem` are changed lines. The card's `cwd` is consumed to build this and is not part of the payload. |
| `started` | number or null | seconds | *Optional.* Unix time the session started. |
| `model` | string | — | *Optional.* Model id, e.g. `claude-opus-5-5`. |
| `prompts` | integer or null | — | *Optional.* User prompts seen in the session. |
| `tools` | integer or null | — | *Optional.* Tool calls seen in the session. |
| `cpu` | number or null | percent of one core | *Optional.* CPU used by the agent's process tree. |
| `rss` | integer or null | bytes | *Optional.* Resident memory of the agent's process tree. |
| `tps` | number or null | output tokens/second | *Optional.* Estimated throughput; includes time to first token. |
| `ctx` | number or null | fraction | *Optional.* Share of the model's context window currently used, `0`–`1`. |
| `ctx_tokens` | integer or null | tokens | *Optional.* Tokens currently in context. |
| `cost` | number or null | USD | *Optional.* Session cost. Claude is API-equivalent (`estimated: true`); opencode reports its real cost. `null` when no price is known. |
| `estimated` | boolean | — | *Optional.* True when `cost` was computed from a price table rather than reported by the agent. |
| `ask` | string | — | *Optional.* Opaque token for `POST /decide`; present only while a permission prompt is waiting. |
| `ask_until` | number | seconds | *Optional.* Unix time the permission hook stops waiting. |
| `ask_text` | string | — | *Optional.* The command or file being approved. |
| `lines` | array | lines | *Optional.* `[added, removed]` from opencode's session summary. |
| `guessed` | boolean | — | *Optional.* True for process-only agents whose state is inferred from CPU use. |

Which source fills what:

| Source | Cards include |
|---|---|
| Hooks (Claude Code, Codex, Cursor, Gemini CLI, Copilot CLI) | `id`, `kind`, `name`, `state`, `detail`, `since`, `started`, `model`, `prompts`, `tools`, `cpu`, `rss`; Claude and Codex also add `ask`, `ask_until`, `ask_text` while waiting. |
| Claude transcripts | `tps`, `ctx`, `ctx_tokens`, `cost`, `estimated`. |
| Codex session logs | `ctx`, `ctx_tokens`, `model`. |
| opencode database | `id`, `kind`, `name`, `state`, `detail`, `since`, `started`, `model`, `tps`, `ctx_tokens`, `cost`, `prompts`, `lines`. |
| Process table | `id`, `kind`, `name`, `state`, `detail`, `since`, `cpu`, `rss`, `guessed`. |

## Limits

Each group is one agent's plan windows.

| Key | Type | Unit | Description |
|---|---|---|---|
| `name` | string | — | Agent or plan name, e.g. `Codex`. |
| `tier` | string | — | *Optional.* Plan tier label, e.g. `Plus`, `Max`; may be empty. |
| `updated` | string | ISO 8601 | *Optional.* When Omarchy last wrote the file. |
| `limits` | array | — | `label` (string, e.g. `5-hour` or `Weekly`), `pct` (number, `0`–`1` used), `resets` (ISO 8601 string or null). |

## Week

Up to seven entries, oldest first, from Omarchy's usage files. Without Omarchy the array is empty.

| Key | Type | Description |
|---|---|---|
| `date` | string | Local date, `YYYY-MM-DD`. |
| `agents` | object | Maps an agent display name to Omarchy's `messageCount` for that day. |

## System

| Key | Type | Unit | Description |
|---|---|---|---|
| `host` | string | — | Hostname. |
| `uptime` | number | seconds | Time since boot. |
| `cpu` | object | — | `pct` (`0`–`100`, average since the last sample), `cores` (array of per-core `0`–`100`), `load` (`[1m, 5m, 15m]` averages), `temp` (°C or null). |
| `mem` | object | bytes | `total`, `used`, `pct` (`0`–`100`), `swap_total`, `swap_used`. |
| `gpus` | array | — | `name`; `util` (percent or null); `mem_used`, `mem_total` (bytes); `temp` (°C or null); `power`, `power_limit` (watts or null). Empty when no supported GPU is found. |
| `net` | object | bytes/second | `rx` and `tx` since the last sample. |
| `disks` | array | — | `mount` (string), `total` and `used` (bytes). Root and home are deduplicated. |
| `nvme_temp` | number or null | °C | NVMe temperature when a sensor exists. |
| `devices` | array | — | Batteries and peripherals: `name`, `pct` (`0`–`100`), `status` (`charging`, `discharging`, `Full`, …). |
| `hist` | object | — | Sparkline history, oldest first, at most 150 samples: `cpu`, `gpu`, `mem` (`0`–`100`), `rx`, `tx` (bytes/second). |

## Today

| Key | Type | Unit | Description |
|---|---|---|---|
| `cost` | number | USD | Sum of priced model rows; unpriced rows do not contribute. |
| `tokens` | integer | tokens | Sum of every row's `total`. |
| `output` | integer | tokens | Sum of output tokens. |
| `burn` | number | USD | Cost in the last hour. |
| `hours` | array | — | Exactly 24 `[tokens, USD]` pairs, indexed by local hour (`0`–`23`). |
| `models` | array | — | Per-model rows, sorted by cost (highest first), then total tokens. |

Each model row:

| Key | Type | Unit | Description |
|---|---|---|---|
| `agent` | string | — | Display name, e.g. `Claude Code`, `Codex`, `opencode`. |
| `model` | string | — | Model id. |
| `input` | integer | tokens | Uncached input tokens. |
| `output` | integer | tokens | Output tokens. |
| `cache_read` | integer | tokens | Cache-read tokens. |
| `cache_write` | integer | tokens | Cache-write tokens. |
| `cost` | number or null | USD | Price for this row, or null when the model has no price. |
| `estimated` | boolean | — | True when the cost came from the local price table. |
| `tps` | number or null | output tokens/second | Throughput, or null when it cannot be measured. |
| `total` | integer | tokens | `input + output + cache_read + cache_write`. |

## Access

Every data response needs the key: `/status?k=<token>`. The key is generated on first run and stored in
`~/.local/state/agent-status/token` (mode `600`). Prompts, file contents and tool output are never part of this
payload; only folder labels, branches, models, counts and short tool hints leave the machine.

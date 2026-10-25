"""Supported agents: how to detect each one, and how to add or remove its hooks.

Three kinds of support:
  hooks     the agent calls `agent-status hook <key>` on lifecycle events (live, exact status)
  data      agent-status reads the agent's own local database or logs (no setup)
  process   the agent is found in the process table and its state is guessed from CPU use
"""
import json, shutil
from dataclasses import dataclass, field
from pathlib import Path

from .config import CLAUDE_DIR, HOME


def ours(cmd):
    cmd = str(cmd or "")
    return " hook" in cmd and ("agent-status" in cmd or "agent_status" in cmd)


def load_json(path):
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        raise SystemExit(f"agent-status: {path} is not valid JSON; fix it or remove it, then retry")


def save_json(path, cfg):
    """Write a config file, keeping a one-time backup of the user's original."""
    backup = path.with_name(path.name + ".bak-agent-status")
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2) + "\n")


# ---------- hook file formats ----------

def nested(path, events, entry, matcher=None, per_event=None):
    """{"hooks": {Event: [{"matcher"?: .., "hooks": [{"type": "command", "command": ..}]}]}}
    Used by Claude Code, Codex and Gemini CLI. per_event overrides entry fields for some events."""
    def install(cmd):
        cfg = load_json(path)
        hooks = cfg.setdefault("hooks", {})
        for ev in events:
            groups = hooks.setdefault(ev, [])
            fields = {"type": "command", "command": cmd, **entry, **(per_event or {}).get(ev, {})}
            mine = [h for g in groups for h in g.get("hooks", []) if ours(h.get("command"))]
            for h in mine:
                h.update(fields)  # an older install may carry a stale path or timeout
            if not mine:
                group = {"hooks": [fields]}
                if matcher is not None:
                    group = {"matcher": matcher, **group}
                groups.append(group)
        save_json(path, cfg)

    def uninstall():
        if not path.exists():
            return
        cfg = load_json(path)
        before = json.dumps(cfg)
        hooks = cfg.get("hooks", {})
        for ev in list(hooks):
            for g in hooks[ev]:
                g["hooks"] = [h for h in g.get("hooks", []) if not ours(h.get("command"))]
            hooks[ev] = [g for g in hooks[ev] if g.get("hooks")]
            if not hooks[ev]:
                del hooks[ev]
        if json.dumps(cfg) != before:
            save_json(path, cfg)

    return install, uninstall


def flat(path, events):
    """{"version": 1, "hooks": {event: [{"command": ..}]}} — Cursor."""
    def install(cmd):
        cfg = load_json(path)
        cfg.setdefault("version", 1)
        hooks = cfg.setdefault("hooks", {})
        for ev in events:
            lst = hooks.setdefault(ev, [])
            if not any(ours(h.get("command")) for h in lst):
                lst.append({"command": cmd})
        save_json(path, cfg)

    def uninstall():
        if not path.exists():
            return
        cfg = load_json(path)
        before = json.dumps(cfg)
        hooks = cfg.get("hooks", {})
        for ev in list(hooks):
            hooks[ev] = [h for h in hooks[ev] if not ours(h.get("command"))]
            if not hooks[ev]:
                del hooks[ev]
        if json.dumps(cfg) != before:
            save_json(path, cfg)

    return install, uninstall


def own_file(path, events):
    """A hooks file that belongs to agent-status alone — GitHub Copilot CLI reads every ~/.copilot/hooks/*.json.
    Copilot's payloads don't name the event, so the command passes it as an argument."""
    def install(cmd):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 1, "hooks": {
            ev: [{"type": "command", "bash": f"{cmd} {ev}", "timeoutSec": 5}] for ev in events}}, indent=2) + "\n")

    def uninstall():
        path.unlink(missing_ok=True)

    return install, uninstall


# ---------- registry ----------

@dataclass
class Agent:
    key: str
    name: str
    how: str                                 # "hooks" | "data" | "process"
    bins: tuple = ()                         # commands that mean it's installed
    paths: tuple = ()                        # config dirs that mean it's installed
    procs: tuple = ()                        # process names (or npm package dirs) to look for
    hook_files: tuple = field(default=(), repr=False)  # (install, uninstall) pair for hook agents
    note: str = ""

    def found(self):
        for b in self.bins:
            if shutil.which(b):
                return b
        for p in self.paths:
            if p.exists():
                return str(p).replace(str(HOME), "~", 1)
        return None

    def install(self, exe):
        if self.hook_files:
            self.hook_files[0](f"{exe} hook {self.key}")

    def uninstall(self):
        if self.hook_files:
            self.hook_files[1]()


CLAUDE_EVENTS = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PermissionRequest", "Notification",
                 "Stop", "SessionEnd"]
CODEX_EVENTS = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PermissionRequest", "Stop", "SessionEnd"]
DECIDE_TIMEOUT = {"PermissionRequest": {"timeout": 90}}  # room for the hook's 60s wait for a dashboard tap
GEMINI_EVENTS = ["SessionStart", "BeforeAgent", "BeforeTool", "AfterTool", "AfterAgent", "Notification", "SessionEnd"]
# Cursor treats a silent reply from its permission hooks as unresolved, so only observational events are used.
CURSOR_EVENTS = ["sessionStart", "afterAgentThought", "postToolUse", "stop", "sessionEnd"]
COPILOT_EVENTS = ["sessionStart", "userPromptSubmitted", "preToolUse", "postToolUse", "permissionRequest",
                  "notification", "agentStop", "sessionEnd"]

AGENTS = [
    Agent("claude", "Claude Code", "hooks", bins=("claude",), paths=(CLAUDE_DIR,), procs=("claude", "@anthropic-ai/claude-code"),
          hook_files=nested(CLAUDE_DIR / "settings.json", CLAUDE_EVENTS, {"timeout": 5}, per_event=DECIDE_TIMEOUT),
          note="status, tokens, cost, tok/s, context"),
    Agent("codex", "Codex CLI", "hooks", bins=("codex",), paths=(HOME / ".codex",), procs=("codex", "@openai/codex"),
          hook_files=nested(HOME / ".codex/hooks.json", CODEX_EVENTS, {"timeout": 5}, per_event=DECIDE_TIMEOUT),
          note="status, tokens, context, plan limits"),
    Agent("cursor", "Cursor CLI", "hooks", bins=("cursor-agent",), paths=(HOME / ".cursor",), procs=("cursor-agent",),
          hook_files=flat(HOME / ".cursor/hooks.json", CURSOR_EVENTS), note="status"),
    Agent("gemini", "Gemini CLI", "hooks", bins=("gemini",), paths=(HOME / ".gemini/settings.json",),
          procs=("gemini", "@google/gemini-cli"),
          hook_files=nested(HOME / ".gemini/settings.json", GEMINI_EVENTS, {"name": "agent-status", "timeout": 5000}, matcher="*"),
          note="status"),
    Agent("copilot", "GitHub Copilot CLI", "hooks", bins=("copilot",), paths=(HOME / ".copilot",), procs=("copilot", "@github/copilot"),
          hook_files=own_file(HOME / ".copilot/hooks/agent-status.json", COPILOT_EVENTS), note="status"),
    Agent("opencode", "opencode", "data", bins=("opencode",), paths=(HOME / ".local/share/opencode/opencode.db",),
          note="status, tokens, real cost, tok/s (reads its database)"),
    Agent("aider", "Aider", "process", bins=("aider",), procs=("aider",)),
    Agent("amp", "Amp", "process", bins=("amp",), procs=("amp", "@sourcegraph/amp")),
    Agent("goose", "Goose", "process", bins=("goose",), procs=("goose",)),
    Agent("crush", "Crush", "process", bins=("crush",), procs=("crush",)),
    Agent("qwen", "Qwen Code", "process", bins=("qwen",), procs=("qwen", "@qwen-code/qwen-code")),
    Agent("kiro", "Kiro CLI", "process", bins=("kiro-cli",), procs=("kiro-cli",)),
    Agent("droid", "Factory Droid", "process", bins=("droid",), procs=("droid",)),
    Agent("cline", "Cline CLI", "process", bins=("cline",), procs=("cline",)),
    Agent("kimi", "Kimi CLI", "process", bins=("kimi",), procs=("kimi",)),
    Agent("auggie", "Auggie", "process", bins=("auggie",), procs=("auggie", "@augmentcode/auggie")),
    Agent("grok", "Grok CLI", "process", bins=("grok",), procs=("grok",)),
    Agent("pi", "Pi", "process", bins=("pi",), procs=("pi",)),
    Agent("qoder", "Qoder CLI", "process", bins=("qodercli",), procs=("qodercli",)),
]
BY_KEY = {a.key: a for a in AGENTS}

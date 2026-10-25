"""Agent hooks: fold lifecycle events from any supported agent into one small state file per session.

Every agent's payload is first mapped onto Claude Code's shape (hook_event_name, session_id, cwd, tool_name,
tool_input), then folded by next_state(). Runs on every tool call, so it never raises.
"""
import json, os, re, sys, time

from .config import SESSIONS
from .procs import agent_key, read_argv, read_stat

EVENT_MAPS = {
    "cursor": {"sessionStart": "SessionStart", "afterAgentThought": "Thinking", "postToolUse": "PreToolUse",
               "stop": "Stop", "sessionEnd": "SessionEnd"},
    "gemini": {"SessionStart": "SessionStart", "BeforeAgent": "UserPromptSubmit", "BeforeTool": "PreToolUse",
               "AfterTool": "PostToolUse", "AfterAgent": "Stop", "Notification": "Notification", "SessionEnd": "SessionEnd"},
    "copilot": {"sessionStart": "SessionStart", "userPromptSubmitted": "UserPromptSubmit", "preToolUse": "PreToolUse",
                "postToolUse": "PostToolUse", "permissionRequest": "PermissionRequest", "notification": "Notification",
                "agentStop": "Stop", "sessionEnd": "SessionEnd"},
}
KEEP_TRANSCRIPT = {"claude", "codex"}  # agents whose transcript format agent-status can read


def tool_detail(ev):
    name = (ev.get("tool_name") or "").split("__")[-1]  # mcp__server__tool -> tool
    inp = ev.get("tool_input")
    if not isinstance(inp, dict):
        inp = {"command": inp} if inp else {}
    path = inp.get("file_path") or inp.get("path") or inp.get("target_file") or ""
    cmd = inp.get("command")
    cmd = " ".join(map(str, cmd)) if isinstance(cmd, list) else str(cmd or "")
    hint = inp.get("description") or os.path.basename(str(path)) or inp.get("pattern") or cmd[:60]
    return f"{name}: {hint}" if hint else name


def next_state(prev, ev, now):
    """Fold one hook event into a session record. None means the session is gone."""
    name = ev.get("hook_event_name")
    if name == "SessionEnd":
        return None
    s = dict(prev or {"state": "idle", "detail": "", "since": now, "started": now, "prompts": 0, "tools": 0})
    s["cwd"] = ev.get("cwd") or s.get("cwd", "")
    for k in ("transcript_path", "model"):
        if ev.get(k):
            s[k] = ev[k]
    new = None
    if name == "UserPromptSubmit":
        new = ("working", "thinking…")
        s["prompts"] = s.get("prompts", 0) + 1
    elif name == "Thinking":
        new = ("working", "thinking…")
    elif name == "PreToolUse":
        new = ("working", tool_detail(ev))
        s["tools"] = s.get("tools", 0) + 1
    elif name == "PostToolUse":
        new = ("working", "thinking…")
    elif name == "PermissionRequest":
        new = ("waiting", ev.get("message") or f"Approve {tool_detail(ev)}")
    elif name == "Notification" and "permission" in (ev.get("message") or "").lower():
        new = ("waiting", ev["message"])  # idle reminders don't change state
    elif name == "Stop":
        new = ("done", "")
    elif name == "SessionStart" and ev.get("source") != "compact":
        new = ("idle", "")
    if new:
        if new[0] != s["state"]:
            s["since"] = now
        s["state"], s["detail"] = new
    s["updated"] = now
    return s


def normalize(ev, agent, event=None):
    """Map another agent's payload onto Claude Code's event shape."""
    ev = dict(ev)
    if event:
        ev["hook_event_name"] = event
    if agent in EVENT_MAPS:
        ev["hook_event_name"] = EVENT_MAPS[agent].get(ev.get("hook_event_name"), "")
    if agent == "cursor":
        ev["session_id"] = ev.get("conversation_id") or ev.get("session_id")
        ev["cwd"] = ev.get("cwd") or (ev.get("workspace_roots") or [""])[0]
    elif agent == "gemini" and ev.get("notification_type") == "ToolPermission":
        ev["hook_event_name"] = "PermissionRequest"
    elif agent == "copilot":
        ev["session_id"] = ev.get("sessionId") or ev.get("session_id")
        ev["tool_name"] = ev.get("toolName") or ev.get("tool_name")
        args = ev.get("toolArgs")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                pass
        ev["tool_input"] = args
    if agent not in KEEP_TRANSCRIPT:
        ev.pop("transcript_path", None)
    return ev


def agent_pid():
    """Walk up from the hook process to the agent that ran it."""
    pid = os.getppid()
    for _ in range(12):
        try:
            comm, fields = read_stat(pid)
            if agent_key(comm, read_argv(pid)):
                return pid
        except (OSError, ValueError):
            return None
        pid = int(fields[1])
        if pid <= 1:
            return None
    return None


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def hook(agent="claude", event=None):
    try:
        ev = normalize(json.load(sys.stdin), agent, event)
        sid = re.sub(r"[^A-Za-z0-9_-]", "", str(ev.get("session_id") or ""))[:80]
        if sid and ev.get("hook_event_name"):
            SESSIONS.mkdir(parents=True, exist_ok=True)
            path = SESSIONS / f"{agent}-{sid}.json"
            s = next_state(read_json(path), ev, time.time())
            if s is None:
                path.unlink(missing_ok=True)
            else:
                s["kind"] = agent
                s["pid"] = s.get("pid") or agent_pid()
                tmp = path.with_suffix(f".{os.getpid()}.tmp")
                tmp.write_text(json.dumps(s))
                tmp.replace(path)
    except Exception:
        pass  # a status display must never break the agent
    if agent == "gemini":
        print("{}")  # Gemini CLI parses stdout as JSON; an empty object means "no decision"

"""Agent hooks: fold lifecycle events from any supported agent into one small state file per session.

Every agent's payload is first mapped onto Claude Code's shape (hook_event_name, session_id, cwd, tool_name,
tool_input), then folded by next_state(). Runs on every tool call, so it never raises.

For agents in DECIDES, a PermissionRequest hook also waits (up to DECIDE_WAIT, and only while a dashboard is open)
for an Allow/Deny tap. Anything else, an error, a timeout, no tap, ends with no output: the agent's own prompt decides.
"""
import json, os, re, secrets, sys, time

from .config import DECIDE_WAIT, DECISIONS, SEEN, SESSIONS
from .procs import MAC, agent_key, proc, table

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
# Agents whose PermissionRequest fires only when a prompt is about to show, and that read this answer shape.
# Copilot is left out: its permissionRequest runs before its own rules and session approvals, so waiting there
# would stall tool calls that never needed the user.
DECIDES = {"claude", "codex"}
ASK_KEYS = ("ask", "ask_until", "ask_text")


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


def ask_text(ev):
    """What is being approved, in full: the model-written description alone is not enough to say yes to."""
    inp = ev.get("tool_input")
    if not isinstance(inp, dict):
        inp = {"command": inp} if inp else {}
    cmd = inp.get("command")
    cmd = " ".join(map(str, cmd)) if isinstance(cmd, list) else cmd
    text = cmd or inp.get("file_path") or inp.get("path") or inp.get("url") or json.dumps(inp, ensure_ascii=False)
    return f"{(ev.get('tool_name') or '').split('__')[-1]}: {text}"[:400]


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
        if new[0] != "waiting":
            for k in ASK_KEYS:
                s.pop(k, None)  # the prompt was answered somewhere else
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
    pid, procs = os.getppid(), table() if MAC else None  # macOS: one `ps` call instead of /proc lookups
    for _ in range(12):
        try:
            comm, ppid, _, argv = procs[pid] if MAC else proc(pid)
            if agent_key(comm, argv):
                return pid
        except (OSError, ValueError, IndexError, KeyError):
            return None
        pid = ppid
        if pid <= 1:
            return None
    return None


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def save(path, s):
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(s))
    tmp.replace(path)


def viewer_present(now):
    try:
        return now - SEEN.stat().st_mtime < 10
    except OSError:
        return False


def answer(behavior):
    """The stdout that tells the agent the user's choice (Claude Code and Codex share this shape)."""
    d = {"behavior": behavior}
    if behavior == "deny":
        d["message"] = "The user denied this from the agent-status dashboard."
    return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": d}}


def wait_decision(ask, until):
    f = DECISIONS / ask
    try:
        while time.time() < until:
            try:
                d = f.read_text().strip()
                return d if d in ("allow", "deny") else None
            except FileNotFoundError:
                time.sleep(0.25)
        return None
    finally:
        f.unlink(missing_ok=True)


def settle(path, ask, behavior, now):
    s = read_json(path)
    if not s or s.get("ask") != ask:
        return  # a later event already moved the session on
    for k in ASK_KEYS:
        s.pop(k, None)
    if behavior:
        s["state"], s["detail"], s["since"] = "working", {"allow": "Allowed", "deny": "Denied"}[behavior] + " from dashboard", now
    save(path, s)


def hook(agent="claude", event=None):
    out = "{}" if agent == "gemini" else ""  # Gemini CLI parses stdout as JSON; an empty object means "no decision"
    try:
        ev = normalize(json.load(sys.stdin), agent, event)
        sid = re.sub(r"[^A-Za-z0-9_-]", "", str(ev.get("session_id") or ""))[:80]
        if sid and ev.get("hook_event_name"):
            SESSIONS.mkdir(parents=True, exist_ok=True)
            path, now = SESSIONS / f"{agent}-{sid}.json", time.time()
            s = next_state(read_json(path), ev, now)
            if s is None:
                path.unlink(missing_ok=True)
            else:
                s["kind"] = agent
                s["pid"] = s.get("pid") or agent_pid()
                ask = (ev["hook_event_name"] == "PermissionRequest" and agent in DECIDES and DECIDE_WAIT > 0
                       and viewer_present(now))
                if ask:
                    DECISIONS.mkdir(parents=True, exist_ok=True)
                    s.update(ask=secrets.token_urlsafe(12), ask_until=now + DECIDE_WAIT, ask_text=ask_text(ev))
                save(path, s)
                if ask:
                    behavior = wait_decision(s["ask"], s["ask_until"])
                    settle(path, s["ask"], behavior, time.time())
                    if behavior:
                        out = json.dumps(answer(behavior))
    except Exception:
        pass  # a status display must never break the agent
    if out:
        print(out, flush=True)

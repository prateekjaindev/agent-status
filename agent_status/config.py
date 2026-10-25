"""Paths and settings. Everything can be overridden with environment variables."""
import os
from pathlib import Path

HOME = Path.home()
_STATE = Path(os.environ.get("XDG_STATE_HOME") or HOME / ".local/state")
_DATA = Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local/share")

STATE = Path(os.environ.get("AGENT_STATUS_STATE") or _STATE / "agent-status")
SESSIONS = STATE / "sessions"
CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or HOME / ".claude")
CLAUDE_PROJECTS = CLAUDE_DIR / "projects"
CURSOR_HOOKS = HOME / ".cursor/hooks.json"
OPENCODE_DB = Path(os.environ.get("AGENT_STATUS_OPENCODE_DB") or _DATA / "opencode/opencode.db")
OMARCHY_USAGE = _STATE / "omarchy/agents/usage"

HOST = os.environ.get("AGENT_STATUS_HOST", "0.0.0.0")
PORT = int(os.environ.get("AGENT_STATUS_PORT", 8787))
INTERVAL = float(os.environ.get("AGENT_STATUS_INTERVAL", 2))
USER_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config") / "agent-status/config.json"


def enabled_agents():
    """Agent keys chosen at install time, or None (track everything) when no choice was saved."""
    import json
    try:
        return set(json.loads(USER_CONFIG.read_text())["agents"])
    except (OSError, ValueError, KeyError, TypeError):
        return None

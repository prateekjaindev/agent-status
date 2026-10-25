"""Omarchy's agent usage files (~/.local/state/omarchy/agents/usage/*.json): plan limits and daily totals.

Optional: on other systems the directory simply doesn't exist and these panels stay empty.
"""
import json
from datetime import datetime

from .config import OMARCHY_USAGE
from .usage import new_row

READ_OURSELVES = {"claude", "opencode", "codex"}  # parsed directly, with more detail than these files have


def read(root=OMARCHY_USAGE):
    """Returns (plan limits, last 7 days of tokens per agent, today's rows for other agents)."""
    limits, days, rows = [], {}, []
    today = datetime.now().date().isoformat()
    for f in sorted(root.glob("*.json")):
        try:
            d = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        name = d.get("name") or f.stem
        if d.get("ready") and d.get("limits"):
            limits.append(dict(name=name, tier=d.get("tierLabel", ""), updated=d.get("updatedAt", ""),
                               limits=[dict(label=l.get("label", ""), pct=l.get("percent") or 0, resets=l.get("resetsAt"))
                                       for l in d["limits"]]))
        for day in d.get("recentDays") or []:
            if day.get("messageCount"):
                days.setdefault(day["date"], {})[name] = day["messageCount"]  # Omarchy counts tokens here
        if f.stem not in READ_OURSELVES and str(d.get("updatedAt", "")).startswith(today):
            for model, n in (d.get("todayTokensByModel") or {}).items():
                r = new_row(name, model)
                r.update(output=n, priced=False)  # shortcut: only a daily total is available, shown as output
                rows.append(r)
    week = [dict(date=k, agents=days[k]) for k in sorted(days)[-7:]]
    return limits, week, rows

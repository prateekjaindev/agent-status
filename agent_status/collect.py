"""Builds one status snapshot from every source. A background thread refreshes it; HTTP serves the cache."""
import json, threading, time
from datetime import datetime

from . import omarchy
from .agents import BY_KEY
from .claude import Transcripts
from .codex import CodexSessions
from .config import INTERVAL, SESSIONS, enabled_agents
from .gitinfo import git_info
from .hooks import read_json
from .opencode import OpenCode
from .procs import ProcTable, label
from .system import System
from .usage import finish_rows

STALE = 6 * 3600  # hook records without a known pid are dropped after this long


def today_start():
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def add_hours(*series):
    return [[sum(h[i][0] for h in series), sum(h[i][1] for h in series)] for i in range(24)]


class Collector:
    def __init__(self):
        self.procs, self.system = ProcTable(), System()
        self.claude, self.codex, self.oc = Transcripts(), CodexSessions(), OpenCode()
        self.json = b"{}"

    def hooked(self, now, on):
        cards, pids = [], set()
        for f in SESSIONS.glob("*.json"):
            s = read_json(f)
            if not s:
                continue
            kind, pid = s.get("kind", "claude"), s.get("pid")
            if pid and pid not in self.procs.procs:
                f.unlink(missing_ok=True)  # the agent exited without a SessionEnd
                continue
            if (not pid and now - s.get("updated", 0) > STALE) or not on(kind):
                continue
            pids.add(pid)
            cpu, rss = self.procs.tree(pid) if pid else (None, None)
            agent = BY_KEY.get(kind)
            card = dict(id=f.stem, kind=agent.name if agent else kind, name=label(s.get("cwd", "")), cwd=s.get("cwd", ""),
                        state=s["state"], detail=s.get("detail", ""), since=s.get("since", now), started=s.get("started"),
                        model=s.get("model", ""), prompts=s.get("prompts"), tools=s.get("tools"), cpu=cpu, rss=rss)
            if s.get("ask") and s.get("ask_until", 0) > now:  # a hook is waiting for an Allow/Deny tap
                card.update(ask=s["ask"], ask_until=s["ask_until"], ask_text=s.get("ask_text", ""))
            reader = {"claude": self.claude, "codex": self.codex}.get(kind)
            if reader:
                card.update({k: v for k, v in reader.session(s.get("transcript_path")).items() if v is not None})
            cards.append(card)
        return cards, pids

    def tick(self):
        now, since = time.time(), today_start()
        enabled = enabled_agents()
        on = lambda key: enabled is None or key in enabled
        self.procs.refresh(now)
        if on("claude"):
            self.claude.scan(since)
        if on("codex"):
            self.codex.scan(since)

        cards, pids = self.hooked(now, on)
        rows, hours, burn = [], [], 0.0
        if on("claude"):
            r, h, b = self.claude.usage(since, now)
            rows, hours, burn = rows + r, hours + [h], burn + b
        if on("codex"):
            r, h = self.codex.usage(since)
            rows, hours = rows + r, hours + [h]
        if on("opencode"):
            c, r, h, b = self.oc.read(now, since)
            cards, rows, hours, burn = cards + c, rows + r, hours + [h], burn + b
        cards += self.procs.scanned(now, pids, enabled)
        for c in cards:
            c["git"] = git_info(c.pop("cwd", ""), now)

        limits = self.codex.limits(now) if on("codex") else []
        om_limits, week, om_rows = omarchy.read()
        have = {l["name"] for l in limits}
        limits += [l for l in om_limits if l["name"] not in have]
        rows = finish_rows(rows + om_rows)
        snapshot = dict(
            now=now, interval=INTERVAL, agents=cards, limits=limits, week=week, system=self.system.sample(now),
            today=dict(cost=sum(r["cost"] or 0 for r in rows), tokens=sum(r["total"] for r in rows),
                       output=sum(r["output"] for r in rows), burn=burn,
                       hours=add_hours(*hours) if hours else [[0, 0]] * 24, models=rows))
        self.json = json.dumps(snapshot, separators=(",", ":")).encode()
        return snapshot

    def run(self):
        while True:
            started = time.monotonic()
            try:
                self.tick()
            except Exception as e:  # keep serving the last good snapshot
                print(f"agent-status: refresh failed: {e!r}", flush=True)
            time.sleep(max(INTERVAL - (time.monotonic() - started), 0.2))

    def start(self):
        self.tick()
        threading.Thread(target=self.run, daemon=True).start()

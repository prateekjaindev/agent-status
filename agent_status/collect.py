"""Builds one status snapshot from every source. A background thread refreshes it; HTTP serves the cache."""
import json, threading, time
from datetime import datetime

from . import omarchy
from .agents import BY_KEY
from .claude import Transcripts
from .codex import CodexSessions
from .config import DECIDE_WAIT, DECISIONS, INTERVAL, SESSIONS, STATE, enabled_agents
from .gitinfo import git_info
from .hooks import read_json
from .opencode import OpenCode
from .procs import ProcTable, label
from .usage import PRICES_AS_OF, finish_rows, price_for

STALE = 6 * 3600  # hook records without a known pid are dropped after this long
TMP_STALE = 60  # a hook killed mid-write leaves a *.tmp younger than any real write
DECISION_STALE = DECIDE_WAIT * 2  # a tap nobody consumed; the hook's wait is already over
CLEAN_INTERVAL = 3600


def _older(path, now, age):
    try:
        return now - path.stat().st_mtime > age
    except OSError:
        return False


def clean_state(now=None, state=STATE, sessions=SESSIONS, decisions=DECISIONS):
    """Remove leftovers from hooks or agents killed mid-write. Returns how many of each kind went."""
    now = time.time() if now is None else now
    removed = dict(tmp=0, decisions=0, sessions=0)
    for p in list(state.rglob("*.tmp")) if state.exists() else []:
        if _older(p, now, TMP_STALE):
            try:
                p.unlink()
                removed["tmp"] += 1
            except OSError:
                pass
    for p in list(decisions.glob("*")) if decisions.exists() else []:
        if p.is_file() and _older(p, now, DECISION_STALE):
            try:
                p.unlink()
                removed["decisions"] += 1
            except OSError:
                pass
    for p in list(sessions.glob("*.json")) if sessions.exists() else []:
        if not _older(p, now, STALE):
            continue
        s = read_json(p)
        if s is None or not s.get("pid"):  # without a pid, hooked() cannot reap it when the agent exits
            try:
                p.unlink()
                removed["sessions"] += 1
            except OSError:
                pass
    return removed


def today_start():
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def add_hours(*series):
    return [[sum(h[i][0] for h in series), sum(h[i][1] for h in series)] for i in range(24)]


def percentile(values, q):
    if not values:
        return None
    s = sorted(values)
    return round(s[min(int(len(s) * q), len(s) - 1)], 1)


class Collector:
    def __init__(self):
        self.procs = ProcTable()
        self.claude, self.codex, self.oc = Transcripts(), CodexSessions(), OpenCode()
        self.json = b"{}"
        self._cleaned = 0.0

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
            agent = BY_KEY.get(kind)
            card = dict(id=f.stem, kind=agent.name if agent else kind, name=label(s.get("cwd", "")), cwd=s.get("cwd", ""),
                        state=s["state"], detail=s.get("detail", ""), since=s.get("since", now), started=s.get("started"),
                        model=s.get("model", ""), prompts=s.get("prompts"), tools=s.get("tools"))
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
        rows, hours, burn, latencies = [], [], 0.0, []
        if on("claude"):
            r, h, b = self.claude.usage(since, now)
            rows, hours, burn = rows + r, hours + [h], burn + b
            latencies += self.claude.metrics(since)
        if on("codex"):
            r, h, b = self.codex.usage(since, now)
            rows, hours, burn = rows + r, hours + [h], burn + b
        if on("opencode"):
            c, r, h, b = self.oc.read(now, since)
            cards, rows, hours, burn = cards + c, rows + r, hours + [h], burn + b
            latencies += self.oc.metrics(since)
        cards += self.procs.scanned(now, pids, enabled)
        for c in cards:
            c["git"] = git_info(c.pop("cwd", ""), now)

        limits = self.codex.limits(now) if on("codex") else []
        om_limits, week, om_rows = omarchy.read()
        have = {l["name"] for l in limits}
        limits += [l for l in om_limits if l["name"] not in have]
        rows = finish_rows(rows + om_rows)

        cost = sum(r["cost"] or 0 for r in rows)
        cache_read = sum(r["cache_read"] for r in rows)
        cache_total = sum(r["input"] for r in rows) + cache_read
        cache_hit = cache_read / cache_total if cache_total else None
        cache_saved = sum(r["cache_read"] * (p["in"] - p["cache_read"]) / 1e6
                          for r in rows if r["cache_read"] and (p := price_for(r["model"])))
        prompts = sum(c.get("prompts") or 0 for c in cards)
        waiting = [c for c in cards if c["state"] == "waiting"]
        speeds = [r["tps"] for r in rows if r["tps"]]
        perf = dict(
            latency_p50=percentile(latencies, .5), latency_p95=percentile(latencies, .95), latency_n=len(latencies),
            tps_p50=percentile(speeds, .5), tps_p95=percentile(speeds, .95), tps_n=len(speeds),
            cache_hit=round(cache_hit, 3) if cache_hit is not None else None,
            cache_saved=round(cache_saved, 4),
            cost_per_prompt=round(cost / prompts, 4) if prompts else None,
            stalled=sum(1 for c in cards if c["state"] == "working" and now - c["since"] > 1800),
            context_high=sum(1 for c in cards if (c.get("ctx") or 0) >= 0.8),
            waiting=len(waiting),
            oldest_wait=round(max((now - c["since"] for c in waiting), default=0), 0),
        )
        snapshot = dict(
            schema=2, now=now, interval=INTERVAL, prices_as_of=PRICES_AS_OF, agents=cards, limits=limits, week=week,
            perf=perf,
            today=dict(cost=cost, tokens=sum(r["total"] for r in rows), output=sum(r["output"] for r in rows), burn=burn,
                       hours=add_hours(*hours) if hours else [[0, 0]] * 24, models=rows))
        self.json = json.dumps(snapshot, separators=(",", ":")).encode()
        return snapshot

    def run(self):
        while True:
            started = time.monotonic()
            try:
                self.tick()
                if started - self._cleaned >= CLEAN_INTERVAL:
                    clean_state()
                    self._cleaned = started
            except Exception as e:  # keep serving the last good snapshot
                print(f"agent-status: refresh failed: {e!r}", flush=True)
            time.sleep(max(INTERVAL - (time.monotonic() - started), 0.2))

    def start(self):
        clean_state()
        self._cleaned = time.monotonic()
        self.tick()
        threading.Thread(target=self.run, daemon=True).start()

"""A generated /status snapshot for screenshots and demos. Fictional agents only: no real paths or prompts."""
import json, math, time
from datetime import datetime, timedelta

from .usage import finish_rows, new_row


def _iso(ts):
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def _wave(n, base, amp, period, phase=0.0, digits=1):
    return [round(base + amp * math.sin(i / period + phase), digits) for i in range(n)]


def _rows():
    rows = []

    claude = new_row("Claude Code", "claude-opus-5-5")
    claude.update(input=182_000, output=14_500, cache_read=3_100_000, cache_write=220_000, cost=4.83,
                  estimated=True, tps_out=14_500, tps_sec=254)
    rows.append(claude)

    codex = new_row("Codex", "gpt-6-sol")
    codex.update(input=96_000, output=8_400, cache_read=240_000, priced=False, tps_out=8_400, tps_sec=195)
    rows.append(codex)

    oc = new_row("opencode", "deepseek-v4")
    oc.update(input=42_000, output=6_100, cache_read=210_000, cache_write=12_000, cost=0.19,
              tps_out=6_100, tps_sec=160)
    rows.append(oc)

    cursor = new_row("Cursor CLI", "claude-sonnet-4-6")
    cursor.update(input=28_000, output=3_200, cache_read=90_000, cache_write=5_000, cost=0.31,
                  estimated=True, tps_out=3_200, tps_sec=94)
    rows.append(cursor)

    aider = new_row("Aider", "qwen-3-coder")
    aider.update(input=8_000, output=2_400, priced=False)
    rows.append(aider)
    return finish_rows(rows)


def snapshot(now=None):
    """Build a contract-valid snapshot. `now` lets tests pin the rotating parts."""
    now = time.time() if now is None else now
    phase = now / 9
    claude_done = int(phase) % 3 == 2
    aider_busy = int(now // 6) % 2 == 0
    today = datetime.now().date()

    cards = [
        dict(id="demo-claude", kind="Claude Code", name="checkout", state="done" if claude_done else "working",
             detail="" if claude_done else "Bash: run tests", since=now - (12 if claude_done else 95),
             started=now - 1420, model="claude-opus-5-5", prompts=3, tools=7, cpu=18.4, rss=412_000_000,
             tps=57.3, ctx=0.18, ctx_tokens=182_000, cost=1.42, estimated=True,
             git=dict(branch="feature/checkout", files=3, add=42, rem=7)),
        dict(id="demo-codex", kind="Codex CLI", name="api", state="waiting", detail="Approve Bash",
             since=now - 35, started=now - 900, model="gpt-6-sol", prompts=2, tools=4, cpu=2.1, rss=198_000_000,
             ctx=0.64, ctx_tokens=160_000, ask="demo-ask-codex", ask_until=now + 45,
             ask_text="Bash: git push --force-with-lease",
             git=dict(branch="main", files=1, add=6, rem=2)),
        dict(id="demo-opencode", kind="opencode", name="dashboard", state="working", detail="Fix login redirect",
             since=now - 240, started=now - 3000, model="deepseek-v4", tps=38.6, ctx_tokens=84_000, cost=0.19,
             prompts=5, lines=[128, 24], git=dict(branch="fix/login", files=6, add=128, rem=24)),
        dict(id="demo-cursor", kind="Cursor CLI", name="mobile", state="done", detail="",
             since=now - 620, started=now - 2400, model="claude-sonnet-4-6", prompts=4, tools=12,
             cpu=0.0, rss=156_000_000, git=dict(branch="release/2.1", files=0, add=0, rem=0)),
        dict(id="pid-14207", kind="Aider", name="infra", state="working" if aider_busy else "idle",
             detail="busy" if aider_busy else "", since=now - 30, cpu=4.2 if aider_busy else 0.4,
             rss=98_000_000, guessed=True, git=dict(branch="main", files=2, add=9, rem=4)),
    ]

    limits = [
        dict(name="Claude", tier="Max", updated=_iso(now - 60), limits=[
            dict(label="5-hour", pct=0.42, resets=_iso(now + 3 * 3600)),
            dict(label="Weekly", pct=0.71, resets=_iso(now + 2 * 86400))]),
        dict(name="Codex", tier="Plus", limits=[
            dict(label="5-hour", pct=0.64, resets=_iso(now + 2 * 3600))]),
    ]

    week = []
    for i in range(7):
        week.append(dict(date=(today - timedelta(days=6 - i)).isoformat(), agents={
            "Claude Code": 18000 + i * 4100, "Codex": 6200 + i * 1800,
            "opencode": 9000 + i * 2400, "Cursor CLI": 2100 + i * 900}))

    hours = [[int(7000 * math.exp(-((h - 15) / 4.5) ** 2) + 900 + 150 * (h % 3)),
              round(0.04 * (7000 * math.exp(-((h - 15) / 4.5) ** 2) + 900 + 150 * (h % 3)) / 1000, 3)]
             for h in range(24)]
    rows = _rows()
    today_usage = dict(cost=round(sum(r["cost"] or 0 for r in rows), 2),
                       tokens=sum(r["total"] for r in rows), output=sum(r["output"] for r in rows),
                       burn=0.42, hours=hours, models=rows)

    cores = [int(18 + 12 * math.sin(phase + i / 3)) for i in range(16)]
    system = dict(
        host="studio", uptime=3 * 86400 + 7200,
        cpu=dict(pct=round(22 + 8 * math.sin(phase), 1), cores=cores, load=[1.24, 0.98, 0.71], temp=52.0),
        mem=dict(total=64 * 2**30, used=38 * 2**30, pct=59.4, swap_total=8 * 2**30, swap_used=512 * 2**20),
        gpus=[dict(name="RTX 4090", util=round(30 + 10 * math.sin(phase / 2), 1), mem_used=6 * 2**30,
                   mem_total=24 * 2**30, temp=63.0, power=141.0, power_limit=450.0)],
        net=dict(rx=round(1_200_000 + 400_000 * math.sin(phase), 0),
                 tx=round(180_000 + 60_000 * math.sin(phase + 1), 0)),
        disks=[dict(mount="/", total=2 * 10**12, used=780 * 10**9)],
        nvme_temp=44.0,
        devices=[dict(name="Battery", pct=76.0, status="discharging"),
                 dict(name="Magic Mouse", pct=61.0, status="discharging")],
        hist=dict(
            cpu=_wave(60, 22, 9, 5, phase), gpu=_wave(60, 30, 12, 7, phase / 2),
            mem=_wave(60, 59, 1.5, 11, phase / 3), rx=_wave(60, 1_200_000, 300_000, 4, phase, 0),
            tx=_wave(60, 180_000, 50_000, 5, phase, 0)),
    )

    return dict(schema=1, now=now, interval=2, agents=cards, limits=limits, week=week,
                system=system, today=today_usage)


class Demo:
    """Stands in for Collector: `/status` calls .json, which rotates a little on every request."""
    demo = True

    @property
    def json(self):
        return json.dumps(snapshot(), separators=(",", ":")).encode()

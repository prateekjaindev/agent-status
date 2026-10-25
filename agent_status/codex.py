"""Codex CLI session logs (~/.codex/sessions/**/rollout-*.jsonl): tokens, context use and plan limits.

`token_count` events carry cumulative totals, so usage is the difference between consecutive events.
Read incrementally, like the Claude transcripts.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from .claude import parse_ts
from .config import HOME
from .usage import new_row

KEYS = ("input_tokens", "cached_input_tokens", "output_tokens")
WINDOWS = {300: "5-hour", 10080: "Weekly", 43200: "Monthly"}


class CodexSessions:
    def __init__(self, root=HOME / ".codex/sessions"):
        self.root = Path(root)
        self.files = {}   # path -> {"off", "model", "total", "events": [(ts, model, delta)], "last", "window"}
        self.rate = None  # (ts, rate_limits) from the newest event seen

    def scan(self, since):
        for p in self.root.rglob("rollout-*.jsonl"):
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_mtime < since:
                continue
            f = self.files.get(str(p))
            if f is None or st.st_size < f["off"]:
                f = self.files[str(p)] = {"off": 0, "model": "?", "total": {}, "events": [], "last": {}, "window": None}
            if st.st_size > f["off"]:
                self._read(p, f)

    def _read(self, path, f):
        with open(path, "rb") as fh:
            fh.seek(f["off"])
            for line in fh:
                if not line.endswith(b"\n"):
                    break
                f["off"] += len(line)
                try:
                    e = json.loads(line)
                    ts, p = parse_ts(e["timestamp"]), e.get("payload") or {}
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
                if e.get("type") == "turn_context" and p.get("model"):
                    f["model"] = p["model"]
                elif e.get("type") == "event_msg" and p.get("type") == "token_count":
                    if p.get("rate_limits") and (not self.rate or ts >= self.rate[0]):
                        self.rate = (ts, p["rate_limits"])
                    info = p.get("info") or {}
                    total = info.get("total_token_usage") or {}
                    delta = {k: (total.get(k) or 0) - (f["total"].get(k) or 0) for k in KEYS}
                    if total and any(delta.values()):
                        f["events"].append((ts, f["model"], delta))
                        f["total"], f["last"] = total, info.get("last_token_usage") or {}
                        f["window"] = info.get("model_context_window") or f["window"]

    def session(self, path):
        f = self.files.get(path or "")
        if not f or not f["last"]:
            return {}
        ctx = f["last"].get("input_tokens") or 0  # OpenAI counts cached tokens inside input_tokens
        return dict(model=f["model"], ctx_tokens=ctx, ctx=ctx / f["window"] if f["window"] else None)

    def usage(self, since):
        rows, hours = {}, [[0, 0.0] for _ in range(24)]
        for f in self.files.values():
            for ts, model, d in f["events"]:
                if ts < since:
                    continue
                r = rows.setdefault(model, new_row("Codex", model))
                r["priced"] = False  # shortcut: no reliable per-token prices for Codex models yet
                r["input"] += d["input_tokens"] - d["cached_input_tokens"]
                r["cache_read"] += d["cached_input_tokens"]
                r["output"] += d["output_tokens"]
                hours[datetime.fromtimestamp(ts).hour][0] += d["input_tokens"] + d["output_tokens"]
        return list(rows.values()), hours

    def limits(self, now):
        if not self.rate:
            return []
        rl, out = self.rate[1], []
        for k in ("primary", "secondary"):
            w = rl.get(k)
            resets = (w or {}).get("resets_at")
            if w and w.get("used_percent") is not None and (not resets or resets > now):  # past resets are stale
                out.append(dict(label=WINDOWS.get(w.get("window_minutes"), f"{w.get('window_minutes')} min"),
                                pct=w["used_percent"] / 100,
                                resets=datetime.fromtimestamp(resets, timezone.utc).isoformat() if resets else None))
        return [dict(name="Codex", tier=(rl.get("plan_type") or "").title(), limits=out)] if out else []

"""Claude Code transcripts (~/.claude/projects/**/*.jsonl): tokens, cost, tok/s and context use.

Files are read incrementally, so each refresh only parses lines appended since the last one.
"""
import json
from datetime import datetime
from pathlib import Path

from .config import CLAUDE_PROJECTS
from .usage import claude_cost, context_window, new_row, tps

CTX_KEYS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def msg_tps(r):
    return tps(r["usage"].get("output_tokens") or 0, r["end"] - r["start"])


class Transcripts:
    def __init__(self, root=CLAUDE_PROJECTS):
        self.root = Path(root)
        self.files = {}  # path -> {"off", "prev", "msgs": {message id: {start, end, model, usage}}}

    def scan(self, since):
        """Read new lines from every transcript touched since `since`."""
        for p in self.root.rglob("*.jsonl"):
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_mtime < since:
                continue
            f = self.files.get(str(p))
            if f is None or st.st_size < f["off"]:
                f = self.files[str(p)] = {"off": 0, "prev": None, "msgs": {}}
            if st.st_size > f["off"]:
                self._read(p, f)

    def _read(self, path, f):
        with open(path, "rb") as fh:
            fh.seek(f["off"])
            for line in fh:
                if not line.endswith(b"\n"):
                    break  # still being written
                f["off"] += len(line)
                try:
                    e = json.loads(line)
                    ts = parse_ts(e["timestamp"])
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
                m = e.get("message") if isinstance(e.get("message"), dict) else {}
                if (e.get("type") == "assistant" and m.get("id") and isinstance(m.get("usage"), dict)
                        and m.get("model") != "<synthetic>"):
                    # one response spans several lines; the last one carries the final usage
                    r = f["msgs"].setdefault(m["id"], {"start": f["prev"] or ts})
                    r.update(end=ts, model=m.get("model") or "?", usage=m["usage"])
                elif e.get("type") == "user":
                    f["prev"] = ts  # a request starts when the prompt or tool result lands

    def session(self, path):
        """Model, tok/s, context use and cost for one session's transcript."""
        f = self.files.get(path or "")
        if not f or not f["msgs"]:
            return {}
        msgs = sorted(f["msgs"].values(), key=lambda r: r["end"])
        last = msgs[-1]
        ctx = sum(last["usage"].get(k) or 0 for k in CTX_KEYS)
        costs = [c for r in msgs if (c := claude_cost(r["model"], r["usage"])) is not None]
        return dict(model=last["model"], tps=next((s for r in reversed(msgs) if (s := msg_tps(r))), None),
                    ctx=ctx / context_window(last["model"]), ctx_tokens=ctx,
                    cost=sum(costs) if costs else None, estimated=True)

    def usage(self, since, now):
        """Today's per-model rows, per-hour [tokens, cost], and cost over the last hour."""
        rows, hours, last_hour = {}, [[0, 0.0] for _ in range(24)], 0.0
        for f in self.files.values():
            for r in f["msgs"].values():
                if r["end"] < since:
                    continue
                u, model = r["usage"], r["model"]
                row = rows.setdefault(model, new_row("Claude Code", model))
                row["estimated"] = True
                row["input"] += u.get("input_tokens") or 0
                row["output"] += u.get("output_tokens") or 0
                row["cache_read"] += u.get("cache_read_input_tokens") or 0
                row["cache_write"] += u.get("cache_creation_input_tokens") or 0
                cost = claude_cost(model, u)
                if cost is None:
                    row["priced"] = False
                else:
                    row["cost"] += cost
                    if now - r["end"] < 3600:
                        last_hour += cost
                if (speed := msg_tps(r)):
                    row["tps_out"] += u["output_tokens"]
                    row["tps_sec"] += r["end"] - r["start"]
                h = hours[datetime.fromtimestamp(r["end"]).hour]
                h[0] += sum(u.get(k) or 0 for k in CTX_KEYS) + (u.get("output_tokens") or 0)
                h[1] += cost or 0
        return list(rows.values()), hours, last_hour

    def metrics(self, since):
        """Turn durations in seconds for responses that finished today."""
        return [r["end"] - r["start"] for f in self.files.values() for r in f["msgs"].values()
                if r["end"] >= since and 0 < r["end"] - r["start"] < 900]

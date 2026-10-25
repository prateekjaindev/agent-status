"""Token maths shared by the collectors: prices, cost, tokens/sec, context windows, usage rows."""
import re

# $/MTok: input, output, cache read. Cache writes bill 1.25x input (5-minute TTL) or 2x (1-hour TTL).
# Source: Anthropic first-party API pricing. Longest matching prefix wins, so suffixes like "[1m]" still match.
PRICES = {
    "claude-fable-5-1": (10, 50, 0.25),
    "claude-fable-5": (10, 50, 1.00),
    "claude-opus-5-5": (4, 20, 0.20),
    "claude-opus-5": (5, 25, 0.50),
    "claude-opus-4-8": (5, 25, 0.50),
    "claude-opus-4-7": (5, 25, 0.50),
    "claude-opus-4-6": (5, 25, 0.50),
    "claude-sonnet-5-5": (2, 10, 0.20),
    "claude-sonnet-5": (2, 10, 0.20),
    "claude-sonnet-4-6": (3, 15, 0.30),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-haiku-4-5": (1, 5, 0.10),
}


def price_for(model):
    best = max((k for k in PRICES if (model or "").startswith(k)), key=len, default=None)
    return PRICES.get(best)


def claude_cost(model, u):
    """API-equivalent dollars for one Claude response's usage block, or None for unknown models."""
    p = price_for(model)
    if not p:
        return None
    w1h = (u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens") or 0
    w5m = (u.get("cache_creation_input_tokens") or 0) - w1h
    return ((u.get("input_tokens") or 0) * p[0] + (u.get("output_tokens") or 0) * p[1]
            + (u.get("cache_read_input_tokens") or 0) * p[2] + w5m * p[0] * 1.25 + w1h * p[0] * 2) / 1e6


def context_window(model):
    """Claude 4.6+ and every 5.x model have a 1M window; older ones 200k."""
    m = re.match(r"claude-[a-z]+-(\d+)(?:-(\d+))?", model or "")
    if not m:
        return 200_000
    major, minor = int(m[1]), int(m[2] or 0)
    return 1_000_000 if major >= 5 or (major == 4 and minor >= 6) else 200_000


def tps(out, seconds):
    """Output tokens/sec for one response, including time to first token. None when not measurable."""
    return out / seconds if out >= 20 and 0.3 < seconds < 900 else None


def new_row(agent, model):
    return dict(agent=agent, model=model, input=0, output=0, cache_read=0, cache_write=0,
                cost=0.0, estimated=False, priced=True, tps_out=0, tps_sec=0.0)


def finish_rows(rows):
    for r in rows:
        r["tps"] = r["tps_out"] / r["tps_sec"] if r["tps_sec"] else None
        r["total"] = r["input"] + r["output"] + r["cache_read"] + r["cache_write"]
        if not r["priced"]:
            r["cost"] = None
        for k in ("tps_out", "tps_sec", "priced"):
            del r[k]
    return sorted(rows, key=lambda r: (-(r["cost"] or 0), -r["total"]))

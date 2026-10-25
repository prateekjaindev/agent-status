"""Token maths shared by the collectors: prices, cost, tokens/sec, context windows, usage rows.

Prices are dated data in prices.json. A file at ~/.config/agent-status/prices.json can override models.
"""
import json, re
from pathlib import Path

from .config import USER_CONFIG

PRICES_FILE = Path(__file__).with_name("prices.json")
PRICES_OVERRIDE = USER_CONFIG.parent / "prices.json"


def _read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


def load_prices(override=PRICES_OVERRIDE):
    """The bundled table with the user's per-model overrides merged on top."""
    base, user = _read_json(PRICES_FILE), _read_json(override)
    return dict(as_of=user.get("as_of") or base.get("as_of") or "",
                source=user.get("source") or base.get("source") or "",
                models={**(base.get("models") or {}), **(user.get("models") or {})})


_loaded = load_prices()
PRICES, PRICES_AS_OF, PRICES_SOURCE = _loaded["models"], _loaded["as_of"], _loaded["source"]


def price_for(model, prices=None):
    """The longest matching model prefix, or None when the model has no price."""
    prices = PRICES if prices is None else prices
    best = max((k for k in prices if (model or "").startswith(k)), key=len, default=None)
    return prices.get(best)


def token_cost(model, input_tokens, output_tokens, cache_read=0, cache_write_5m=0, cache_write_1h=0, prices=None):
    """USD for token counts at $/MTok; None for an unknown model. Cache writes default to 1.25x/2x input."""
    p = price_for(model, prices)
    if not p:
        return None
    in_rate = p["in"]
    return (input_tokens * in_rate + output_tokens * p["out"] + cache_read * p["cache_read"]
            + cache_write_5m * p.get("cache_write_5m", in_rate * 1.25)
            + cache_write_1h * p.get("cache_write_1h", in_rate * 2)) / 1e6


def claude_cost(model, u, prices=None):
    """API-equivalent dollars for one Claude response's usage block, or None for unknown models."""
    w1h = (u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens") or 0
    w5m = (u.get("cache_creation_input_tokens") or 0) - w1h
    return token_cost(model, u.get("input_tokens") or 0, u.get("output_tokens") or 0,
                      u.get("cache_read_input_tokens") or 0, w5m, w1h, prices)


def codex_cost(model, d, prices=None):
    """OpenAI counts cached tokens inside input_tokens; Codex's deltas split them."""
    cached = d.get("cached_input_tokens") or 0
    return token_cost(model, max((d.get("input_tokens") or 0) - cached, 0), d.get("output_tokens") or 0,
                      cached, prices=prices)


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

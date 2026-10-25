"""opencode's SQLite database: live session state, tokens, real cost and tok/s. Opened read-only."""
import json, sqlite3
from datetime import datetime

from .config import OPENCODE_DB
from .procs import label
from .usage import new_row, tps

TOK = "coalesce(json_extract(data,'$.tokens.output'),0)+coalesce(json_extract(data,'$.tokens.reasoning'),0)"
DUR = "(json_extract(data,'$.time.completed')-json_extract(data,'$.time.created'))"
COST = "coalesce(json_extract(data,'$.cost'),0)"


def _out(m):
    t = m.get("tokens") or {}
    return (t.get("output") or 0) + (t.get("reasoning") or 0)


class OpenCode:
    def __init__(self, db=OPENCODE_DB):
        self.db = db
        self.msgs = {}      # message id -> (created ms, model, input, output, cache read, cache write, cost, duration ms)
        self.seen = 0       # newest time_updated already read
        self.sessions = {}  # session id -> (time_updated, recent assistant messages, cost, prompts, first ms)

    def _sync(self, con, since):
        """Read only assistant messages created today that changed since the last call."""
        for mid, created, updated, model, i, o, cr, cw, cost, dur in con.execute(f"""
                SELECT id, time_created, time_updated, json_extract(data,'$.model.id'),
                  coalesce(json_extract(data,'$.tokens.input'),0), {TOK},
                  coalesce(json_extract(data,'$.tokens.cache.read'),0), coalesce(json_extract(data,'$.tokens.cache.write'),0),
                  {COST}, {DUR}
                FROM session_message WHERE type='assistant' AND time_created >= ? AND time_updated > ? AND json_valid(data)""",
                                                                          (since * 1000, self.seen)):
            self.msgs[mid] = (created, model or "?", i, o, cr, cw, cost, dur)
            self.seen = max(self.seen, updated)
        self.msgs = {k: v for k, v in self.msgs.items() if v[0] >= since * 1000}  # drop yesterday after midnight

    def usage(self, now):
        rows, hours, last_hour = {}, [[0, 0.0] for _ in range(24)], 0.0
        for created, model, i, o, cr, cw, cost, dur in self.msgs.values():
            r = rows.setdefault(model, new_row("opencode", model))
            r["input"] += i
            r["output"] += o
            r["cache_read"] += cr
            r["cache_write"] += cw
            r["cost"] += cost
            if dur and (speed := tps(o, dur / 1000)):
                r["tps_out"] += o
                r["tps_sec"] += dur / 1000
            h = hours[datetime.fromtimestamp(created / 1000).hour]
            h[0] += i + o + cr + cw
            h[1] += cost
            if now - created / 1000 < 3600:
                last_hour += cost
        return list(rows.values()), hours, last_hour

    def read(self, now, since):
        """Returns (cards, usage rows, hours, cost over the last hour)."""
        if not self.db.exists():
            return [], [], [[0, 0.0] for _ in range(24)], 0.0
        con = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True, timeout=1)
        try:
            self._sync(con, since)
            return (self.cards(con, now), *self.usage(now))
        except sqlite3.Error:
            return [], [], [[0, 0.0] for _ in range(24)], 0.0
        finally:
            con.close()

    def cards(self, con, now):
        cards, live = [], {}
        for sid, directory, title, add, rem, updated in con.execute(
                "SELECT id, directory, title, summary_additions, summary_deletions, time_updated FROM session_v2 "
                "WHERE parent_id IS NULL AND time_updated >= ? ORDER BY time_updated DESC LIMIT 12", ((now - 1800) * 1000,)):
            cached = self.sessions.get(sid)
            if not cached or cached[0] != updated:  # parse messages only when the session changed
                msgs = [json.loads(d) for (d,) in con.execute(
                    "SELECT data FROM session_message WHERE session_id=? AND type='assistant' ORDER BY seq DESC LIMIT 30", (sid,))]
                cached = (updated, msgs, *con.execute(
                    f"SELECT sum(CASE WHEN type='assistant' THEN {COST} END), sum(type='user'), min(time_created) "
                    "FROM session_message WHERE session_id=?", (sid,)).fetchone())
            live[sid] = cached
            _, msgs, cost, prompts, first = cached
            if not msgs:
                continue
            last, t = msgs[0], msgs[0].get("time") or {}
            # finished with "tool-calls" means a tool is running and another response will follow
            if not t.get("completed") or (last.get("finish") != "stop" and now - t["completed"] / 1000 < 600):
                state, since_ts = "working", (t.get("created") or now * 1000) / 1000
            else:
                state, since_ts = "done", t["completed"] / 1000
            speed = next((s for m in msgs if (mt := m.get("time") or {}).get("completed")
                          and (s := tps(_out(m), (mt["completed"] - mt["created"]) / 1000))), None)
            tok = last.get("tokens") or {}
            cache = tok.get("cache") or {}
            cards.append(dict(
                id=f"oc-{sid}", kind="opencode", name=label(directory), cwd=directory, state=state, detail=title or "",
                since=since_ts, started=(first or 0) / 1000, model=(last.get("model") or {}).get("id", ""), tps=speed,
                ctx_tokens=(tok.get("input") or 0) + (cache.get("read") or 0) + (cache.get("write") or 0),
                cost=cost, prompts=prompts, lines=[add or 0, rem or 0]))
        self.sessions = live
        return cards

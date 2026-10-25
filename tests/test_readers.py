"""Claude transcripts, Codex session logs and the opencode database, read from small fixtures."""
import json, sqlite3, tempfile, time, unittest
from pathlib import Path

from agent_status.claude import Transcripts
from agent_status.codex import CodexSessions
from agent_status.opencode import OpenCode


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int(t % 1 * 1000):03d}Z"


class ClaudeTranscripts(unittest.TestCase):
    def test_incremental_dedupe_and_tps(self):
        with tempfile.TemporaryDirectory() as d:
            now = time.time()
            path = Path(d) / "proj" / "s1.jsonl"
            path.parent.mkdir()
            usage = {"input_tokens": 10, "output_tokens": 200, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 0}
            lines = [{"type": "user", "timestamp": iso(now - 10)},
                     # one response split over two lines: count it once, with the last line's usage
                     {"type": "assistant", "timestamp": iso(now - 8), "message": {"id": "m1", "model": "claude-opus-5-5", "usage": dict(usage, output_tokens=50)}},
                     {"type": "assistant", "timestamp": iso(now - 6), "message": {"id": "m1", "model": "claude-opus-5-5", "usage": usage}}]
            path.write_text("".join(json.dumps(l) + "\n" for l in lines) + '{"partial":')  # unfinished last line
            t = Transcripts(d)
            t.scan(now - 3600)
            rows, hours, last_hour = t.usage(now - 3600, now)
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]["output"], rows[0]["cache_read"]), (200, 1000))
            self.assertAlmostEqual(rows[0]["tps_out"] / rows[0]["tps_sec"], 50, places=0)  # 200 tokens over 4s
            session = t.session(str(path))
            self.assertEqual((session["model"], session["ctx_tokens"]), ("claude-opus-5-5", 1010))
            self.assertGreater(last_hour, 0)
            # appending a new line is picked up without re-reading the file
            with open(path, "a") as f:
                f.write("\n" + json.dumps({"type": "assistant", "timestamp": iso(now), "message": {"id": "m2", "model": "claude-opus-5-5", "usage": usage}}) + "\n")
            t.scan(now - 3600)
            self.assertEqual(t.usage(now - 3600, now)[0][0]["output"], 400)


class CodexLogs(unittest.TestCase):
    def test_deltas_context_and_limits(self):
        with tempfile.TemporaryDirectory() as d:
            now = time.time()
            path = Path(d) / "2026/10/25/rollout-x.jsonl"
            path.parent.mkdir(parents=True)

            def tc(t, inp, cached, out):
                return {"timestamp": iso(t), "type": "event_msg", "payload": {"type": "token_count", "info": {
                    "total_token_usage": {"input_tokens": inp, "cached_input_tokens": cached, "output_tokens": out},
                    "last_token_usage": {"input_tokens": 5000}, "model_context_window": 250000},
                    "rate_limits": {"plan_type": "plus", "primary": {"used_percent": 64.0, "window_minutes": 300, "resets_at": now + 600}}}}
            lines = [{"timestamp": iso(now - 20), "type": "turn_context", "payload": {"model": "gpt-6-sol"}},
                     tc(now - 15, 1000, 800, 100), tc(now - 14, 1000, 800, 100), tc(now - 5, 3000, 2000, 300)]
            path.write_text("".join(json.dumps(l) + "\n" for l in lines))
            c = CodexSessions(d)
            c.scan(now - 3600)
            rows, _ = c.usage(now - 3600)
            self.assertEqual((rows[0]["model"], rows[0]["output"], rows[0]["cache_read"]), ("gpt-6-sol", 300, 2000))
            self.assertEqual(c.session(str(path))["ctx"], 0.02)
            limits = c.limits(now)[0]
            self.assertEqual((limits["tier"], limits["limits"][0]["label"], limits["limits"][0]["pct"]), ("Plus", "5-hour", 0.64))
            self.assertEqual(c.limits(now + 3600), [])  # the window has reset: old percentage is stale


class OpenCodeDb(unittest.TestCase):
    def test_usage_and_cards(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "opencode.db"
            now = time.time()
            ms = int(now * 1000)
            con = sqlite3.connect(db)
            con.executescript("""
                CREATE TABLE session_v2 (id TEXT, directory TEXT, title TEXT, parent_id TEXT, summary_additions INT,
                                         summary_deletions INT, time_updated INT);
                CREATE TABLE session_message (id TEXT, session_id TEXT, type TEXT, seq INT, time_created INT,
                                              time_updated INT, data TEXT);""")
            con.execute("INSERT INTO session_v2 VALUES ('s1', '/w/app', 'Fix login', NULL, 12, 3, ?)", (ms,))
            done = {"time": {"created": ms - 4000, "completed": ms - 2000}, "finish": "stop", "cost": 0.05,
                    "model": {"id": "deepseek-v4"}, "tokens": {"input": 100, "output": 80, "reasoning": 20, "cache": {"read": 900, "write": 0}}}
            con.execute("INSERT INTO session_message VALUES ('u1', 's1', 'user', 1, ?, ?, '{}')", (ms - 5000, ms - 5000))
            con.execute("INSERT INTO session_message VALUES ('m1', 's1', 'assistant', 2, ?, ?, ?)", (ms - 4000, ms - 2000, json.dumps(done)))
            con.commit()
            con.close()
            cards, rows, hours, last_hour = OpenCode(db).read(now, now - 3600)
            self.assertEqual((rows[0]["output"], rows[0]["cache_read"], round(rows[0]["cost"], 2)), (100, 900, 0.05))
            self.assertAlmostEqual(rows[0]["tps_out"] / rows[0]["tps_sec"], 50)  # 100 tokens over 2s
            card = cards[0]
            self.assertEqual((card["name"], card["state"], card["prompts"], card["lines"]), ("app", "done", 1, [12, 3]))
            self.assertAlmostEqual(last_hour, 0.05)

    def test_missing_db(self):
        self.assertEqual(OpenCode(Path("/nonexistent/db"))
                         .read(time.time(), 0)[:2], ([], []))


if __name__ == "__main__":
    unittest.main()

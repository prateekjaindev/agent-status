"""Allow/Deny from the dashboard: the hook waits for a tap, the server records it, and every failure means no decision."""
import io, json, tempfile, threading, time, unittest
from contextlib import redirect_stdout
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from agent_status import hooks, server
from agent_status.hooks import ask_text, next_state

BASH = {"hook_event_name": "PermissionRequest", "session_id": "s1", "cwd": "/p", "tool_name": "Bash",
        "tool_input": {"command": "rm -rf build", "description": "clean"}}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        d = Path(self.dir.name)
        self.sessions, self.decisions, self.seen = d / "sessions", d / "decisions", d / "seen"
        self.seen.touch()
        for p in (mock.patch.multiple(hooks, SESSIONS=self.sessions, DECISIONS=self.decisions, SEEN=self.seen, DECIDE_WAIT=5),
                  mock.patch.multiple(server, SESSIONS=self.sessions, DECISIONS=self.decisions, SEEN=self.seen)):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.dir.cleanup)

    def run_hook(self, ev, agent="claude"):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), redirect_stdout(out):
            hooks.hook(agent)
        return out.getvalue()

    def state(self, agent="claude"):
        return json.loads((self.sessions / f"{agent}-s1.json").read_text())

    def tap(self, decision, agent="claude"):
        """Answer the prompt as soon as the hook publishes it, like the tablet does."""
        def go():
            for _ in range(200):
                try:
                    s = self.state(agent)
                    if s.get("ask"):
                        self.result = server.decide(json.dumps({"id": f"{agent}-s1", "ask": s["ask"], "decision": decision}))
                        return
                except (OSError, ValueError):
                    pass
                time.sleep(0.01)
        t = threading.Thread(target=go)
        t.start()
        return t


class Hook(Base):
    def test_allow(self):
        t = self.tap("allow")
        out = json.loads(self.run_hook(BASH))
        t.join()
        self.assertEqual(self.result, (200, "ok"))
        self.assertEqual(out["hookSpecificOutput"], {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}})
        s = self.state()
        self.assertEqual((s["state"], s["detail"]), ("working", "Allowed from dashboard"))
        self.assertNotIn("ask", s)
        self.assertEqual(list(self.decisions.iterdir()), [])

    def test_deny_codex(self):
        t = self.tap("deny", "codex")
        out = json.loads(self.run_hook(BASH, "codex"))
        t.join()
        d = out["hookSpecificOutput"]["decision"]
        self.assertEqual(d["behavior"], "deny")
        self.assertIn("dashboard", d["message"])

    def test_timeout_is_no_decision(self):
        with mock.patch.object(hooks, "DECIDE_WAIT", 0.3):
            started = time.time()
            self.assertEqual(self.run_hook(BASH), "")
        self.assertLess(time.time() - started, 2)
        s = self.state()
        self.assertEqual(s["state"], "waiting")  # the terminal prompt takes over
        self.assertNotIn("ask", s)

    def test_no_dashboard_open_means_no_wait(self):
        self.seen.unlink()
        started = time.time()
        self.assertEqual(self.run_hook(BASH), "")
        self.assertLess(time.time() - started, 1)
        self.assertNotIn("ask", self.state())

    def test_copilot_never_waits(self):
        ev = {"sessionId": "s1", "cwd": "/p", "toolName": "bash", "toolArgs": '{"command": "ls"}'}
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), redirect_stdout(out):
            hooks.hook("copilot", "permissionRequest")
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(self.state("copilot")["state"], "waiting")
        self.assertNotIn("ask", self.state("copilot"))

    def test_garbage_input_is_silent(self):
        with mock.patch("sys.stdin", io.StringIO("not json")), redirect_stdout(io.StringIO()) as out:
            hooks.hook("claude")
        self.assertEqual(out.getvalue(), "")


class State(unittest.TestCase):
    def test_ask_cleared_when_prompt_answered_elsewhere(self):
        s = dict(next_state(None, BASH, 1), ask="a", ask_until=99, ask_text="Bash: ls")
        self.assertEqual(next_state(s, {"hook_event_name": "Notification", "message": "needs your permission"}, 2)["ask"], "a")
        self.assertNotIn("ask", next_state(s, {"hook_event_name": "PostToolUse"}, 3))

    def test_ask_text_shows_the_real_command(self):
        self.assertEqual(ask_text(BASH), "Bash: rm -rf build")
        self.assertEqual(ask_text({"tool_name": "shell", "tool_input": {"command": ["git", "push"]}}), "shell: git push")
        self.assertEqual(ask_text({"tool_name": "Write", "tool_input": {"file_path": "/a/b.py", "content": "x"}}), "Write: /a/b.py")


class Decide(Base):
    def session(self, **kw):
        self.sessions.mkdir(parents=True, exist_ok=True)
        (self.sessions / "claude-s1.json").write_text(json.dumps({"state": "waiting", **kw}))

    def test_rejects(self):
        self.session(ask="tok", ask_until=time.time() + 30)
        req = lambda **kw: server.decide(json.dumps({"id": "claude-s1", "ask": "tok", "decision": "allow", **kw}))
        self.assertEqual(req(ask="other")[0], 409)
        self.assertEqual(req(decision="always")[0], 400)
        self.assertEqual(req(id="../token")[0], 400)
        self.assertEqual(req(id="claude-nope")[0], 409)
        self.assertEqual(server.decide(b"{")[0], 400)
        self.assertEqual(server.decide(b"[]")[0], 400)
        self.assertFalse(self.decisions.exists())
        self.session(ask="tok", ask_until=time.time() - 1)
        self.assertEqual(req()[0], 409)  # the hook already gave up


class Http(Base):
    limits = None

    def setUp(self):
        super().setUp()
        fake = mock.Mock(json=b'{"agents":[]}')
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.handler("KEY", fake, self.limits))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.sessions.mkdir(parents=True)
        (self.sessions / "claude-s1.json").write_text(json.dumps({"ask": "tok", "ask_until": time.time() + 30}))

    def post(self, path="/decide?k=KEY", ctype="application/json", origin=None):
        c = HTTPConnection("127.0.0.1", self.httpd.server_port)
        headers = {"Content-Type": ctype, **({"Origin": origin} if origin else {})}
        c.request("POST", path, json.dumps({"id": "claude-s1", "ask": "tok", "decision": "allow"}), headers)
        return c.getresponse().status

    def test_csrf_and_key(self):
        self.assertEqual(self.post("/decide?k=bad"), 403)
        self.assertEqual(self.post("/decide"), 403)
        self.assertEqual(self.post(ctype="text/plain"), 403)  # what a cross-site <form> can send
        self.assertEqual(self.post(origin="http://evil.example"), 403)
        self.assertFalse(self.decisions.exists())
        self.assertEqual(self.post(origin=f"http://127.0.0.1:{self.httpd.server_port}"), 200)
        self.assertEqual((self.decisions / "tok").read_text(), "allow")

    def test_status_marks_viewer(self):
        self.seen.unlink()
        c = HTTPConnection("127.0.0.1", self.httpd.server_port)
        c.request("GET", "/status?k=KEY")
        self.assertEqual(c.getresponse().status, 200)
        self.assertTrue(self.seen.exists())

    def test_rotation_invalidates_the_old_key_without_a_restart(self):
        key = ["OLD"]
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.handler(lambda: key[0], mock.Mock(json=b'{"agents":[]}')))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)

        def get(k):
            c = HTTPConnection("127.0.0.1", httpd.server_port)
            c.request("GET", f"/status?k={k}")
            return c.getresponse().status

        self.assertEqual(get("OLD"), 200)
        key[0] = "NEW"
        self.assertEqual(get("OLD"), 403)
        self.assertEqual(get("NEW"), 200)


class LimitsHttp(Http):
    def setUp(self):
        self.limits = {"status": server.RateLimiter(2, 60), "decide": server.RateLimiter(5, 60)}
        super().setUp()

    def get(self):
        c = HTTPConnection("127.0.0.1", self.httpd.server_port)
        c.request("GET", "/status?k=KEY")
        return c.getresponse().status

    def test_status_limit(self):
        self.assertEqual([self.get(), self.get()], [200, 200])
        self.assertEqual(self.get(), 429)

    def test_decide_limit(self):
        self.assertEqual([self.post() for _ in range(5)], [200] * 5)
        self.assertEqual(self.post(), 429)


if __name__ == "__main__":
    unittest.main()

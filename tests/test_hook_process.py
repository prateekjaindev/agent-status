"""Run the hook command the agents actually run: fixtures for every installed event, plus hostile input."""
import json, os, re, subprocess, sys, tempfile, time, unittest
from pathlib import Path

from agent_status import agents
from agent_status.hooks import EVENT_MAPS

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures/hooks"
EVENTS = {
    "claude": agents.CLAUDE_EVENTS,
    "codex": agents.CODEX_EVENTS,
    "cursor": agents.CURSOR_EVENTS,
    "gemini": agents.GEMINI_EVENTS,
    "copilot": agents.COPILOT_EVENTS,
}
STATE = {"SessionStart": "idle", "UserPromptSubmit": "working", "Thinking": "working", "PreToolUse": "working",
         "PostToolUse": "working", "PermissionRequest": "waiting", "Notification": "waiting", "Stop": "done"}
BUDGET = 0.3  # seconds; a hook runs inside another agent on every tool call


def canonical(agent, event):
    return EVENT_MAPS[agent].get(event, "") if agent in EVENT_MAPS else event


def run_hook(agent, event, data, state):
    cmd = [sys.executable, "-m", "agent_status", "hook", agent] + ([event] if event else [])
    env = {**os.environ, "AGENT_STATUS_STATE": str(state)}
    started = time.perf_counter()
    proc = subprocess.run(cmd, input=data, capture_output=True, cwd=ROOT, env=env, timeout=10)
    return proc, time.perf_counter() - started


def session_id(payload):
    raw = payload.get("session_id") or payload.get("conversation_id") or payload.get("sessionId") or ""
    return re.sub(r"[^A-Za-z0-9_-]", "", str(raw))[:80]


class InstalledEvents(unittest.TestCase):
    def test_covers_every_hook_agent(self):
        self.assertEqual(set(EVENTS), {a.key for a in agents.AGENTS if a.how == "hooks"})
        self.assertTrue(set(EVENT_MAPS) <= set(EVENTS))

    def test_every_installed_event_has_a_fixture_that_folds(self):
        for agent, events in EVENTS.items():
            for event in events:
                with self.subTest(agent=agent, event=event), tempfile.TemporaryDirectory() as tmp:
                    state = Path(tmp) / "state"
                    payload = json.loads((FIX / agent / f"{event}.json").read_text())
                    sid, canon = session_id(payload), canonical(agent, event)
                    path = state / "sessions" / f"{agent}-{sid}.json"
                    if canon == "SessionEnd":
                        path.parent.mkdir(parents=True)
                        path.write_text(json.dumps({"state": "working", "kind": agent, "updated": time.time()}))

                    proc, elapsed = run_hook(agent, event if agent == "copilot" else None,
                                             json.dumps(payload).encode(), state)
                    if elapsed >= BUDGET:  # CI scheduling can add a one-off delay; retry once before failing
                        with tempfile.TemporaryDirectory() as retry_tmp:
                            _, retry = run_hook(agent, event if agent == "copilot" else None,
                                                json.dumps(payload).encode(), Path(retry_tmp) / "state")
                        elapsed = min(elapsed, retry)

                    self.assertEqual(proc.returncode, 0, proc.stderr.decode())
                    self.assertNotIn(b"Traceback", proc.stdout + proc.stderr)
                    self.assertEqual(proc.stdout.decode(), "{}\n" if agent == "gemini" else "")
                    self.assertLess(elapsed, BUDGET, f"{agent} {event} took {elapsed:.2f}s")
                    if canon == "SessionEnd":
                        self.assertFalse(path.exists(), "SessionEnd must remove the session")
                        continue
                    s = json.loads(path.read_text())
                    self.assertEqual((s["kind"], s["state"]), (agent, STATE[canon]),
                                     f"{agent} {event}: {s['state']} != {STATE[canon]}")
                    if canon == "UserPromptSubmit":
                        self.assertEqual(s["prompts"], 1)
                    if canon == "PreToolUse":
                        self.assertEqual(s["tools"], 1)


class Garbage(unittest.TestCase):
    CASES = [
        ("empty", b""),
        ("invalid-json", b"{not json"),
        ("binary", b"\x00\xff\xfe\x01\x02"),
        ("huge", b'{"session_id":"big","hook_event_name":"UserPromptSubmit","prompt":"' + b"a" * (5 * 1024 * 1024) + b'"}'),
        ("traversal", b'{"session_id":"../../escape","hook_event_name":"UserPromptSubmit"}'),
    ]

    def test_hook_always_exits_zero_and_writes_only_in_state(self):
        for name, data in self.CASES:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                root, state = Path(tmp), Path(tmp) / "state"
                proc, _ = run_hook("claude", None, data, state)
                self.assertEqual(proc.returncode, 0, proc.stderr.decode())
                self.assertNotIn(b"Traceback", proc.stdout + proc.stderr)
                written = [p for p in root.rglob("*") if p.is_file()]
                self.assertTrue(all(p.is_relative_to(state) for p in written), f"{name} escaped {state}: {written}")
                if name == "traversal":
                    self.assertEqual([p.name for p in written], ["claude-escape.json"])


class DoctorCommand(unittest.TestCase):
    def test_reports_when_nothing_is_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "HOME": tmp, "XDG_CONFIG_HOME": str(Path(tmp) / "config"),
                   "AGENT_STATUS_STATE": str(Path(tmp) / "state")}
            proc = subprocess.run([sys.executable, "-m", "agent_status", "doctor"],
                                  capture_output=True, cwd=ROOT, env=env, timeout=10)
            self.assertEqual(proc.returncode, 1)
            self.assertIn(b"not installed yet", proc.stdout)


if __name__ == "__main__":
    unittest.main()

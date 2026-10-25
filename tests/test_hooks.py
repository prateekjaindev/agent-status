import unittest

from agent_status.hooks import next_state, normalize, tool_detail


def ev(name, **kw):
    return dict(hook_event_name=name, cwd="/p", **kw)


class ClaudeFlow(unittest.TestCase):
    def test_full_turn(self):
        s = next_state(None, ev("SessionStart", source="startup"), 1)
        self.assertEqual(s["state"], "idle")
        s = next_state(s, ev("UserPromptSubmit"), 2)
        self.assertEqual((s["state"], s["since"], s["prompts"]), ("working", 2, 1))
        s = next_state(s, ev("PreToolUse", tool_name="Bash", tool_input={"description": "run tests"}), 3)
        self.assertEqual((s["detail"], s["since"], s["tools"]), ("Bash: run tests", 2, 1))
        s = next_state(s, ev("Notification", message="Claude needs your permission to use Bash"), 4)
        self.assertEqual(s["state"], "waiting")
        s = next_state(s, ev("PostToolUse"), 5)
        self.assertEqual((s["state"], s["since"]), ("working", 5))
        s = next_state(s, ev("SessionStart", source="compact"), 6)
        self.assertEqual(s["state"], "working")  # auto-compaction mid-turn must not reset state
        s = next_state(s, ev("Stop"), 7)
        self.assertEqual(s["state"], "done")
        s = next_state(s, ev("Notification", message="Claude is waiting for your input"), 8)
        self.assertEqual(s["state"], "done")  # idle reminders are not permission prompts
        self.assertIsNone(next_state(s, ev("SessionEnd"), 9))

    def test_permission_request_event(self):  # Codex and Copilot
        s = next_state(None, ev("PermissionRequest", tool_name="shell", tool_input={"command": ["rm", "-rf", "build"]}), 1)
        self.assertEqual(s["state"], "waiting")
        self.assertIn("rm -rf build", s["detail"])


class Normalize(unittest.TestCase):
    def test_cursor(self):
        c = normalize({"hook_event_name": "postToolUse", "conversation_id": "abc", "workspace_roots": ["/w/repo"],
                       "tool_name": "Shell", "tool_input": {"command": "ls"}, "transcript_path": "/x"}, "cursor")
        s = next_state(None, c, 1)
        self.assertEqual((c["session_id"], s["cwd"], s["detail"]), ("abc", "/w/repo", "Shell: ls"))
        self.assertNotIn("transcript_path", c)
        self.assertEqual(normalize({"hook_event_name": "preToolUse"}, "cursor")["hook_event_name"], "")

    def test_gemini(self):
        self.assertEqual(normalize({"hook_event_name": "BeforeAgent"}, "gemini")["hook_event_name"], "UserPromptSubmit")
        self.assertEqual(normalize({"hook_event_name": "AfterAgent"}, "gemini")["hook_event_name"], "Stop")
        n = normalize({"hook_event_name": "Notification", "notification_type": "ToolPermission", "message": "Allow?"}, "gemini")
        self.assertEqual(next_state(None, n, 1)["state"], "waiting")

    def test_copilot_event_comes_from_argument(self):
        c = normalize({"sessionId": "s1", "cwd": "/r", "toolName": "bash", "toolArgs": '{"command": "npm test"}'},
                      "copilot", "preToolUse")
        self.assertEqual((c["hook_event_name"], c["session_id"]), ("PreToolUse", "s1"))
        self.assertEqual(next_state(None, c, 1)["detail"], "bash: npm test")
        self.assertEqual(normalize({}, "copilot", "agentStop")["hook_event_name"], "Stop")

    def test_claude_and_codex_pass_through(self):
        e = {"hook_event_name": "Stop", "session_id": "x", "transcript_path": "/t.jsonl"}
        self.assertEqual(normalize(e, "claude"), e)
        self.assertEqual(normalize(e, "codex")["transcript_path"], "/t.jsonl")

    def test_tool_detail(self):
        self.assertEqual(tool_detail({"tool_name": "mcp__x__search", "tool_input": {"file_path": "/a/b.py"}}), "search: b.py")
        self.assertEqual(tool_detail({"tool_name": "Read", "tool_input": "not a dict"}), "Read: not a dict")


if __name__ == "__main__":
    unittest.main()

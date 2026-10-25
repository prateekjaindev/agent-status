"""Hooks are added once, leave the user's own hooks alone, and come out cleanly."""
import json, tempfile, unittest
from pathlib import Path

from agent_status.agents import AGENTS, flat, nested, own_file, ours

CMD = "/home/u/.local/bin/agent-status"


class Formats(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.d = Path(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def test_nested_keeps_user_hooks(self):
        path = self.d / "settings.json"
        user = {"theme": "dark", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "notify-send done"}]}]}}
        path.write_text(json.dumps(user))
        install, uninstall = nested(path, ["Stop", "PreToolUse"], {"timeout": 5})
        install(f"{CMD} hook claude")
        install(f"{CMD} hook claude")  # idempotent
        cfg = json.loads(path.read_text())
        self.assertEqual(len(cfg["hooks"]["Stop"]), 2)
        self.assertEqual(len(cfg["hooks"]["PreToolUse"]), 1)
        self.assertTrue(path.with_name("settings.json.bak-agent-status").exists())
        uninstall()
        self.assertEqual(json.loads(path.read_text()), user)

    def test_nested_with_matcher(self):  # Gemini CLI
        path = self.d / "gemini.json"
        install, _ = nested(path, ["BeforeTool"], {"name": "agent-status", "timeout": 5000}, matcher="*")
        install(f"{CMD} hook gemini")
        group = json.loads(path.read_text())["hooks"]["BeforeTool"][0]
        self.assertEqual(group["matcher"], "*")
        self.assertEqual(group["hooks"][0]["timeout"], 5000)

    def test_uninstall_leaves_untouched_files_alone(self):
        path = self.d / "hooks.json"
        path.write_text('{"hooks":{}}')  # compact formatting the user chose
        nested(path, ["Stop"], {})[1]()
        self.assertEqual(path.read_text(), '{"hooks":{}}')

    def test_flat(self):  # Cursor
        path = self.d / "hooks.json"
        install, uninstall = flat(path, ["stop", "sessionStart"])
        install(f"{CMD} hook cursor")
        cfg = json.loads(path.read_text())
        self.assertEqual((cfg["version"], cfg["hooks"]["stop"]), (1, [{"command": f"{CMD} hook cursor"}]))
        uninstall()
        self.assertEqual(json.loads(path.read_text()), {"version": 1, "hooks": {}})

    def test_own_file_passes_event_name(self):  # Copilot
        path = self.d / "hooks" / "agent-status.json"
        install, uninstall = own_file(path, ["preToolUse"])
        install(f"{CMD} hook copilot")
        entry = json.loads(path.read_text())["hooks"]["preToolUse"][0]
        self.assertEqual(entry["bash"], f"{CMD} hook copilot preToolUse")
        uninstall()
        self.assertFalse(path.exists())

    def test_ours(self):
        self.assertTrue(ours(f"{CMD} hook"))
        self.assertTrue(ours("python3 -m agent_status hook codex"))
        self.assertFalse(ours("/home/u/.claude/hooks/boost-hook-claude.sh"))

    def test_registry_keys_unique(self):
        keys = [a.key for a in AGENTS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(a.hook_files for a in AGENTS if a.how == "hooks"))


if __name__ == "__main__":
    unittest.main()

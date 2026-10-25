"""Hooks are added once, leave the user's own hooks alone, and come out cleanly."""
import json, tempfile, unittest
from pathlib import Path
from unittest import mock

import agent_status.install as install_mod
from agent_status.agents import AGENTS, Agent, flat, nested, own_file, ours
from agent_status.install import doctor

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
        install, uninstall, _ = nested(path, ["Stop", "PreToolUse"], {"timeout": 5})
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
        install, _, _ = nested(path, ["BeforeTool"], {"name": "agent-status", "timeout": 5000}, matcher="*")
        install(f"{CMD} hook gemini")
        group = json.loads(path.read_text())["hooks"]["BeforeTool"][0]
        self.assertEqual(group["matcher"], "*")
        self.assertEqual(group["hooks"][0]["timeout"], 5000)

    def test_nested_per_event_and_refresh(self):
        path = self.d / "settings.json"
        path.write_text(json.dumps({"hooks": {"PermissionRequest": [{"hooks": [
            {"type": "command", "command": "/old/agent-status hook", "timeout": 5}]}]}}))
        install, _, _ = nested(path, ["PermissionRequest", "Stop"], {"timeout": 5}, per_event={"PermissionRequest": {"timeout": 90}})
        install(f"{CMD} hook claude")
        hooks = json.loads(path.read_text())["hooks"]
        self.assertEqual(hooks["PermissionRequest"], [{"hooks": [{"type": "command", "command": f"{CMD} hook claude", "timeout": 90}]}])
        self.assertEqual(hooks["Stop"][0]["hooks"][0]["timeout"], 5)

    def test_uninstall_leaves_untouched_files_alone(self):
        path = self.d / "hooks.json"
        path.write_text('{"hooks":{}}')  # compact formatting the user chose
        nested(path, ["Stop"], {})[1]()
        self.assertEqual(path.read_text(), '{"hooks":{}}')

    def test_flat(self):  # Cursor
        path = self.d / "hooks.json"
        install, uninstall, _ = flat(path, ["stop", "sessionStart"])
        install(f"{CMD} hook cursor")
        cfg = json.loads(path.read_text())
        self.assertEqual((cfg["version"], cfg["hooks"]["stop"]), (1, [{"command": f"{CMD} hook cursor"}]))
        uninstall()
        self.assertEqual(json.loads(path.read_text()), {"version": 1, "hooks": {}})

    def test_own_file_passes_event_name(self):  # Copilot
        path = self.d / "hooks" / "agent-status.json"
        install, uninstall, _ = own_file(path, ["preToolUse"])
        install(f"{CMD} hook copilot")
        entry = json.loads(path.read_text())["hooks"]["preToolUse"][0]
        self.assertEqual(entry["bash"], f"{CMD} hook copilot preToolUse")
        uninstall()
        self.assertFalse(path.exists())

    def test_stale_nested(self):
        path = self.d / "settings.json"
        install, _, stale = nested(path, ["Stop", "PermissionRequest"], {"timeout": 5},
                                   per_event={"PermissionRequest": {"timeout": 90}})
        cmd = f"{CMD} hook claude"
        self.assertEqual(stale(cmd), ["Stop", "PermissionRequest"])
        install(cmd)
        self.assertEqual(stale(cmd), [])
        cfg = json.loads(path.read_text())
        cfg["hooks"]["PermissionRequest"][0]["hooks"][0]["timeout"] = 5  # written by an older version
        path.write_text(json.dumps(cfg))
        self.assertEqual(stale(cmd), ["PermissionRequest"])
        self.assertEqual(stale("/new/agent-status hook claude"), ["Stop", "PermissionRequest"])

    def test_stale_flat_updates_the_command(self):
        path = self.d / "hooks.json"
        install, _, stale = flat(path, ["stop"])
        self.assertEqual(stale(f"{CMD} hook cursor"), ["stop"])
        install(f"{CMD} hook cursor")
        self.assertEqual(stale(f"{CMD} hook cursor"), [])
        install("/new/agent-status hook cursor")
        self.assertEqual(json.loads(path.read_text())["hooks"]["stop"], [{"command": "/new/agent-status hook cursor"}])

    def test_stale_own_file(self):
        path = self.d / "hooks" / "agent-status.json"
        install, _, stale = own_file(path, ["preToolUse", "stop"])
        self.assertEqual(stale(f"{CMD} hook copilot"), ["preToolUse", "stop"])
        install(f"{CMD} hook copilot")
        self.assertEqual(stale(f"{CMD} hook copilot"), [])
        self.assertEqual(stale("/new/agent-status hook copilot"), ["preToolUse", "stop"])

    def test_ours(self):
        self.assertTrue(ours(f"{CMD} hook"))
        self.assertTrue(ours("python3 -m agent_status hook codex"))
        self.assertFalse(ours("/home/u/.claude/hooks/boost-hook-claude.sh"))

    def test_registry_keys_unique(self):
        keys = [a.key for a in AGENTS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(a.hook_files for a in AGENTS if a.how == "hooks"))


class Doctor(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.d = Path(self.dir.name)
        self.agent = Agent("fake", "Fake CLI", "hooks",
                           hook_files=nested(self.d / "settings.json", ["Stop", "SessionEnd"], {"timeout": 5}))

    def tearDown(self):
        self.dir.cleanup()

    def test_reports_stale_then_up_to_date(self):
        lines = []
        self.assertEqual(doctor(agents=[self.agent], selected={"fake"}, exe=CMD, out=lines.append), 1)
        self.assertTrue(any("stale hooks: Stop, SessionEnd" in line for line in lines))
        self.assertIn(f"  run: {CMD} install --agents fake", lines)
        self.agent.install(CMD)
        lines.clear()
        self.assertEqual(doctor(agents=[self.agent], selected={"fake"}, exe=CMD, out=lines.append), 0)
        self.assertTrue(any("hooks up to date" in line for line in lines))

    def test_broken_config_is_reported_not_raised(self):
        (self.d / "settings.json").write_text("{not json")
        lines = []
        self.assertEqual(doctor(agents=[self.agent], selected={"fake"}, exe=CMD, out=lines.append), 1)
        self.assertTrue(any("not valid JSON" in line for line in lines))

    def test_not_installed(self):
        lines = []
        with mock.patch.object(install_mod, "enabled_agents", return_value=None):
            self.assertEqual(doctor(agents=[self.agent], exe=CMD, out=lines.append), 1)
        self.assertTrue(any(f"run: {CMD} install" in line for line in lines))


if __name__ == "__main__":
    unittest.main()

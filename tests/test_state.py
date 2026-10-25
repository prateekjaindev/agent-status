"""Stale hook state: temp files, unconsumed taps and sessions that never got a pid are cleaned; fresh ones stay."""
import json, os, tempfile, unittest
from pathlib import Path

from agent_status.collect import DECISION_STALE, STALE, TMP_STALE, clean_state

NOW = 1_700_000_000


def make(path, age, text="{}"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    os.utime(path, (NOW - age, NOW - age))


class CleanState(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.state = Path(self.dir.name) / "state"
        self.sessions = self.state / "sessions"
        self.decisions = self.state / "decisions"

    def tearDown(self):
        self.dir.cleanup()

    def clean(self):
        return clean_state(now=NOW, state=self.state, sessions=self.sessions, decisions=self.decisions)

    def test_removes_only_stale_files(self):
        make(self.state / "old.tmp", TMP_STALE + 1)
        make(self.state / "fresh.tmp", TMP_STALE - 1)
        make(self.sessions / "old.tmp", TMP_STALE + 1)
        make(self.decisions / "old.tmp", TMP_STALE + 1)
        make(self.decisions / "old-tap", DECISION_STALE + 1)
        make(self.decisions / "fresh-tap", DECISION_STALE - 1)
        make(self.sessions / "no-pid.json", STALE + 1, json.dumps({"state": "idle", "updated": NOW}))
        make(self.sessions / "fresh-no-pid.json", STALE - 1, json.dumps({"state": "idle"}))
        make(self.sessions / "with-pid.json", STALE + 1, json.dumps({"state": "working", "pid": 123}))
        make(self.sessions / "broken.json", STALE + 1, "{not json")

        self.assertEqual(self.clean(), dict(tmp=3, decisions=1, sessions=2))
        self.assertFalse((self.state / "old.tmp").exists())
        self.assertFalse((self.sessions / "old.tmp").exists())
        self.assertFalse((self.decisions / "old.tmp").exists())
        self.assertFalse((self.decisions / "old-tap").exists())
        self.assertFalse((self.sessions / "no-pid.json").exists())
        self.assertFalse((self.sessions / "broken.json").exists())
        self.assertTrue((self.state / "fresh.tmp").exists())
        self.assertTrue((self.decisions / "fresh-tap").exists())
        self.assertTrue((self.sessions / "fresh-no-pid.json").exists())
        self.assertTrue((self.sessions / "with-pid.json").exists())

    def test_missing_directories_are_fine(self):
        self.assertEqual(self.clean(), dict(tmp=0, decisions=0, sessions=0))


if __name__ == "__main__":
    unittest.main()

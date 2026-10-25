"""The /status JSON contract: a fixture-built snapshot must match docs/api.md exactly."""
import json, tempfile, time, unittest
from pathlib import Path
from unittest import mock

from agent_status import collect, demo
from agent_status.collect import Collector
from agent_status.usage import new_row


def number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def integer(v):
    return type(v) is int


def text(v):
    return isinstance(v, str)


def boolean(v):
    return type(v) is bool


class Opt:
    """A key that only some cards carry."""

    def __init__(self, spec):
        self.spec = spec


class Nullable:
    def __init__(self, spec):
        self.spec = spec


class Map:
    """An object with arbitrary string keys and one value shape."""

    def __init__(self, spec):
        self.spec = spec


GIT = {"branch": Nullable(text), "files": integer, "add": integer, "rem": integer}
CARD = {
    "id": text, "kind": text, "name": text, "state": text, "detail": text, "since": number,
    "git": Nullable(GIT),
    "started": Opt(Nullable(number)), "model": Opt(text), "prompts": Opt(Nullable(integer)),
    "tools": Opt(Nullable(integer)),
    "tps": Opt(Nullable(number)), "ctx": Opt(Nullable(number)), "ctx_tokens": Opt(Nullable(integer)),
    "cost": Opt(Nullable(number)), "estimated": Opt(boolean),
    "ask": Opt(text), "ask_until": Opt(number), "ask_text": Opt(text),
    "lines": Opt([integer, integer]), "guessed": Opt(boolean),
}
LIMIT = {"name": text, "tier": Opt(text), "updated": Opt(text),
         "limits": [{"label": text, "pct": number, "resets": Opt(Nullable(text))}]}
ROW = {"agent": text, "model": text, "input": integer, "output": integer, "cache_read": integer,
       "cache_write": integer, "cost": Nullable(number), "estimated": boolean, "tps": Nullable(number),
       "total": integer}
STATUS = {
    "schema": integer, "now": number, "interval": number, "prices_as_of": text,
    "agents": [CARD],
    "limits": [LIMIT],
    "week": [{"date": text, "agents": Map(integer)}],
    "today": {"cost": number, "tokens": integer, "output": integer, "burn": number,
              "hours": [[number, number]], "models": [ROW]},
}


def check(value, spec, path):
    if isinstance(spec, Opt):
        check(value, spec.spec, path)
    elif isinstance(spec, Nullable):
        if value is not None:
            check(value, spec.spec, path)
    elif isinstance(spec, Map):
        assert isinstance(value, dict), f"{path}: expected an object, got {value!r}"
        for k, v in value.items():
            assert isinstance(k, str), f"{path}: non-string key {k!r}"
            check(v, spec.spec, f"{path}.{k}")
    elif isinstance(spec, dict):
        assert isinstance(value, dict), f"{path}: expected an object, got {value!r}"
        required = {k for k, v in spec.items() if not isinstance(v, Opt)}
        assert not set(value) - set(spec), f"{path}: undocumented keys {sorted(set(value) - set(spec))}"
        assert not required - set(value), f"{path}: missing keys {sorted(required - set(value))}"
        for k, v in value.items():
            check(v, spec[k], f"{path}.{k}")
    elif isinstance(spec, list):
        assert isinstance(value, list), f"{path}: expected an array, got {value!r}"
        if len(spec) == 1:
            for i, v in enumerate(value):
                check(v, spec[0], f"{path}[{i}]")
        else:
            assert len(value) == len(spec), f"{path}: expected {len(spec)} items, got {len(value)}"
            for i, (v, s) in enumerate(zip(value, spec)):
                check(v, s, f"{path}[{i}]")
    else:
        assert spec(value), f"{path}: {value!r} has the wrong type"


class FakeProcs:
    def __init__(self):
        self.procs = {4242: None, 4243: None}

    def refresh(self, now):
        pass

    def tree(self, pid):
        return 12.5, 4096

    def scanned(self, now, skip, enabled):
        return [dict(id="pid-9001", kind="Aider", name="app", cwd="", state="working", detail="busy",
                     since=now - 60, guessed=True)]


class FakeClaude:
    def scan(self, since):
        pass

    def session(self, path):
        return dict(model="claude-opus-5-5", tps=50.0, ctx=0.01, ctx_tokens=1010, cost=0.02, estimated=True)

    def usage(self, since, now):
        row = new_row("Claude Code", "claude-opus-5-5")
        row.update(input=10, output=200, cache_read=1000, cost=0.02, estimated=True, tps_out=200, tps_sec=4)
        return [row], [[1200, 0.02] for _ in range(24)], 0.5


class FakeCodex:
    def scan(self, since):
        pass

    def session(self, path):
        return dict(model="gpt-6-sol", ctx_tokens=5000, ctx=0.02)

    def usage(self, since, now):
        row = new_row("Codex", "gpt-6-sol")
        row.update(input=100, output=20, cache_read=50, cost=0.01, estimated=True)
        return [row], [[170, 0.01] for _ in range(24)], 0.01

    def limits(self, now):
        return [dict(name="Codex", tier="Plus",
                     limits=[dict(label="5-hour", pct=0.64, resets="2026-10-25T12:00:00+00:00")])]


class FakeOpenCode:
    def read(self, now, since):
        row = new_row("opencode", "deepseek-v4")
        row.update(input=100, output=80, cache_read=900, cost=0.05, tps_out=100, tps_sec=2)
        card = dict(id="oc-s1", kind="opencode", name="app", cwd="/Users/me/src/agent-status", state="done",
                    detail="Fix login", since=now - 100, started=now - 500, model="deepseek-v4", tps=50.0,
                    ctx_tokens=1000, cost=0.05, prompts=1, lines=[12, 3])
        return [card], [row], [[100, 0.05] for _ in range(24)], 0.05


class Contract(unittest.TestCase):
    def snapshot(self):
        now = time.time()
        with tempfile.TemporaryDirectory() as d:
            sessions = Path(d) / "sessions"
            sessions.mkdir()
            common = dict(cwd="/Users/me/src/agent-status", since=now - 30, started=now - 300, updated=now,
                          prompts=2, tools=3, pid=4242)
            (sessions / "claude-1.json").write_text(json.dumps({
                **common, "kind": "claude", "state": "waiting", "detail": "Approve Bash", "model": "claude-opus-5-5",
                "ask": "ask-token", "ask_until": now + 60, "ask_text": "Bash: rm -rf build",
                "transcript_path": "/tmp/claude.jsonl"}))
            (sessions / "codex-1.json").write_text(json.dumps({
                **common, "pid": 4243, "kind": "codex", "state": "working", "detail": "thinking…",
                "model": "gpt-6-sol", "transcript_path": "/tmp/codex.jsonl"}))
            om_row = new_row("Omarchy Agent", "some-model")
            om_row.update(output=500, priced=False)
            with mock.patch.object(collect, "SESSIONS", sessions), \
                    mock.patch.object(collect, "enabled_agents", return_value=None), \
                    mock.patch.object(collect, "git_info",
                                      side_effect=lambda cwd, now: dict(branch="t06-contract", files=2, add=10, rem=3)
                                      if cwd else None), \
                    mock.patch.object(collect.omarchy, "read", return_value=(
                            [dict(name="Claude", tier="Max", updated="2026-10-25T10:00:00Z",
                                  limits=[dict(label="5-hour", pct=0.4, resets=None)])],
                            [dict(date="2026-10-24", agents={"Claude": 1234})], [om_row])):
                c = Collector()
                c.procs = FakeProcs()
                c.claude, c.codex, c.oc = FakeClaude(), FakeCodex(), FakeOpenCode()
                return json.loads(json.dumps(c.tick()))

    def test_snapshot_matches_the_documented_contract(self):
        snap = self.snapshot()
        self.assertEqual(snap["schema"], 2)
        self.assertEqual(len(snap["today"]["hours"]), 24)
        check(snap, STATUS, "status")

    def test_demo_snapshot_matches_the_contract(self):
        snap = json.loads(json.dumps(demo.snapshot(now=1_800_000_000)))
        self.assertEqual(snap["schema"], 2)
        self.assertEqual(len(snap["agents"]), 5)
        self.assertEqual(len(snap["today"]["hours"]), 24)
        check(snap, STATUS, "demo")

    def test_demo_moves_between_requests(self):
        a = demo.snapshot(now=1_800_000_000)
        b = demo.snapshot(now=1_800_000_009)
        self.assertNotEqual(a["agents"][0]["state"], b["agents"][0]["state"])

    def test_checker_catches_undocumented_and_missing_keys(self):
        snap = self.snapshot()
        snap["today"]["new_field"] = 1
        with self.assertRaises(AssertionError):
            check(snap, STATUS, "status")
        snap = self.snapshot()
        del snap["agents"][0]["id"]
        with self.assertRaises(AssertionError):
            check(snap, STATUS, "status")


if __name__ == "__main__":
    unittest.main()

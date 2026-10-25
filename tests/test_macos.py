"""macOS process parsing, the LaunchAgent, and (on a Mac) the live process table."""
import os, plistlib, sys, time, unittest
from pathlib import Path

from agent_status import install, procs

FIX = Path(__file__).parent / "fixtures/macos"


def fixture(name):
    return (FIX / name).read_text()


class Parsers(unittest.TestCase):
    def test_ps(self):
        table = procs.parse_ps(fixture("ps.txt"))
        self.assertEqual(len(table), 8)
        comm, ppid, ticks, argv = table[4400]
        self.assertEqual((comm, ppid), ("claude", 4321))
        self.assertEqual(ticks, round(185.4 * procs.CLK_TCK))
        self.assertEqual(procs.agent_key(comm, argv), "claude")  # Claude Code renames its process to `claude`
        self.assertEqual(procs.agent_key(*[table[4410][i] for i in (0, 3)]), "gemini")  # node + package path
        self.assertEqual(procs.agent_key(*[table[4500][i] for i in (0, 3)]), "codex")
        self.assertEqual(table[4500][2], round((86400 + 2 * 3600 + 3 * 60 + 4.5) * procs.CLK_TCK))
        self.assertEqual(table[4600][0], "(zombie)")

    def test_cputime(self):
        self.assertEqual(procs.cputime("0:00.21"), 0.21)
        self.assertEqual(procs.cputime("12:34.56"), 754.56)

    def test_lsof_cwd(self):
        self.assertEqual(procs.lsof_cwd(fixture("lsof.txt")), "/Users/me/src/agent-status")
        self.assertEqual(procs.lsof_cwd(""), "")


class LaunchAgent(unittest.TestCase):
    def test_plist(self):
        job = plistlib.loads(plistlib.dumps(install.launch_agent()))
        self.assertEqual(job["Label"], install.LABEL)
        self.assertEqual(job["ProgramArguments"][-1], "serve")
        self.assertTrue(job["RunAtLoad"])
        self.assertEqual(job["KeepAlive"], {"SuccessfulExit": False})
        self.assertEqual(install.PLIST.name, f"{install.LABEL}.plist")


@unittest.skipUnless(sys.platform == "darwin", "macOS only")
class LiveMac(unittest.TestCase):
    def test_procs(self):
        t = procs.ProcTable()
        t.refresh(time.time())
        self.assertIn(os.getpid(), t.procs)
        self.assertEqual(t.procs[os.getpid()][1], os.getppid())
        self.assertEqual(t.cwd(os.getpid()), os.getcwd())


if __name__ == "__main__":
    unittest.main()

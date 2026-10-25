"""macOS backends: command-output parsers on fixtures, the LaunchAgent, and (on a Mac) the live probes."""
import os, plistlib, sys, time, unittest
from pathlib import Path

from agent_status import install, procs, system

FIX = Path(__file__).parent / "fixtures/macos"


def fixture(name):
    return (FIX / name).read_text()


class Parsers(unittest.TestCase):
    def test_ps(self):
        table = procs.parse_ps(fixture("ps.txt"))
        self.assertEqual(len(table), 8)
        comm, ppid, ticks, rss, argv = table[4400]
        self.assertEqual((comm, ppid, rss), ("claude", 4321, 412880 * 1024))
        self.assertEqual(ticks, round(185.4 * procs.CLK_TCK))
        self.assertEqual(procs.agent_key(comm, argv), "claude")  # Claude Code renames its process to `claude`
        self.assertEqual(procs.agent_key(*[table[4410][i] for i in (0, 4)]), "gemini")  # node + package path
        self.assertEqual(procs.agent_key(*[table[4500][i] for i in (0, 4)]), "codex")
        self.assertEqual(table[4500][2], round((86400 + 2 * 3600 + 3 * 60 + 4.5) * procs.CLK_TCK))
        self.assertEqual(table[4600][0], "(zombie)")

    def test_cputime(self):
        self.assertEqual(procs.cputime("0:00.21"), 0.21)
        self.assertEqual(procs.cputime("12:34.56"), 754.56)

    def test_lsof_cwd(self):
        self.assertEqual(procs.lsof_cwd(fixture("lsof.txt")), "/Users/me/src/agent-status")
        self.assertEqual(procs.lsof_cwd(""), "")

    def test_memory(self):
        memsize, swap = fixture("sysctl_mem.txt").splitlines()
        m = system.mac_memory(fixture("vm_stat.txt"), memsize, swap)
        page = 16384
        self.assertEqual(m["total"], 16 * 2**30)
        self.assertEqual(m["used"], (340000 - 10000 + 150000 + 50000) * page)
        self.assertAlmostEqual(m["pct"], 100 * m["used"] / m["total"])
        self.assertEqual((m["swap_total"], m["swap_used"]), (2048 * 2**20, int(512.5 * 2**20)))

    def test_net_counts_each_real_interface_once(self):
        self.assertEqual(system.mac_net(fixture("netstat.txt")), (6000000000 + 20000, 400000000 + 30000))

    def test_batteries(self):
        self.assertEqual(system.mac_batteries(fixture("pmset.txt")), [dict(name="Battery", pct=76.0, status="discharging")])
        self.assertEqual(system.mac_batteries("Now drawing from 'AC Power'\n"), [])  # desktop Mac

    def test_uptime(self):
        self.assertAlmostEqual(system.mac_uptime(fixture("boottime.txt")), time.time() - 1761300000, delta=5)

    def test_bad_output_falls_back(self):
        self.assertEqual(system.safe(lambda: system.mac_memory("", "0", ""), "default"), "default")


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
    def test_system(self):
        s = system.System()
        s.sample(time.time())
        time.sleep(0.5)
        snap = s.sample(time.time())
        self.assertEqual(len(snap["cpu"]["cores"]), os.cpu_count())
        self.assertGreater(snap["mem"]["total"], 0)
        self.assertGreater(snap["uptime"], 0)

    def test_procs(self):
        t = procs.ProcTable()
        t.refresh(time.time())
        self.assertIn(os.getpid(), t.procs)
        self.assertEqual(t.procs[os.getpid()][1], os.getppid())
        self.assertEqual(t.cwd(os.getpid()), os.getcwd())


if __name__ == "__main__":
    unittest.main()

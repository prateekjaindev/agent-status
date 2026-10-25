"""Process table: finds agent processes and measures CPU/RAM per process tree, from /proc."""
import os
from collections import defaultdict
from pathlib import Path

from .agents import AGENTS, BY_KEY

CLK_TCK = os.sysconf("SC_CLK_TCK")
PAGE = os.sysconf("SC_PAGE_SIZE")
INTERPRETERS = {"node", "bun", "deno", "python", "python3"}
NAMES = {p: a.key for a in AGENTS for p in a.procs if "/" not in p}
PACKAGES = {p: a.key for a in AGENTS for p in a.procs if "/" in p}  # npm-installed agents run as `node .../pkg/...`


def read_stat(pid):
    stat = Path(f"/proc/{pid}/stat").read_text()
    return stat[stat.index("(") + 1:stat.rindex(")")], stat[stat.rindex(")") + 2:].split()


def read_argv(pid):
    return [a.decode(errors="replace") for a in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")]


def agent_key(comm, argv):
    if comm in NAMES:
        return NAMES[comm]
    if comm in INTERPRETERS and argv and len(argv) > 1:
        script = argv[1]
        if Path(script).name in NAMES:
            return NAMES[Path(script).name]
        return next((key for pkg, key in PACKAGES.items() if f"/{pkg}/" in script), None)
    return None


def label(cwd):
    return "~" if cwd == str(Path.home()) else (Path(cwd).name or cwd or "?")


class ProcTable:
    def __init__(self):
        self.procs = {}      # pid -> (comm, ppid, ticks, rss bytes, argv or None)
        self.cpu = {}        # pid -> % of one core since last refresh
        self.children = defaultdict(list)
        self._prev = {}      # pid -> (ticks, time)
        self._since = {}     # pid -> (state, since) for process-detected agents

    def refresh(self, now):
        procs = {}
        try:
            entries = list(os.scandir("/proc"))
        except OSError:
            entries = []  # not Linux: no process data
        for d in entries:
            if not d.name.isdigit():
                continue
            try:
                comm, f = read_stat(d.name)
                argv = read_argv(d.name) if comm in INTERPRETERS else None
                procs[int(d.name)] = (comm, int(f[1]), int(f[11]) + int(f[12]), int(f[21]) * PAGE, argv)
            except (OSError, ValueError, IndexError):
                pass
        cpu, children = {}, defaultdict(list)
        for pid, p in procs.items():
            last = self._prev.get(pid)
            if last:
                cpu[pid] = max(0.0, (p[2] - last[0]) / CLK_TCK / max(now - last[1], 0.1) * 100)
            self._prev[pid] = (p[2], now)
            children[p[1]].append(pid)
        for gone in set(self._prev) - set(procs):
            del self._prev[gone]
            self._since.pop(gone, None)
        self.procs, self.cpu, self.children = procs, cpu, children

    def tree(self, pid):
        """(cpu %, rss bytes) of a process and all its descendants."""
        cpu = rss = 0
        stack = [pid]
        while stack:
            q = stack.pop()
            if q in self.procs:
                cpu += self.cpu.get(q, 0)
                rss += self.procs[q][3]
                stack += self.children.get(q, [])
        return round(cpu, 1), rss

    def scanned(self, now, skip, enabled=None):
        """Cards for agent processes not already reported by hooks. State is guessed from CPU use."""
        cards = []
        for pid, (comm, ppid, _, _, argv) in self.procs.items():
            key = agent_key(comm, argv)
            if not key or pid in skip or (enabled is not None and key not in enabled):
                continue
            parent = self.procs.get(ppid)
            if parent and agent_key(parent[0], parent[4]) == key:
                continue  # child of the same agent
            cpu, rss = self.tree(pid)
            state = "working" if cpu > 3 else "idle"
            if self._since.get(pid, (None,))[0] != state:
                self._since[pid] = (state, now)
            try:
                cwd = os.readlink(f"/proc/{pid}/cwd")
            except OSError:
                cwd = ""
            hooked = BY_KEY[key].how == "hooks"
            cards.append(dict(id=f"pid-{pid}", kind=BY_KEY[key].name, name=label(cwd), cwd=cwd, state=state,
                              detail="restart it to get live status" if hooked else ("busy" if state == "working" else ""),
                              since=self._since[pid][1], cpu=cpu, rss=rss, guessed=True))
        return cards

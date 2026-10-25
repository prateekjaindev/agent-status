"""Machine performance from /proc and /sys (plus nvidia-smi when present), with a short history.
On macOS the same numbers come from built-in commands (sysctl, vm_stat, netstat, pmset) and the Mach kernel."""
import os, re, shutil, socket, subprocess, sys, time
from collections import deque
from pathlib import Path

MAC = sys.platform == "darwin"
HISTORY = 150  # samples kept for sparklines (5 minutes at the default 2s interval)
SKIP_NET = ("lo", "veth", "br-", "docker", "virbr", "tailscale", "tun", "wg", "zt", "utun", "awdl", "llw", "gif", "stf", "anpi")
CPU_SENSORS = ("k10temp", "coretemp", "zenpower", "cpu_thermal", "acpitz")


def _read(path, default=None):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default


def safe(fn, default):
    """Run one probe; a missing file or tool (e.g. no /proc on macOS) yields the default."""
    try:
        return fn()
    except (OSError, subprocess.SubprocessError, ValueError, IndexError, KeyError, TypeError, ZeroDivisionError):
        return default


def run(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout


if MAC:
    import ctypes
    _libc = ctypes.CDLL(None)
    _libc.mach_host_self.restype = ctypes.c_uint
    _libc.host_processor_info.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.POINTER(ctypes.c_uint),
                                          ctypes.POINTER(ctypes.POINTER(ctypes.c_int)), ctypes.POINTER(ctypes.c_uint)]
    _libc.vm_deallocate.argtypes = [ctypes.c_uint, ctypes.c_size_t, ctypes.c_size_t]
    _HOST, _TASK = _libc.mach_host_self(), ctypes.c_uint.in_dll(_libc, "mach_task_self_").value  # fetched once: each call takes a port ref


def mac_cpu_ticks():
    """Per-core (total, idle) ticks from host_processor_info, with the sum first like /proc/stat."""
    n, info, size = ctypes.c_uint(), ctypes.POINTER(ctypes.c_int)(), ctypes.c_uint()
    if _libc.host_processor_info(_HOST, 2, ctypes.byref(n), ctypes.byref(info), ctypes.byref(size)):  # 2 = CPU load info
        raise OSError("host_processor_info failed")
    try:
        cores = [(sum(info[i * 4:i * 4 + 4]), info[i * 4 + 2]) for i in range(n.value)]  # user, system, idle, nice
    finally:
        _libc.vm_deallocate(_TASK, ctypes.addressof(info.contents), size.value * 4)
    return [(sum(t for t, _ in cores), sum(i for _, i in cores))] + cores


def mac_memory(vm_stat, memsize, swapusage):
    """Used memory as Activity Monitor counts it: app (anonymous minus purgeable) + wired + compressed."""
    page = int(re.search(r"page size of (\d+)", vm_stat)[1])
    v = {k.strip('"'): int(n) * page for k, n in re.findall(r"^(.+?):\s+(\d+)\.$", vm_stat, re.M)}
    total = int(memsize)
    used = v.get("Anonymous pages", 0) - v.get("Pages purgeable", 0) + v["Pages wired down"] + v.get("Pages occupied by compressor", 0)
    swap = {k: float(n) * 1024 ** "KMG".index(u) * 1024 for k, n, u in re.findall(r"(total|used) = ([\d.]+)([KMG])", swapusage)}
    return dict(total=total, used=used, pct=100 * used / total, swap_total=int(swap.get("total", 0)), swap_used=int(swap.get("used", 0)))


def mac_net(netstat):
    """(rx, tx) byte counters summed over real interfaces from `netstat -ib` (one <Link#> row per interface)."""
    rx = tx = 0
    for f in (line.split() for line in netstat.splitlines()):
        if len(f) > 6 and f[2].startswith("<Link#") and not f[0].startswith(SKIP_NET):
            rx, tx = rx + int(f[-5]), tx + int(f[-2])  # counted from the right: the Address column can be empty
    return rx, tx


def mac_batteries(pmset):
    """Batteries from `pmset -g batt`: the internal one plus any UPS."""
    return [dict(name="Battery" if name.startswith("InternalBattery") else name, pct=float(pct), status=status.strip())
            for name, pct, status in re.findall(r"-(\S.*?) \(id=\d+\)\s+(\d+)%; ([^;]+);", pmset)]


def mac_uptime(boottime):
    return time.time() - int(re.search(r"sec = (\d+)", boottime)[1])


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None  # nvidia-smi prints "[N/A]" for unsupported fields


class System:
    def __init__(self):
        self.hist = {k: deque(maxlen=HISTORY) for k in ("cpu", "gpu", "mem", "rx", "tx")}
        self._cpu = self._net = None
        self._nvidia = shutil.which("nvidia-smi")

    def sample(self, now):
        cpu, cores = safe(self.cpu, (0.0, []))
        mem = safe(self.memory, dict(total=0, used=0, pct=0, swap_total=0, swap_used=0))
        net, gpus = safe(lambda: self.network(now), dict(rx=0, tx=0)), safe(self.gpus, [])
        for k, v in (("cpu", cpu), ("mem", mem["pct"]), ("gpu", gpus[0]["util"] if gpus else 0),
                     ("rx", net["rx"]), ("tx", net["tx"])):
            self.hist[k].append(round(v or 0, 1))
        temps = safe(self.temps, {})
        uptime = safe(lambda: mac_uptime(run("sysctl", "-n", "kern.boottime")), 0) if MAC else _num((_read("/proc/uptime") or "0").split()[0])
        return dict(host=socket.gethostname(), uptime=uptime,
                    cpu=dict(pct=round(cpu, 1), cores=cores, load=safe(os.getloadavg, (0, 0, 0)), temp=temps.get("cpu")),
                    mem=mem, gpus=gpus, net=net, disks=safe(self.disks, []), nvme_temp=temps.get("nvme"),
                    devices=safe(self.devices, []), hist={k: list(v) for k, v in self.hist.items()})

    def cpu(self):
        if MAC:
            cur = mac_cpu_ticks()
        else:
            rows = [r.split() for r in Path("/proc/stat").read_text().splitlines() if r.startswith("cpu")]
            cur = [(sum(map(int, r[1:9])), int(r[4]) + int(r[5])) for r in rows]  # (total, idle + iowait)
        prev, self._cpu = self._cpu, cur
        if not prev or len(prev) != len(cur):
            return 0.0, [0] * (len(cur) - 1)
        pct = [100 * (1 - (i - pi) / max(t - pt, 1)) for (t, i), (pt, pi) in zip(cur, prev)]
        return max(pct[0], 0), [max(round(p), 0) for p in pct[1:]]

    def memory(self):
        if MAC:
            return mac_memory(run("vm_stat"), *run("sysctl", "-n", "hw.memsize", "vm.swapusage").splitlines()[:2])
        m = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, v = line.split(":", 1)
            m[k] = int(v.split()[0]) * 1024
        total, avail = m.get("MemTotal", 1), m.get("MemAvailable", 0)
        return dict(total=total, used=total - avail, pct=100 * (total - avail) / total,
                    swap_total=m.get("SwapTotal", 0), swap_used=m.get("SwapTotal", 0) - m.get("SwapFree", 0))

    def network(self, now):
        rx = tx = 0
        if MAC:
            rx, tx = mac_net(run("netstat", "-ib"))
        else:
            for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
                name, data = line.split(":", 1)
                if not name.strip().startswith(SKIP_NET):
                    f = data.split()
                    rx, tx = rx + int(f[0]), tx + int(f[8])
        prev, self._net = self._net, (rx, tx, now)
        if not prev:
            return dict(rx=0, tx=0)
        dt = max(now - prev[2], 0.1)
        return dict(rx=max(rx - prev[0], 0) / dt, tx=max(tx - prev[1], 0) / dt)

    def gpus(self):
        out = []
        if self._nvidia:
            try:
                res = subprocess.run([self._nvidia, "--query-gpu=name,utilization.gpu,memory.used,memory.total,"
                                      "temperature.gpu,power.draw,power.limit", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=2)
                for line in res.stdout.strip().splitlines():
                    name, util, used, total, temp, power, limit = [x.strip() for x in line.split(",")]
                    out.append(dict(name=name.replace("NVIDIA GeForce ", ""), util=_num(util), mem_used=(_num(used) or 0) * 2**20,
                                    mem_total=(_num(total) or 0) * 2**20, temp=_num(temp), power=_num(power), power_limit=_num(limit)))
            except (OSError, subprocess.TimeoutExpired, ValueError):
                pass
        for dev in sorted(Path("/sys/class/drm").glob("card[0-9]*/device")):
            util = _num(_read(dev / "gpu_busy_percent"))
            if util is None or _read(dev / "vendor") != "0x1002":
                continue
            hw = next(dev.glob("hwmon/hwmon*"), None)
            temp, power = (_num(_read(hw / "temp1_input")), _num(_read(hw / "power1_average"))) if hw else (None, None)
            out.append(dict(name="AMD Radeon", util=util, mem_used=_num(_read(dev / "mem_info_vram_used")) or 0,
                            mem_total=_num(_read(dev / "mem_info_vram_total")) or 0,
                            temp=temp / 1000 if temp else None, power=power / 1e6 if power else None, power_limit=None))
        return out

    def temps(self):
        t = {}
        for hw in Path("/sys/class/hwmon").glob("hwmon*"):
            name, val = _read(hw / "name", ""), _num(_read(hw / "temp1_input"))
            if val is None:
                continue
            if name in CPU_SENSORS and "cpu" not in t:
                t["cpu"] = val / 1000
            elif name == "nvme" and "nvme" not in t:
                t["nvme"] = val / 1000
        return t

    def disks(self):
        out, seen = [], set()
        for mount in ("/", str(Path.home())):
            try:
                st = os.statvfs(mount)
            except OSError:
                continue
            key = (st.f_blocks, st.f_bfree)  # btrfs subvolumes have distinct st_dev but share a filesystem
            if key in seen:
                continue
            seen.add(key)
            total = st.f_blocks * st.f_frsize
            out.append(dict(mount=mount, total=total, used=total - st.f_bavail * st.f_frsize))
        return out

    def devices(self):
        """Batteries: laptop, mouse, keyboard, headset (anything the kernel exposes with a capacity)."""
        if MAC:
            return mac_batteries(run("pmset", "-g", "batt"))
        out = []
        for ps in sorted(Path("/sys/class/power_supply").glob("*")):
            cap = _num(_read(ps / "capacity"))
            if cap is None:
                continue
            out.append(dict(name=_read(ps / "model_name") or ps.name, pct=cap, status=_read(ps / "status", "")))
        return out

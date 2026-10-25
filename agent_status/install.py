"""`agent-status install`: pick agents, add their hooks, start the background service. `uninstall` reverses it."""
import json, os, plistlib, shutil, subprocess, sys, time
from pathlib import Path

from .agents import AGENTS, BY_KEY
from .config import HOME, USER_CONFIG, enabled_agents

UNIT = HOME / ".config/systemd/user/agent-status.service"
LABEL = "dev.agent-status"
PLIST = HOME / f"Library/LaunchAgents/{LABEL}.plist"
HOW = {"hooks": "live hooks", "data": "reads its data", "process": "process only"}


def command():
    exe = shutil.which("agent-status")
    return exe if exe else f"{sys.executable} -m agent_status"  # the PATH entry survives upgrades


def systemctl(*args):
    return subprocess.run(["systemctl", "--user", *args], check=False, capture_output=True)


def launchctl(*args):
    return subprocess.run(["launchctl", *args], check=False, capture_output=True)


def launch_agent():
    """macOS LaunchAgent: start at login, restart if it crashes."""
    exe = shutil.which("agent-status")
    log = str(HOME / "Library/Logs/agent-status.log")
    return dict(Label=LABEL, ProgramArguments=[exe, "serve"] if exe else [sys.executable, "-m", "agent_status", "serve"],
                RunAtLoad=True, KeepAlive=dict(SuccessfulExit=False), StandardOutPath=log, StandardErrorPath=log,
                EnvironmentVariables=dict(PATH=os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")))  # finds Homebrew git


def table(selected):
    print()
    for i, a in enumerate(AGENTS, 1):
        found = a.found()
        mark = "[x]" if a.key in selected else "[ ]"
        where = f"found {found}" if found else "not found"
        print(f"  {mark} {i:>2}  {a.name:<20} {HOW[a.how]:<15} {where}")
    print()


def doctor(agents=None, selected=None, exe=None, out=print):
    """Report whether every selected agent still has the hook set this version writes.
    Returns 1 when a config is stale (or hooks were never installed), 0 when everything matches."""
    agents = AGENTS if agents is None else agents
    selected = enabled_agents() if selected is None else selected
    exe = command() if exe is None else exe
    if selected is None:
        out("  ! hooks are not installed yet")
        out(f"    run: {exe} install")
        return 1
    if not selected:
        out("  – no agents are selected")
        out(f"    run: {exe} install")
        return 0
    stale = []
    out("")
    for a in agents:
        if a.key not in selected:
            continue
        if a.how != "hooks":
            out(f"  ✓ {a.name:<20} {HOW[a.how]} (no hooks to check)")
            continue
        try:
            missing = a.stale(exe)
        except SystemExit as e:
            stale.append(a.key)
            out(f"  ! {a.name:<20} {e}")  # load_json already names the broken file
            continue
        if missing:
            stale.append(a.key)
            out(f"  ! {a.name:<20} stale hooks: {', '.join(missing)}")
        else:
            out(f"  ✓ {a.name:<20} hooks up to date")
    out("")
    if stale:
        out(f"  run: {exe} install --agents {','.join(sorted(selected))}")
        return 1
    return 0


def choose(preselected):
    """Interactive toggle list. Returns the chosen agent keys."""
    selected = set(preselected)
    while True:
        table(selected)
        try:
            ans = input("Toggle by number (e.g. 3 7), [a]ll found, [n]one, Enter to continue, [q]uit: ").strip().lower()
        except EOFError:
            return selected
        if not ans:
            return selected
        if ans == "q":
            raise SystemExit("cancelled")
        if ans == "a":
            selected = {a.key for a in AGENTS if a.found()}
            continue
        if ans == "n":
            selected = set()
            continue
        for tok in ans.replace(",", " ").split():
            if tok.isdigit() and 1 <= int(tok) <= len(AGENTS):
                selected ^= {AGENTS[int(tok) - 1].key}
            else:
                print(f"  ? ignoring {tok!r}")


def parse_args(args):
    opts = {"agents": None, "yes": False, "service": True}
    it = iter(args)
    for a in it:
        if a in ("-y", "--yes"):
            opts["yes"] = True
        elif a == "--no-service":
            opts["service"] = False
        elif a == "--agents":
            opts["agents"] = next(it, "")
        elif a.startswith("--agents="):
            opts["agents"] = a.split("=", 1)[1]
        else:
            raise SystemExit(f"unknown option {a}\nusage: agent-status install [--agents claude,codex,...] [--yes] [--no-service]")
    return opts


def install(args=()):
    opts, exe = parse_args(args), command()
    previous = enabled_agents() or set()
    if opts["agents"] is not None:
        chosen = {k.strip() for k in opts["agents"].split(",") if k.strip()}
        unknown = chosen - set(BY_KEY)
        if unknown:
            raise SystemExit(f"unknown agents: {', '.join(sorted(unknown))}\nknown: {', '.join(BY_KEY)}")
    else:
        default = previous or {a.key for a in AGENTS if a.found()}
        if opts["yes"] or not sys.stdin.isatty():
            chosen = default
        else:
            print("Which agents should agent-status track?  (detected ones are preselected)")
            chosen = choose(default)

    USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    USER_CONFIG.write_text(json.dumps({"agents": sorted(chosen)}, indent=2) + "\n")
    print()
    for a in AGENTS:
        if a.key in chosen:
            a.install(exe)
            print(f"  ✓ {a.name}" + (" — hooks added" if a.how == "hooks" else ""))
        elif a.how == "hooks":
            a.uninstall()  # no-op unless our hooks are there
            if a.key in previous:
                print(f"  – {a.name} — hooks removed")

    if opts["service"] and sys.platform == "darwin":
        PLIST.parent.mkdir(parents=True, exist_ok=True)
        PLIST.write_bytes(plistlib.dumps(launch_agent()))
        launchctl("bootout", f"gui/{os.getuid()}/{LABEL}")  # no-op on first install
        for _ in range(5):  # bootout returns before the old job is fully gone, so bootstrap can briefly fail
            if launchctl("bootstrap", f"gui/{os.getuid()}", str(PLIST)).returncode == 0:
                print(f"  ✓ background service running ({PLIST.name})")
                break
            time.sleep(1)
        else:
            print(f"  ! launchctl could not start {PLIST}: run `{exe} serve` yourself")
    elif opts["service"] and shutil.which("systemctl"):
        UNIT.parent.mkdir(parents=True, exist_ok=True)
        UNIT.write_text(f"[Unit]\nDescription=agent-status dashboard\nAfter=network-online.target\n\n"
                        f"[Service]\nExecStart={exe} serve\nRestart=on-failure\n\n[Install]\nWantedBy=default.target\n")
        systemctl("daemon-reload")
        systemctl("enable", "agent-status")
        systemctl("restart", "agent-status")
        print(f"  ✓ background service running ({UNIT.name})")
    elif opts["service"]:
        print(f"  ! no systemd here: run `{exe} serve` yourself (or from a login item)")

    from .server import urls
    from .config import PORT
    print("\nOpen on your tablet or phone (same Wi-Fi):")
    for url, what in urls():
        print(f"  {url}   ({what})")
    print("\n  iPad/iPhone: Safari → Share → Add to Home Screen")
    print("  Android:     Chrome → ⋮ → Add to Home screen")
    if shutil.which("ufw"):
        print(f"\nFirewall: ufw is installed; if the page won't load, allow the port:\n  sudo ufw allow {PORT}/tcp")
    print("\nAgents that are already running pick up their hooks after a restart.")


def uninstall(args=()):
    for a in AGENTS:
        if a.how == "hooks":
            a.uninstall()
    print("  ✓ hooks removed from every agent")
    if UNIT.exists():
        systemctl("disable", "--now", "agent-status")
        UNIT.unlink()
        systemctl("daemon-reload")
        print("  ✓ background service removed")
    if PLIST.exists():
        launchctl("bootout", f"gui/{os.getuid()}/{LABEL}")
        PLIST.unlink()
        print("  ✓ background service removed")
    USER_CONFIG.unlink(missing_ok=True)
    print("  ✓ settings removed (session state in ~/.local/state/agent-status is left in place)")

"""agent-status — a live dashboard of your AI coding agents.

  agent-status install [--agents claude,codex,...] [--yes] [--no-service]
                                 choose agents, add their hooks, start the background service
  agent-status uninstall         remove every hook and the service
  agent-status agents            list supported agents and what was detected
  agent-status doctor            check that installed hooks match this version
  agent-status serve [--demo]    run the dashboard server in the foreground (--demo: fictional data)
  agent-status url               print the dashboard links
  agent-status hook AGENT [EVENT]   (called by agent hooks; reads the event JSON on stdin)
"""
import sys

from . import __version__


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""
    if cmd == "hook":
        from .hooks import hook  # keep this path light: it runs on every tool call
        hook(argv[1] if len(argv) > 1 else "claude", argv[2] if len(argv) > 2 else None)
    elif cmd == "serve":
        from .server import serve
        serve(demo="--demo" in argv[1:])
    elif cmd == "url":
        from .server import urls
        for url, what in urls():
            print(f"{url}   ({what})")
    elif cmd == "install":
        from .install import install
        install(argv[1:])
    elif cmd == "uninstall":
        from .install import uninstall
        uninstall(argv[1:])
    elif cmd == "agents":
        from .config import enabled_agents
        from .install import table
        enabled = enabled_agents()
        table(enabled if enabled is not None else set())
        print("  [x] = tracked (from `agent-status install`)" if enabled is not None else "  not installed yet: run `agent-status install`")
    elif cmd == "doctor":
        from .install import doctor
        sys.exit(doctor())
    elif cmd in ("-V", "--version", "version"):
        print(__version__)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()

"""HTTP server: the dashboard page is public, the /status data and /decide need the access key."""
import json, os, re, secrets, socket, socketserver, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import DECISIONS, HOST, PORT, SEEN, SESSIONS, STATE

WEB = Path(__file__).parent / "web"
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"),
          "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
          **{f"/icon-{n}.png": (f"icon-{n}.png", "image/png") for n in (180, 192, 512)}}


def token():
    path = STATE / "token"
    if not path.exists():
        STATE.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(12))
        path.chmod(0o600)
    return path.read_text().strip()


def lan_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("10.255.255.255", 1))  # no packet is sent; this only picks the outbound interface
        return s.getsockname()[0]


def hostname():
    """The host's name without a `.local` suffix; `urls()` adds it back exactly once (macOS already has it)."""
    name = socket.gethostname()
    return name[:-len(".local")] if name.lower().endswith(".local") else name


def urls():
    key = token()
    return [(f"http://{hostname()}.local:{PORT}/?k={key}", "stable name (mDNS/Avahi)"),
            (f"http://{lan_ip()}:{PORT}/?k={key}", "current IP")]


class Server(ThreadingHTTPServer):
    def server_bind(self):
        # http.server's server_bind calls getfqdn("0.0.0.0"), a reverse lookup that blocks for over a minute
        # on macOS CI. The socket must be accepting while curl waits, so skip the lookup.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def decide(body, now=None):
    """Record an Allow/Deny tap for the permission prompt a hook is waiting on. Returns (http code, message)."""
    try:
        req = json.loads(body)
        sid, ask, decision = req["id"], req["ask"], req["decision"]
    except (ValueError, KeyError, TypeError):
        return 400, "bad request"
    if decision not in ("allow", "deny") or not all(isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", v)
                                                    for v in (sid, ask)):
        return 400, "bad request"
    try:
        s = json.loads((SESSIONS / f"{sid}.json").read_text())
    except (OSError, ValueError):
        s = None
    # The ask token is fresh per prompt, so a late or replayed tap can't answer a different prompt.
    if not s or not secrets.compare_digest(str(s.get("ask", "")), ask) or s.get("ask_until", 0) < (now or time.time()):
        return 409, "that prompt is no longer waiting"
    DECISIONS.mkdir(parents=True, exist_ok=True)
    tmp = DECISIONS / f"{ask}.{os.getpid()}.tmp"
    tmp.write_text(decision)
    tmp.replace(DECISIONS / ask)
    return 200, "ok"


def handler(key, collector):
    class Handler(BaseHTTPRequestHandler):
        def authorized(self, u):
            return secrets.compare_digest(parse_qs(u.query).get("k", [""])[0], key)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/status":
                if not self.authorized(u):
                    return self.send(403, "application/json", b'{"error":"bad key"}')
                try:
                    SEEN.touch()  # lets permission hooks know someone is watching
                except OSError:
                    pass
                return self.send(200, "application/json", collector.json)
            if u.path in STATIC:
                name, ctype = STATIC[u.path]
                return self.send(200, ctype, (WEB / name).read_bytes())
            self.send(404, "text/plain", b"not found")

        def do_POST(self):
            u = urlparse(self.path)
            if u.path != "/decide":
                return self.send(404, "text/plain", b"not found")
            # CSRF: a cross-site page can't send a JSON content type without a CORS preflight (never granted here),
            # doesn't know the key, and a browser always names its origin on a POST.
            origin = self.headers.get("Origin")
            if (not self.authorized(u) or self.headers.get_content_type() != "application/json"
                    or (origin and urlparse(origin).netloc != self.headers.get("Host"))):
                return self.send(403, "application/json", b'{"error":"forbidden"}')
            n = self.headers.get("Content-Length", "")
            n = int(n) if n.isdigit() else 0
            if not 0 < n <= 2048:
                return self.send(400, "application/json", b'{"error":"bad request"}')
            code, msg = decide(self.rfile.read(n))
            self.send(code, "application/json", json.dumps({"ok" if code == 200 else "error": msg}).encode())

        def send(self, code, ctype, body):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    return Handler


def serve():
    from .collect import Collector
    key, collector = token(), Collector()
    collector.start()
    for url, what in urls():
        print(f"agent-status: {url}  ({what})", flush=True)
    Server((HOST, PORT), handler(key, collector)).serve_forever()

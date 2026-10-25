"""HTTP server: the dashboard page is public, the /status data needs the access key."""
import secrets, socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .collect import Collector
from .config import HOST, PORT, STATE

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


def urls():
    key = token()
    return [(f"http://{socket.gethostname()}.local:{PORT}/?k={key}", "stable name (mDNS/Avahi)"),
            (f"http://{lan_ip()}:{PORT}/?k={key}", "current IP")]


def serve():
    key, collector = token(), Collector()
    collector.start()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/status":
                if not secrets.compare_digest(parse_qs(u.query).get("k", [""])[0], key):
                    return self.send(403, "application/json", b'{"error":"bad key"}')
                return self.send(200, "application/json", collector.json)
            if u.path in STATIC:
                name, ctype = STATIC[u.path]
                return self.send(200, ctype, (WEB / name).read_bytes())
            self.send(404, "text/plain", b"not found")

        def send(self, code, ctype, body):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    for url, what in urls():
        print(f"agent-status: {url}  ({what})", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()

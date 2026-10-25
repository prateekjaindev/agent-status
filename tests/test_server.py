"""The dashboard links, the server's startup path (the macOS CI smoke-test hang) and the key/limits."""
import tempfile, unittest
from pathlib import Path
from unittest import mock

from agent_status import server


class Urls(unittest.TestCase):
    def urls(self, host):
        with mock.patch.object(server.socket, "gethostname", return_value=host), \
                mock.patch.object(server, "lan_ip", return_value="192.0.2.10"), \
                mock.patch.object(server, "token", return_value="k"):
            return [u for u, _ in server.urls()]

    def test_adds_local_once(self):
        for host, name in (("myhost", "myhost"), ("myhost.local", "myhost"), ("myhost.LOCAL", "myhost")):
            with self.subTest(host=host):
                self.assertEqual(self.urls(host), [f"http://{name}.local:{server.PORT}/?k=k",
                                                   f"http://192.0.2.10:{server.PORT}/?k=k"])


class Limits(unittest.TestCase):
    def test_sliding_window_per_client(self):
        r = server.RateLimiter(2, 10)
        self.assertTrue(r.allow("a", now=0))
        self.assertTrue(r.allow("a", now=1))
        self.assertFalse(r.allow("a", now=2))
        self.assertTrue(r.allow("b", now=2))  # another client has its own window
        self.assertTrue(r.allow("a", now=11))  # the first hit expired


class Rotate(unittest.TestCase):
    def test_writes_a_new_private_key_and_prints_its_links(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d)
            with mock.patch.object(server, "STATE", state), \
                    mock.patch.object(server.socket, "gethostname", return_value="myhost"), \
                    mock.patch.object(server, "lan_ip", return_value="192.0.2.10"):
                old, out = server.token(), []
                server.rotate_key(out=out.append)
                new = server.token()
                self.assertNotEqual(old, new)
                self.assertEqual((state / "token").stat().st_mode & 0o777, 0o600)
                self.assertTrue(any(f"http://myhost.local:{server.PORT}/?k={new}" in line for line in out))
                self.assertTrue(any(f"http://192.0.2.10:{server.PORT}/?k={new}" in line for line in out))


class Bind(unittest.TestCase):
    def test_bind_does_not_look_up_the_hostname(self):
        # http.server's server_bind calls getfqdn(0.0.0.0), which blocks for over a minute on macOS CI.
        class Collector:
            json = b"{}"

        with mock.patch("socket.getfqdn", side_effect=AssertionError("getfqdn must not run at startup")):
            srv = server.Server(("127.0.0.1", 0), server.handler("k", Collector()))
            try:
                self.assertEqual(srv.server_name, "127.0.0.1")
                self.assertEqual(srv.server_address[0], "127.0.0.1")
            finally:
                srv.server_close()


if __name__ == "__main__":
    unittest.main()

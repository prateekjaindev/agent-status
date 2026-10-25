"""The dashboard links and the server's startup path (the macOS CI smoke-test hang)."""
import unittest
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

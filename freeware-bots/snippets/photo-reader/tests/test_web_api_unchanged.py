"""Regression: the JSON API (/health, /message, /photo and the error replies) is
byte-for-byte the same as v0.1.1. Each request goes to the frozen v0.1.1 adapter
(tests/legacy_web_v0_1_1.py) and to the current adapter, on the same bot, and the
status code, Content-Type and body are compared. The only intended difference
is that GET / and GET /index.html now serve the web UI (v0.1.1 answered 404)."""
import http.client
import json
import socket
import unittest
from http.server import ThreadingHTTPServer
import threading

from tests.helpers import FakeOllama, test_cfg
from tests import legacy_web_v0_1_1 as legacy
from bot.core import Bot
from bot.adapters.web import WebAdapter, API_GET, API_POST


def raw_request(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        c.request(method, path, body=body, headers=headers or {})
        r = c.getresponse()
        return r.status, r.getheader("Content-Type"), r.read()
    finally:
        c.close()


def normalise(path, body):
    """/health carries uptime and a message counter that differ between two calls."""
    if path.startswith("/health"):
        d = json.loads(body)
        d.pop("uptime_s", None); d.pop("memory_messages", None)
        return d
    return body


class ApiUnchangedTests(unittest.TestCase):
    MAX = 1000

    def setUp(self):
        self.fake = FakeOllama(reply="same <reply> & text")
        cfg = test_cfg(self.fake.url)
        cfg["web"]["max_body_bytes"] = self.MAX
        self.bot = Bot(cfg)
        self.old = ThreadingHTTPServer(("127.0.0.1", 0), legacy.make_handler(self.bot))
        threading.Thread(target=self.old.serve_forever, daemon=True).start()
        self.new = WebAdapter(self.bot); self.new.start(background=True)

    def tearDown(self):
        self.new.stop(); self.old.shutdown(); self.old.server_close()
        self.fake.close(); self.bot.close()

    CASES = [
        ("GET", "/health", None, {}),
        ("GET", "/health?x=1", None, {}),
        ("GET", "/nope", None, {}),
        ("GET", "/favicon.ico", None, {}),
        ("GET", "/photo", None, {}),
        ("POST", "/message", json.dumps({"user": "a", "text": "hi"}).encode(), {"Content-Type": "application/json"}),
        ("POST", "/message", json.dumps({"text": "no user"}).encode(), {"Content-Type": "application/json"}),
        ("POST", "/message", b"{}", {"Content-Type": "application/json"}),
        ("POST", "/message", b"{not json", {"Content-Type": "application/json"}),
        ("POST", "/message", json.dumps({"text": 5}).encode(), {"Content-Type": "application/json"}),
        ("POST", "/message", b"", {"Content-Type": "application/json"}),
        ("POST", "/photo", b"", {"Content-Type": "image/png"}),
        ("POST", "/photo?user=u&filename=a.png", b"\x89PNG....", {"Content-Type": "image/png"}),
        ("POST", "/photo", b"plain text", {"Content-Type": "text/plain"}),
        ("POST", "/photo", b"x" * (MAX + 1), {"Content-Type": "image/png"}),
        ("POST", "/nope", b"x", {}),
        ("POST", "/", b"x", {}),
        ("POST", "/index.html", b"x", {}),
    ]

    def test_same_replies_as_v0_1_1(self):
        for method, path, body, hdr in self.CASES:
            with self.subTest(method=method, path=path, body=(body or b"")[:20]):
                o = raw_request(self.old.server_address[1], method, path, body, hdr)
                n = raw_request(self.new.port, method, path, body, hdr)
                self.assertEqual(o[0], n[0], "status")
                self.assertEqual(o[1], n[1], "content-type")
                self.assertEqual(normalise(path, o[2]), normalise(path, n[2]), "body")

    def test_only_ui_paths_changed(self):
        for path in ("/", "/index.html"):
            o = raw_request(self.old.server_address[1], "GET", path)
            n = raw_request(self.new.port, "GET", path)
            self.assertEqual((o[0], o[1]), (404, "application/json; charset=utf-8"))
            self.assertEqual((n[0], n[1]), (200, "text/html; charset=utf-8"))

    def test_api_constants_match_routes(self):
        for p in API_GET:
            self.assertEqual(raw_request(self.new.port, "GET", p)[0], 200)
        for p in API_POST:
            self.assertNotEqual(raw_request(self.new.port, "POST", p, b"{}")[0], 404)

    def test_golden_v0_1_1_error_bodies(self):
        """Absolute expectations, written down from v0.1.1 behaviour."""
        p = self.new.port
        self.assertEqual(raw_request(p, "GET", "/nope")[2], json.dumps({"error": "not found"}, indent=2).encode())
        self.assertEqual(raw_request(p, "POST", "/message", b"{}")[2],
                         json.dumps({"error": "JSON field 'text' required"}, indent=2).encode())
        self.assertEqual(raw_request(p, "POST", "/photo", b"")[2],
                         json.dumps({"error": "empty body; send image bytes"}, indent=2).encode())
        s, ct, b = raw_request(p, "POST", "/photo", b"x" * (self.MAX + 1))
        self.assertEqual((s, json.loads(b)), (413, {"error": f"body too large ({self.MAX + 1} > {self.MAX} bytes)"}))
        s, ct, b = raw_request(p, "POST", "/message", json.dumps({"text": "hi"}).encode())
        self.assertEqual((s, ct), (200, "application/json; charset=utf-8"))
        self.assertEqual(json.loads(b)["text"], "same <reply> & text")  # JSON is not HTML-escaped

    def test_negative_content_length_is_400_not_a_hang(self):
        # v0.1.2 fix: v0.1.1 called rfile.read(-1) here and waited for the client to close.
        s = socket.create_connection(("127.0.0.1", self.new.port), timeout=10)
        try:
            s.sendall(b"POST /message HTTP/1.1\r\nHost: x\r\nContent-Length: -5\r\n\r\n")
            data = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
        finally:
            s.close()
        self.assertTrue(data.startswith(b"HTTP/1.0 400"), data[:40])
        self.assertIn(b"bad Content-Length", data)


if __name__ == "__main__":
    unittest.main()

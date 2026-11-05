import json
import unittest
import urllib.error
import urllib.request

from tests.helpers import FakeOllama, test_cfg
from bot.core import Bot
from bot.adapters.web import WebAdapter


def call(url, data=None, ctype="application/json"):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


class WebAdapterTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeOllama()
        cfg = test_cfg(self.fake.url)
        cfg["web"]["max_body_bytes"] = 1000
        self.bot = Bot(cfg)
        self.web = WebAdapter(self.bot)
        self.web.start(background=True)
        self.base = f"http://127.0.0.1:{self.web.port}"

    def tearDown(self):
        self.web.stop(); self.fake.close(); self.bot.close()

    def test_health(self):
        code, body = call(self.base + "/health")
        self.assertEqual(code, 200)
        self.assertEqual(body["status"], "ok")
        self.assertIn("ollama", body)

    def test_message(self):
        code, body = call(self.base + "/message", json.dumps({"user": "a", "text": "hi"}).encode())
        self.assertEqual((code, body["text"]), (200, "fake-reply"))

    def test_bad_requests(self):
        self.assertEqual(call(self.base + "/message", b"{}")[0], 400)
        self.assertEqual(call(self.base + "/nope")[0], 404)
        self.assertEqual(call(self.base + "/photo", b"x" * 2000, "image/png")[0], 413)
        self.assertEqual(call(self.base + "/photo", b"", "image/png")[0], 400)

    def test_photo_default_job_unsupported(self):
        code, body = call(self.base + "/photo", b"\x89PNG....", "image/png")
        self.assertEqual((code, body["status"]), (200, "unsupported"))


if __name__ == "__main__":
    unittest.main()

import json
import logging
import os
import tempfile
import unittest

from tests.helpers import FakeOllama, free_port, test_cfg
from bot import config as config_mod, __version__
from bot.core import Bot
from bot.logging_setup import RedactFilter
from bot.memory import Memory
from bot.ollama_client import OllamaClient, OllamaError, OllamaUnavailable


class ConfigTests(unittest.TestCase):
    def test_defaults_and_file_and_env(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "c.json")
        with open(p, "w") as f:
            json.dump({"bot_name": "x", "ollama": {"chat_model": "m1"}}, f)
        cfg = config_mod.load(p, env={"BOT_OLLAMA_URL": "http://203.0.113.50:11434", "BOT_WEB_PORT": "9000"})
        self.assertEqual(cfg["bot_name"], "x")
        self.assertEqual(cfg["ollama"]["chat_model"], "m1")
        self.assertEqual(cfg["ollama"]["base_url"], "http://203.0.113.50:11434")
        self.assertEqual(cfg["web"]["port"], 9000)
        self.assertEqual(cfg["memory"]["backend"], "sqlite")

    def test_shipped_config_has_no_secrets(self):
        from bot import ROOT
        text = (ROOT / "config" / "config.example.json").read_text()
        cfg = json.loads(text)
        self.assertEqual(cfg["telegram"]["token_env"], "TELEGRAM_BOT_TOKEN")
        self.assertNotIn("token\":", text.replace("token_env\":", ""))


class MemoryTests(unittest.TestCase):
    def test_add_recent_kv(self):
        m = Memory(":memory:")
        for i in range(5):
            m.add("web", "u1", "user", f"m{i}")
        m.add("web", "u2", "user", "other")
        self.assertEqual([r["content"] for r in m.recent("web", "u1", 3)], ["m2", "m3", "m4"])
        m.set("k", "v")
        self.assertEqual(m.get("k"), "v")
        self.assertIsNone(m.get("nope"))
        self.assertEqual(m.count(), 6)


class LoggingTests(unittest.TestCase):
    def test_redacts_token(self):
        rec = logging.LogRecord("bot", logging.INFO, "", 0, "token is %s", ("SECRET123456",), None)
        RedactFilter(["SECRET123456"]).filter(rec)
        self.assertEqual(rec.getMessage(), "token is ***REDACTED***")

    def test_log_file_written(self):
        cfg = test_cfg(); cfg["log_level"] = "INFO"
        Bot(cfg)
        with open(os.path.join(cfg["data_dir"], "logs", "bot.log")) as f:
            self.assertIn("started", f.read())


class OllamaClientTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeOllama(models=["qwen3:8b", "llava:latest"])

    def tearDown(self):
        self.fake.close()

    def test_calls_against_fake_server(self):
        c = OllamaClient(self.fake.url, 5)
        self.assertEqual(c.version(), "fake-0.0")
        self.assertTrue(c.has_model("qwen3:8b"))
        self.assertTrue(c.has_model("llava"))
        self.assertFalse(c.has_model("qwen2.5vl:7b"))
        self.assertEqual(c.chat("qwen3:8b", [{"role": "user", "content": "hi"}]), "fake-reply")
        self.assertEqual(c.generate("llava:latest", "describe", images=[b"\x89PNG"]), "fake-reply")
        self.assertEqual(self.fake.requests[-1][2]["images"], ["iVBORw=="])
        self.assertNotIn("think", self.fake.requests[-1][2])
        c.generate("llava:latest", "describe", think=False)
        self.assertIs(self.fake.requests[-1][2]["think"], False)
        self.assertEqual(c.last_response["response"], "fake-reply")
        with self.assertRaises(OllamaError):
            c.chat("missing:1b", [])

    def test_unreachable(self):
        c = OllamaClient(f"http://127.0.0.1:{free_port()}", 2)
        with self.assertRaises(OllamaUnavailable):
            c.models()
        self.assertFalse(c.status()["reachable"])


class BotTests(unittest.TestCase):
    def test_chat_with_fake_and_memory(self):
        fake = FakeOllama()
        try:
            bot = Bot(test_cfg(fake.url))
            r = bot.handle_text("web", "u", "hello")
            self.assertEqual(r, {"text": "fake-reply", "status": "ok"})
            bot.handle_text("web", "u", "again")
            msgs = fake.requests[-1][2]["messages"]
            self.assertEqual([m["content"] for m in msgs], ["hello", "fake-reply", "again"])
            h = bot.health()
            self.assertEqual(h["version"], __version__)
            self.assertTrue(h["ollama"]["reachable"])
        finally:
            fake.close()

    def test_chat_when_ollama_down(self):
        bot = Bot(test_cfg(f"http://127.0.0.1:{free_port()}"))
        r = bot.handle_text("web", "u", "hello")
        self.assertEqual(r["status"], "model_unavailable")


class RealOllamaProbe(unittest.TestCase):
    """Probes the REAL Ollama at the configured URL. Skipped when none is running."""
    def test_real_ollama(self):
        url = os.environ.get("BOT_OLLAMA_URL", "http://127.0.0.1:11434")
        st = OllamaClient(url, 3).status()
        if not st["reachable"]:
            self.skipTest(f"no real Ollama at {url}: {st['error']}")
        self.assertIsInstance(st["models"], list)
        print(f"\n  real Ollama at {url}: version {st['version']}, models {st['models']}")


if __name__ == "__main__":
    unittest.main()

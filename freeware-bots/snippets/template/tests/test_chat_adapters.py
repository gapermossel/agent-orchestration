"""Chat adapter tests. OFFLINE ONLY: no real tokens, no network sends.
- All three adapters must fail safely (AdapterUnavailable) when the library
  or the token env var is missing; the reason is printed for the report.
- Telegram (library imports on the box): the Application is built with a
  placeholder token and the handlers are driven with stand-in objects that
  record the reply instead of sending it."""
import asyncio
import unittest

from tests.helpers import test_cfg
from bot.core import Bot
from bot.adapters import AdapterUnavailable, import_library
from bot.adapters.telegram_adapter import TelegramAdapter
from bot.adapters.discord_adapter import DiscordAdapter
from bot.adapters.matrix_adapter import MatrixAdapter

PLACEHOLDER = "123456:PLACEHOLDER-NOT-A-REAL-TOKEN"


def telegram_importable(cfg):
    try:
        import_library(cfg, "telegram")
        import telegram.ext  # noqa: F401
        return True
    except Exception:
        return False


class ChatAdapterStubTests(unittest.TestCase):
    def test_fail_safely_without_libs_or_tokens(self):
        bot = Bot(test_cfg())
        try:
            for cls in (TelegramAdapter, DiscordAdapter, MatrixAdapter):
                with self.subTest(cls.__name__):
                    with self.assertRaises(AdapterUnavailable) as cm:
                        cls(bot, env={})
                    print(f"\n  {cls.__name__}: {cm.exception}")
        finally:
            bot.close()


class _Rec:
    def __init__(self):
        self.sent = []


class _Msg:
    def __init__(self, rec, text=None, photo=None):
        self.rec, self.text, self.photo = rec, text, photo

    async def reply_text(self, text):
        self.rec.sent.append(text)


class _File:
    def __init__(self, data):
        self.data = data

    async def download_as_bytearray(self):
        return bytearray(self.data)


class _Photo:
    def __init__(self, data):
        self.data = data

    async def get_file(self):
        return _File(self.data)


class _User:
    id = 42


class _Update:
    def __init__(self, msg):
        self.message, self.effective_user = msg, _User()


class TelegramOfflineTests(unittest.TestCase):
    def setUp(self):
        self.cfg = test_cfg()
        if not telegram_importable(self.cfg):
            self.skipTest("python-telegram-bot not importable on this box")
        self.bot = Bot(self.cfg)
        self.ad = TelegramAdapter(self.bot, env={"TELEGRAM_BOT_TOKEN": PLACEHOLDER})

    def tearDown(self):
        if hasattr(self, "bot"):
            self.bot.close()

    def test_build_app_registers_handlers_without_network(self):
        import telegram
        app = self.ad.build_app()
        hs = app.handlers[0]
        self.assertEqual(len(hs), 2)
        self.assertEqual([h.callback for h in hs], [self.ad.on_photo, self.ad.on_text])
        self.assertEqual(app.bot.token, PLACEHOLDER)
        print(f"\n  python-telegram-bot {telegram.__version__} imported from {telegram.__file__}")

    def test_text_handler_replies_via_bot(self):
        rec = _Rec()
        asyncio.run(self.ad.on_text(_Update(_Msg(rec, text="hello")), None))
        self.assertEqual(len(rec.sent), 1)
        self.assertEqual(self.bot.memory.count(), 2)

    def test_photo_handler_passes_bytes_and_truncates(self):
        rec = _Rec()
        seen = {}

        def fake_handle_photo(channel, user, data, filename=None):
            seen.update(channel=channel, user=user, data=data, filename=filename)
            return {"text": "x" * 5000}

        self.bot.handle_photo = fake_handle_photo
        upd = _Update(_Msg(rec, photo=[_Photo(b"small"), _Photo(b"\x89PNGbig")]))
        asyncio.run(self.ad.on_photo(upd, None))
        self.assertEqual(seen, {"channel": "telegram", "user": 42, "data": b"\x89PNGbig", "filename": "telegram.jpg"})
        self.assertEqual(len(rec.sent[0]), 4000)


if __name__ == "__main__":
    unittest.main()

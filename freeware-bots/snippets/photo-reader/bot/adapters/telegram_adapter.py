"""Telegram adapter (python-telegram-bot v22.8 from the library source tree).

Status: the library now imports on the box (httpx 0.28.1 present). Tested
OFFLINE only: the Application is built with a placeholder token and the two
handlers are driven with stand-in Update objects; nothing is sent to Telegram.
It has NOT been run against the real Telegram service. The real token comes
only from the env var named in config telegram.token_env."""
import asyncio
import os

from . import import_library, require_env

UNTESTED = True  # never connected to the real Telegram service

MAX_REPLY = 4000


class TelegramAdapter:
    name = "telegram"

    def __init__(self, bot, env=None):
        env = os.environ if env is None else env
        self.bot = bot
        self.tg = import_library(bot.cfg, "telegram")
        self.token = require_env(env, bot.cfg["telegram"]["token_env"])

    async def on_text(self, update, context):
        r = await asyncio.to_thread(self.bot.handle_text, "telegram", update.effective_user.id, update.message.text)
        await update.message.reply_text(r["text"][:MAX_REPLY])

    async def on_photo(self, update, context):
        f = await update.message.photo[-1].get_file()
        data = bytes(await f.download_as_bytearray())
        r = await asyncio.to_thread(self.bot.handle_photo, "telegram", update.effective_user.id, data, "telegram.jpg")
        await update.message.reply_text(r["text"][:MAX_REPLY])

    def build_app(self):
        """Build the PTB Application. Makes no network call by itself."""
        from telegram.ext import Application, MessageHandler, filters

        app = Application.builder().token(self.token).build()
        app.add_handler(MessageHandler(filters.PHOTO, self.on_photo))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))
        return app

    def start(self, background=False):
        self.build_app().run_polling()

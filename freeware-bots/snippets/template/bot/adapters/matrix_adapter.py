"""Matrix adapter. UNTESTED STUB: matrix-nio 0.26.0 is in the library source
tree but cannot be imported on the box: aiohttp and aiofiles are now present,
but aiohttp-socks, h2, jsonschema, unpaddedbase64 and pycryptodome are not. Homeserver, user id and access token come only from the
env vars named in config.matrix."""
import asyncio
import os

from . import import_library, require_env

UNTESTED = True


class MatrixAdapter:
    name = "matrix"

    def __init__(self, bot, env=None):
        env = os.environ if env is None else env
        m = bot.cfg["matrix"]
        self.bot = bot
        self.nio = import_library(bot.cfg, "nio")
        self.homeserver = require_env(env, m["homeserver_env"])
        self.user_id = require_env(env, m["user_id_env"])
        self.token = require_env(env, m["access_token_env"])

    def start(self, background=False):
        asyncio.run(self._run())

    async def _run(self):
        nio, bot = self.nio, self.bot
        client = nio.AsyncClient(self.homeserver, self.user_id)
        client.access_token = self.token

        async def reply(room, text):
            await client.room_send(room.room_id, "m.room.message", {"msgtype": "m.text", "body": text})

        async def on_text(room, event):
            if event.sender == self.user_id:
                return
            r = await asyncio.to_thread(bot.handle_text, "matrix", event.sender, event.body)
            await reply(room, r["text"])

        async def on_image(room, event):
            resp = await client.download(event.url)
            r = await asyncio.to_thread(bot.handle_photo, "matrix", event.sender, resp.body, event.body)
            await reply(room, r["text"])

        client.add_event_callback(on_text, nio.RoomMessageText)
        client.add_event_callback(on_image, nio.RoomMessageImage)
        await client.sync_forever(timeout=30000)

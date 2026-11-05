"""Discord adapter. UNTESTED STUB: discord.py v2.7.1 is in the library source
tree but cannot be imported on the box: aiohttp is now present, but discord.py
imports the 'audioop' module, which Python 3.13 removed (the 'audioop-lts'
package would provide it; not present). Token comes only from the env var named in config discord.token_env."""
import asyncio
import os

from . import import_library, require_env

UNTESTED = True


class DiscordAdapter:
    name = "discord"

    def __init__(self, bot, env=None):
        env = os.environ if env is None else env
        self.bot = bot
        self.discord = import_library(bot.cfg, "discord")
        self.token = require_env(env, bot.cfg["discord"]["token_env"])

    def start(self, background=False):
        discord, bot = self.discord, self.bot
        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)

        @client.event
        async def on_message(message):
            if message.author == client.user:
                return
            images = [a for a in message.attachments if (a.content_type or "").startswith("image/")]
            if images:
                data = await images[0].read()
                r = await asyncio.to_thread(bot.handle_photo, "discord", message.author.id, data, images[0].filename)
            elif message.content:
                r = await asyncio.to_thread(bot.handle_text, "discord", message.author.id, message.content)
            else:
                return
            await message.channel.send(r["text"][:1900])

        client.run(self.token)

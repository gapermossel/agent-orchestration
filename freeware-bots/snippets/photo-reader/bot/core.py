"""Bot core: ties config, logging, memory, the Ollama client and a job together.
Channel adapters call Bot.handle_text / Bot.handle_photo and send back reply["text"]."""
import time

from . import __version__, config as config_mod, logging_setup
from .config import resolve_path
from .jobs import load_job
from .memory import Memory
from .ollama_client import OllamaClient


class Bot:
    def __init__(self, cfg=None, env=None):
        self.cfg = cfg or config_mod.load(env=env)
        self.log = logging_setup.setup(self.cfg, env)
        self.started = time.time()
        mpath = self.cfg["memory"]["path"]
        self.memory = Memory(mpath if mpath == ":memory:" else resolve_path(self.cfg, mpath))
        o = self.cfg["ollama"]
        self.ollama = OllamaClient(o["base_url"], o.get("timeout_s", 120))
        self.job = load_job(self.cfg.get("job", "bot.jobs.chat:ChatJob"))(self)
        self.log.info("bot %s v%s started, job=%s, ollama=%s", self.cfg["bot_name"], __version__, self.job.name, o["base_url"])

    def health(self):
        return {
            "status": "ok",
            "bot": self.cfg["bot_name"],
            "version": __version__,
            "template_version": self.cfg.get("template_version", __version__),
            "job": self.job.name,
            "uptime_s": round(time.time() - self.started, 1),
            "memory_messages": self.memory.count(),
            "ollama": self.ollama.status(),
            "job_health": self.job.health(),
        }

    def handle_text(self, channel, user, text):
        self.log.info("text in channel=%s user=%s len=%d", channel, user, len(text))
        reply = self.job.handle_text(channel, user, text)
        self.memory.add(channel, user, "user", text)
        self.memory.add(channel, user, "assistant", reply.get("text", ""))
        return reply

    def handle_photo(self, channel, user, data, filename=None):
        self.log.info("photo in channel=%s user=%s bytes=%d", channel, user, len(data))
        reply = self.job.handle_photo(channel, user, data, filename)
        self.memory.add(channel, user, "user", f"[photo {filename or ''} {len(data)} bytes]")
        self.memory.add(channel, user, "assistant", reply.get("text", ""))
        return reply

    def close(self):
        self.memory.close()
        for h in list(self.log.handlers):
            h.close()
            self.log.removeHandler(h)

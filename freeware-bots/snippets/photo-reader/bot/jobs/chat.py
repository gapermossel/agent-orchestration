from ..ollama_client import OllamaError
from .base import Job


class ChatJob(Job):
    """Default template job: answer text with the local Ollama chat model,
    using recent history from memory."""
    name = "chat"

    def health(self):
        return {"chat_model": self.bot.cfg["ollama"]["chat_model"]}

    def handle_text(self, channel, user, text):
        cfg = self.bot.cfg
        history = self.bot.memory.recent(channel, user, cfg["memory"]["history_turns"])
        try:
            answer = self.bot.ollama.chat(cfg["ollama"]["chat_model"], history + [{"role": "user", "content": text}])
            status = "ok"
        except OllamaError as e:
            self.bot.log.warning("chat failed: %s", e)
            answer, status = f"Local model unavailable: {e}", "model_unavailable"
        return {"text": answer, "status": status}

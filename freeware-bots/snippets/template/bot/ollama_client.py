"""Minimal Ollama REST client (urllib, no extra packages).

Default base URL is http://127.0.0.1:11434. To use Ollama on the Windows host
instead, set ollama.base_url in config.json or the BOT_OLLAMA_URL environment
variable, e.g. http://<windows-host-ip>:11434 (Ollama there must listen on that
interface: OLLAMA_HOST=0.0.0.0)."""
import base64
import json
import urllib.error
import urllib.request


class OllamaError(Exception):
    pass


class OllamaUnavailable(OllamaError):
    pass


class OllamaClient:
    def __init__(self, base_url="http://127.0.0.1:11434", timeout_s=120):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def _req(self, method, path, body=None, timeout=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout_s) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            raise OllamaError(f"HTTP {e.code} from {path}: {e.read().decode(errors='replace')[:300]}")
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            raise OllamaUnavailable(f"Ollama not reachable at {self.base_url}: {e}")

    def version(self):
        return self._req("GET", "/api/version", timeout=5).get("version")

    def models(self):
        return [m.get("name") for m in self._req("GET", "/api/tags", timeout=5).get("models", [])]

    def has_model(self, name):
        names = self.models()
        if name in names:
            return True
        return ":" not in name and f"{name}:latest" in names

    def status(self):
        try:
            return {"reachable": True, "url": self.base_url, "version": self.version(), "models": self.models()}
        except OllamaError as e:
            return {"reachable": False, "url": self.base_url, "error": str(e)}

    def chat(self, model, messages):
        r = self._req("POST", "/api/chat", {"model": model, "messages": messages, "stream": False})
        return r.get("message", {}).get("content", "")

    def generate(self, model, prompt, images=None, think=None, timeout_s=None, options=None):
        """Return the model's answer text. The full Ollama reply (timings,
        token counts, any 'thinking' text) is kept in self.last_response.
        think=False asks a thinking model to skip its reasoning step."""
        body = {"model": model, "prompt": prompt, "stream": False}
        if images:
            body["images"] = [base64.b64encode(i).decode() if isinstance(i, bytes) else i for i in images]
        if think is not None:
            body["think"] = bool(think)
        if options:
            body["options"] = options
        self.last_response = self._req("POST", "/api/generate", body, timeout=timeout_s)
        return self.last_response.get("response", "")

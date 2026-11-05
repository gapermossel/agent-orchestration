"""Test helpers. FakeOllama is a FAKE stand-in server that speaks the Ollama REST
shape; it proves this code's request/response handling, NOT a real model."""
import atexit
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot import config as config_mod  # noqa: E402


class FakeOllama:
    def __init__(self, models=("qwen3:8b",), reply="fake-reply"):
        self.models, self.reply, self.requests = list(models), reply, []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _j(self, obj):
                b = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                outer.requests.append(("GET", self.path, None))
                if self.path == "/api/version":
                    return self._j({"version": "fake-0.0"})
                if self.path == "/api/tags":
                    return self._j({"models": [{"name": m} for m in outer.models]})
                self.send_response(404); self.end_headers()

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append(("POST", self.path, body))
                if body.get("model") not in outer.models:
                    b = json.dumps({"error": f"model '{body.get('model')}' not found"}).encode()
                    self.send_response(404); self.send_header("Content-Length", str(len(b))); self.end_headers()
                    return self.wfile.write(b)
                if self.path == "/api/chat":
                    return self._j({"message": {"role": "assistant", "content": outer.reply}})
                if self.path == "/api/generate":
                    return self._j({"response": outer.reply})
                self.send_response(404); self.end_headers()

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def close(self):
        self.httpd.shutdown(); self.httpd.server_close()


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def tracked_tmp(prefix="bottest-"):
    """A temp dir that is removed when the test process exits (v0.1.2: no more
    leftover /tmp/bottest-* dirs)."""
    d = tempfile.mkdtemp(prefix=prefix)
    atexit.register(shutil.rmtree, d, True)
    return d


def test_cfg(ollama_url=None, **over):
    tmp = tracked_tmp("bottest-")
    cfg = config_mod.load(path=os.path.join(tmp, "none.json"), env={})
    cfg["data_dir"] = tmp
    cfg["memory"]["path"] = os.path.join(tmp, "mem.sqlite3")
    cfg["web"]["port"] = 0
    cfg["log_level"] = "WARNING"
    # Never let a unit test reach a real Ollama by accident: default to a closed port.
    cfg["ollama"]["base_url"] = ollama_url or f"http://127.0.0.1:{free_port()}"
    cfg["ollama"]["timeout_s"] = 10
    for k, v in over.items():
        cfg[k] = v
    return cfg

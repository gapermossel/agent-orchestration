"""FROZEN COPY of bot/adapters/web.py as shipped in v0.1.1 (no web UI).
Used only by tests/test_web_api_unchanged.py to prove the JSON API did not change.
Do not edit."""
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def make_handler(bot):
    max_body = bot.cfg["web"].get("max_body_bytes", 10 * 1024 * 1024)

    class Handler(BaseHTTPRequestHandler):
        server_version = "freeware-bot"

        def log_message(self, fmt, *args):
            bot.log.debug("web %s", fmt % args)

        def _send(self, code, obj):
            body = json.dumps(obj, ensure_ascii=False, indent=2).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > max_body:
                raise ValueError(f"body too large ({n} > {max_body} bytes)")
            return self.rfile.read(n)

        def do_GET(self):
            path = urllib.parse.urlparse(self.path).path
            if path == "/health":
                return self._send(200, bot.health())
            self._send(404, {"error": "not found"})

        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            try:
                raw = self._body()
                if u.path == "/message":
                    msg = json.loads(raw or b"{}")
                    if not isinstance(msg.get("text"), str):
                        return self._send(400, {"error": "JSON field 'text' required"})
                    return self._send(200, bot.handle_text("web", msg.get("user", "anon"), msg["text"]))
                if u.path == "/photo":
                    if not raw:
                        return self._send(400, {"error": "empty body; send image bytes"})
                    user = q.get("user", ["anon"])[0]
                    name = q.get("filename", [None])[0]
                    return self._send(200, bot.handle_photo("web", user, raw, name))
                self._send(404, {"error": "not found"})
            except ValueError as e:
                self._send(413 if "too large" in str(e) else 400, {"error": str(e)})
            except Exception as e:  # keep serving
                bot.log.exception("web handler error")
                self._send(500, {"error": f"internal error: {type(e).__name__}"})

    return Handler


class WebAdapter:
    name = "web"

    def __init__(self, bot, env=None):
        self.bot = bot
        w = bot.cfg["web"]
        self.httpd = ThreadingHTTPServer((w["host"], int(w["port"])), make_handler(bot))
        self.thread = None

    @property
    def port(self):
        return self.httpd.server_address[1]

    def start(self, background=False):
        self.bot.log.info("web adapter on http://%s:%s", *self.httpd.server_address[:2])
        if background:
            self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.thread.start()
        else:
            self.httpd.serve_forever()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

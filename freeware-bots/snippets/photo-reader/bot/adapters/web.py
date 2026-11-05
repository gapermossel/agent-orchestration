"""Web/HTTP adapter (standard library http.server only). Tested on the box.

GET  /  (or /index.html)  -> small self-contained HTML page (web UI, v0.1.2):
                             photo upload -> POST /photo, text box -> POST /message,
                             shows the JSON reply. Inline CSS/JS only; no CDN or
                             external assets.
GET  /health              -> JSON health report
POST /message  JSON {"user": "...", "text": "..."}  -> JSON reply
POST /photo    raw image bytes (any image/* content type), ?user=...&filename=...
               -> JSON reply

The JSON API (/health, /message, /photo) is unchanged from v0.1.1.

Bind address: config web.host / web.port (or env BOT_WEB_HOST / BOT_WEB_PORT).
Default 127.0.0.1. Any local address works, e.g. a Tailscale 100.x address,
0.0.0.0, or an IPv6 address such as fd7a:... (IPv6 is detected by the ':').
There is NO login: anyone who can reach the address can use the bot.
"""
import html
import json
import re
import socket
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import __version__

# The JSON endpoints the page calls. Tests check the page uses exactly these.
API_GET = ("/health",)
API_POST = ("/message", "/photo")
UI_PATHS = ("/", "/index.html")

# Browser security headers for the HTML page only (JSON replies are unchanged).
UI_CSP = ("default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
          "connect-src 'self'; img-src 'self' blob:; base-uri 'none'; form-action 'none'; "
          "frame-ancestors 'none'")

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{BOT}}</title>
<style>
  :root { color-scheme: light dark; --fg:#1b1f23; --bg:#f6f7f9; --card:#fff; --mute:#5c6670; --line:#d8dde2; --acc:#2f6fdf; --err:#b3261e; --ok:#1e7d32; }
  @media (prefers-color-scheme: dark) { :root { --fg:#e6e8ea; --bg:#15181b; --card:#1f2327; --mute:#9aa4ad; --line:#333a40; --acc:#7aa7ff; --err:#ff8a80; --ok:#81c784; } }
  * { box-sizing: border-box; }
  body { margin:0; font:16px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color:var(--fg); background:var(--bg); }
  main { max-width: 860px; margin: 0 auto; padding: 16px; }
  h1 { font-size: 1.35rem; margin: 4px 0 2px; }
  h2 { font-size: 1.05rem; margin: 0 0 10px; }
  h3 { font-size: .95rem; margin: 14px 0 4px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px; margin:12px 0; }
  .mute { color:var(--mute); font-size:.9rem; }
  .row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
  input[type=text] { flex:1 1 260px; padding:8px 10px; font:inherit; border:1px solid var(--line); border-radius:8px; background:transparent; color:inherit; }
  button { padding:8px 16px; font:inherit; border:0; border-radius:8px; background:var(--acc); color:#fff; cursor:pointer; }
  button:disabled { opacity:.55; cursor:wait; }
  pre { white-space:pre-wrap; word-break:break-word; background:var(--bg); border:1px solid var(--line); border-radius:8px; padding:10px; margin:4px 0; font:14px/1.4 ui-monospace, Menlo, Consolas, monospace; }
  .status { font-weight:600; }
  .working { color:var(--acc); }
  .error { color:var(--err); font-weight:600; }
  .good { color:var(--ok); }
  table { border-collapse:collapse; font-size:.9rem; }
  td { padding:2px 12px 2px 0; vertical-align:top; }
  img.preview { max-width:220px; max-height:160px; border-radius:6px; border:1px solid var(--line); display:block; margin-top:8px; }
  details { margin-top:10px; }
</style>
</head>
<body data-max-bytes="{{MAX}}">
<main>
  <h1>{{BOT}}</h1>
  <div class="mute">version {{VERSION}} &middot; <span id="health">checking&hellip;</span></div>

  <section class="card">
    <h2>Send a photo</h2>
    <form id="photo-form" action="/photo" method="post" class="row">
      <input id="photo-file" name="photo" type="file" accept="image/*" required>
      <button id="photo-send" type="submit">Upload photo</button>
    </form>
    <div class="mute">Up to <span id="max-mb"></span> MB. Reading a photo can take a minute or more.</div>
    <img id="photo-preview" class="preview" alt="" hidden>
  </section>

  <section class="card">
    <h2>Send a message</h2>
    <form id="message-form" action="/message" method="post" class="row">
      <input id="message-text" name="text" type="text" placeholder="Type a message" autocomplete="off" required>
      <button id="message-send" type="submit">Send</button>
    </form>
  </section>

  <section class="card" id="reply-card" hidden>
    <h2>Reply</h2>
    <div id="reply"></div>
  </section>
</main>
<script>
"use strict";
(function () {
  // All server, OCR and model text is put on the page with textContent only,
  // so it is always shown as plain text and never run as HTML.
  var MAX = parseInt(document.body.dataset.maxBytes, 10) || 10485760;
  var TIMEOUT_MS = 20 * 60 * 1000;   // a CPU description can take minutes
  var USER = "web-ui";
  var busy = false;
  var $ = function (id) { return document.getElementById(id); };
  $("max-mb").textContent = (MAX / 1048576).toFixed(MAX < 1048576 ? 2 : 0);

  function el(tag, text, cls) {
    var e = document.createElement(tag);
    if (text !== undefined && text !== null) e.textContent = String(text);
    if (cls) e.className = cls;
    return e;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function secs(v) { return (typeof v === "number") ? v.toFixed(2) + " s" : ""; }
  function addRow(tbl, k, v) {
    if (v === undefined || v === null || v === "") return;
    var tr = el("tr"); tr.appendChild(el("td", k, "mute")); tr.appendChild(el("td", v)); tbl.appendChild(tr);
  }

  function setBusy(on) {
    busy = on;
    ["photo-send", "message-send"].forEach(function (id) { $(id).disabled = on; });
  }

  function working(label) {
    var out = $("reply"); clear(out); $("reply-card").hidden = false;
    var line = el("div", "", "working"); out.appendChild(line);
    var t0 = Date.now();
    function tick() { line.textContent = "working\u2026 " + label + " (" + Math.round((Date.now() - t0) / 1000) + " s)"; }
    tick();
    var timer = setInterval(tick, 1000);
    return function () { clearInterval(timer); return (Date.now() - t0) / 1000; };
  }

  function part(title, p) {
    var box = el("div");
    box.appendChild(el("h3", title));
    if (!p || typeof p !== "object") { box.appendChild(el("div", "(not in reply)", "mute")); return box; }
    var st = el("div", "status: " + (p.status || "?"), "status " + (p.status === "ok" ? "good" : "error"));
    box.appendChild(st);
    if (p.status === "ok") {
      box.appendChild(el("pre", (p.text === "" ? "(no text found)" : p.text)));
    } else if (p.reason || p.error) {
      box.appendChild(el("pre", p.reason || p.error, "error"));
    }
    var tbl = el("table");
    addRow(tbl, "engine", p.engine);
    addRow(tbl, "model", p.model);
    if (typeof p.think === "boolean") addRow(tbl, "think", String(p.think));
    addRow(tbl, "time", secs(p.elapsed_s));
    function pairs(obj, names) {   // only the numbers that are really there
      var out = [];
      names.forEach(function (n) { if (typeof obj[n[0]] === "number") out.push(n[1] + " " + n[2](obj[n[0]])); });
      return out.join(", ");
    }
    var num = function (v) { return String(v); };
    if (p.ollama_timing_s && typeof p.ollama_timing_s === "object") {
      addRow(tbl, "model timing", pairs(p.ollama_timing_s, [["total", "total", secs], ["load", "load", secs],
        ["prompt_eval", "prompt", secs], ["eval", "output", secs]]));
    }
    if (p.tokens && typeof p.tokens === "object") {
      addRow(tbl, "tokens", pairs(p.tokens, [["prompt", "prompt", num], ["output", "output", num]]));
    }
    if (tbl.firstChild) box.appendChild(tbl);
    return box;
  }

  function render(httpStatus, data, rawText, clientSecs) {
    var out = $("reply"); clear(out);
    var head = el("div", "", "status");
    head.textContent = "HTTP " + httpStatus + " \u00b7 " + clientSecs.toFixed(1) + " s";
    out.appendChild(head);
    if (data === null) {
      out.appendChild(el("div", "The server did not send JSON.", "error"));
      out.appendChild(el("pre", rawText || "(empty reply)"));
      return;
    }
    if (httpStatus >= 400 || data.error) {
      out.appendChild(el("div", "Error: " + (data.error || ("HTTP " + httpStatus)), "error"));
    }
    if (data.status) out.appendChild(el("div", "status: " + data.status, "status " + (data.status === "ok" ? "good" : "error")));
    if ("ocr" in data || "description" in data) {
      var meta = el("table");
      addRow(meta, "image type", data.image_type);
      addRow(meta, "bytes", data.bytes);
      addRow(meta, "mode", data.mode);
      addRow(meta, "total time (server)", secs(data.elapsed_s));
      out.appendChild(meta);
      if ("ocr" in data) out.appendChild(part("Text in photo (OCR)", data.ocr));
      if ("description" in data) out.appendChild(part("Description", data.description));
    } else if (typeof data.text === "string") {
      out.appendChild(el("pre", data.text));
    }
    var det = el("details"); det.appendChild(el("summary", "Raw JSON reply"));
    det.appendChild(el("pre", JSON.stringify(data, null, 2))); out.appendChild(det);
  }

  function renderFailure(err, clientSecs) {
    var out = $("reply"); clear(out);
    var msg = (err && err.name === "AbortError")
      ? "No reply after " + Math.round(TIMEOUT_MS / 60000) + " minutes; gave up waiting. The bot may still be working."
      : "Could not reach the bot: " + (err && err.message ? err.message : String(err)) +
        ". Check it is running and that the file is under the size limit.";
    out.appendChild(el("div", msg, "error"));
    out.appendChild(el("div", "after " + clientSecs.toFixed(1) + " s", "mute"));
  }

  function send(url, opts, label) {
    if (busy) return;
    setBusy(true);
    var done = working(label);
    var ctl = ("AbortController" in window) ? new AbortController() : null;
    var timer = ctl ? setTimeout(function () { ctl.abort(); }, TIMEOUT_MS) : null;
    if (ctl) opts.signal = ctl.signal;
    var status = 0;
    fetch(url, opts).then(function (r) { status = r.status; return r.text(); })
      .then(function (txt) {
        var data = null;
        try { data = JSON.parse(txt); if (!data || typeof data !== "object") data = null; } catch (e) { data = null; }
        render(status, data, txt, done());
      })
      .catch(function (err) { renderFailure(err, done()); })
      .then(function () { if (timer) clearTimeout(timer); setBusy(false); });
  }

  $("photo-file").addEventListener("change", function () {
    var f = this.files && this.files[0], img = $("photo-preview");
    if (img.src) { URL.revokeObjectURL(img.src); img.removeAttribute("src"); }
    img.hidden = true;
    if (f && /^image\//.test(f.type)) { img.src = URL.createObjectURL(f); img.hidden = false; }
  });

  $("photo-form").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var f = $("photo-file").files[0];
    if (!f) return;
    if (f.size > MAX) {
      $("reply-card").hidden = false; clear($("reply"));
      $("reply").appendChild(el("div", "That file is " + f.size + " bytes; the limit is " + MAX + " bytes.", "error"));
      return;
    }
    var url = "/photo?user=" + encodeURIComponent(USER) + "&filename=" + encodeURIComponent(f.name);
    send(url, { method: "POST", body: f, headers: { "Content-Type": f.type || "application/octet-stream" } },
         "reading " + f.name);
  });

  $("message-form").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var t = $("message-text").value;
    if (!t.trim()) return;
    send("/message", { method: "POST", body: JSON.stringify({ user: USER, text: t }),
                       headers: { "Content-Type": "application/json" } }, "waiting for reply");
  });

  fetch("/health").then(function (r) { return r.json(); }).then(function (h) {
    var bits = ["status " + h.status];
    if (h.ollama) bits.push("model server " + (h.ollama.reachable ? "reachable" : "NOT reachable"));
    if (h.job_health && typeof h.job_health === "object") {
      Object.keys(h.job_health).forEach(function (k) {
        var v = h.job_health[k];
        if (v && typeof v === "object" && "ready" in v) bits.push(k + " " + (v.ready ? "ready" : "NOT ready"));
      });
    }
    $("health").textContent = bits.join(" \u00b7 ");
  }).catch(function () { $("health").textContent = "health check failed"; });
})();
</script>
</body>
</html>
"""


def render_page(bot, max_body):
    """The HTML page. Only the bot name and version are filled in (HTML-escaped)."""
    values = {
        "BOT": html.escape(str(bot.cfg.get("bot_name", "bot")), quote=True),
        "VERSION": html.escape(str(__version__), quote=True),
        "MAX": str(int(max_body)),
    }
    # One pass, so text inside a value (e.g. a bot name containing "{{MAX}}") is never re-filled.
    return re.sub(r"\{\{(BOT|VERSION|MAX)\}\}", lambda m: values[m.group(1)], PAGE)


def make_handler(bot):
    max_body = bot.cfg["web"].get("max_body_bytes", 10 * 1024 * 1024)
    page = render_page(bot, max_body).encode("utf-8")

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

        def _send_page(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", UI_CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(page)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n < 0:
                raise ValueError("bad Content-Length")
            if n > max_body:
                # Not reading the body; close the connection so the client is not left mid-upload.
                self.close_connection = True
                raise ValueError(f"body too large ({n} > {max_body} bytes)")
            return self.rfile.read(n)

        def do_GET(self):
            path = urllib.parse.urlparse(self.path).path
            if path in UI_PATHS:
                return self._send_page()
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


class _Server4(ThreadingHTTPServer):
    daemon_threads = True


class _Server6(ThreadingHTTPServer):
    daemon_threads = True
    address_family = socket.AF_INET6


def make_server(host, port, handler):
    """Bind host:port. IPv6 literals (contain ':', optional [brackets]) use AF_INET6."""
    host = str(host).strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    cls = _Server6 if ":" in host else _Server4
    return cls((host, int(port)), handler)


class WebAdapter:
    name = "web"

    def __init__(self, bot, env=None):
        self.bot = bot
        w = bot.cfg["web"]
        self.httpd = make_server(w["host"], w["port"], make_handler(bot))
        self.thread = None

    @property
    def host(self):
        return self.httpd.server_address[0]

    @property
    def port(self):
        return self.httpd.server_address[1]

    @property
    def url(self):
        h = self.host
        return f"http://[{h}]:{self.port}/" if ":" in h else f"http://{h}:{self.port}/"

    def start(self, background=False):
        self.bot.log.info("web adapter on %s (web UI at /, API: /health /message /photo)", self.url)
        if self.host not in ("127.0.0.1", "::1", "localhost"):
            self.bot.log.warning("web adapter bound to %s: anyone who can reach this address can use the bot (no login)", self.host)
        if background:
            self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.thread.start()
        else:
            self.httpd.serve_forever()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

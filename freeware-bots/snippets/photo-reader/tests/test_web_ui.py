"""Web UI page (GET /): served, self-contained, wired to the real API paths,
and safe with hostile text. The Node-driven tests run the page's own script in
a stand-in DOM (tests/ui_harness.js, not a browser) and are skipped if `node`
is not on PATH."""
import html
import json
import re
import shutil
import socket
import subprocess
import unittest
import urllib.request

from tests.helpers import ROOT, FakeOllama, test_cfg
from bot import config as config_mod
from bot.core import Bot
from bot.adapters.web import WebAdapter, API_GET, API_POST, render_page

HARNESS = ROOT / "tests" / "ui_harness.js"


def get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.status, dict(r.headers), r.read().decode("utf-8")


class Served:
    def __init__(self, **cfg_over):
        self.fake = FakeOllama(reply=cfg_over.pop("reply", "fake-reply"))
        cfg = test_cfg(self.fake.url)
        for k, v in cfg_over.items():
            cfg[k] = v
        self.bot = Bot(cfg)
        self.web = WebAdapter(self.bot); self.web.start(background=True)
        self.base = f"http://127.0.0.1:{self.web.port}"

    def close(self):
        self.web.stop(); self.fake.close(); self.bot.close()


class PageTests(unittest.TestCase):
    def setUp(self):
        self.s = Served()

    def tearDown(self):
        self.s.close()

    def test_get_root_serves_html_with_both_forms(self):
        for path in ("/", "/index.html", "/?x=1"):
            code, hdr, page = get(self.s.base + path)
            self.assertEqual(code, 200)
            self.assertEqual(hdr["Content-Type"], "text/html; charset=utf-8")
            self.assertIn("default-src 'none'", hdr["Content-Security-Policy"])
            self.assertEqual(hdr["X-Content-Type-Options"], "nosniff")
            self.assertTrue(page.startswith("<!DOCTYPE html>"))
            self.assertRegex(page, r'<form id="photo-form" action="/photo" method="post"')
            self.assertRegex(page, r'<input id="photo-file" name="photo" type="file" accept="image/\*"')
            self.assertRegex(page, r'<form id="message-form" action="/message" method="post"')
            self.assertRegex(page, r'<input id="message-text" name="text" type="text"')
            self.assertIn("working\\u2026", page)  # the busy state text

    def test_self_contained_no_external_assets(self):
        page = get(self.s.base + "/")[2]
        self.assertNotRegex(page, r"https?://", "no absolute URLs at all")
        self.assertNotRegex(page, r"""(src|href)\s*=\s*["']?//""")
        self.assertNotIn("<link", page)
        self.assertNotRegex(page, r"<script[^>]*\ssrc=")
        self.assertNotIn("@import", page)
        self.assertNotRegex(page, r"url\(")
        self.assertEqual(len(re.findall(r"<script>", page)), 1)
        self.assertEqual(len(re.findall(r"<style>", page)), 1)

    def test_page_endpoints_match_api(self):
        page = get(self.s.base + "/")[2]
        used = set(re.findall(r'''(?:fetch\(|action=|url = )\s*["'](/[a-z.]*)''', page))
        self.assertEqual(used, set(API_GET) | set(API_POST))
        self.assertIn('"/photo?user="', page)
        self.assertIn('send("/message"', page)
        self.assertIn('fetch("/health")', page)

    def test_page_never_uses_html_injection_apis(self):
        page = get(self.s.base + "/")[2]
        script = re.search(r"<script>([\s\S]*)</script>", page).group(1)
        for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
            self.assertNotIn(bad, script)
        self.assertIn("textContent", script)

    def test_upload_limit_shown_to_page(self):
        page = get(self.s.base + "/")[2]
        self.assertIn('data-max-bytes="%d"' % self.s.bot.cfg["web"]["max_body_bytes"], page)

    def test_api_still_works_next_to_page(self):
        req = urllib.request.Request(self.s.base + "/message", data=json.dumps({"text": "hi"}).encode(),
                                     headers={"Content-Type": "application/json"})
        self.assertEqual(json.loads(urllib.request.urlopen(req, timeout=10).read())["text"], "fake-reply")


class EscapingTests(unittest.TestCase):
    def test_bot_name_and_version_are_escaped(self):
        bad = '<script>alert("x")</script>&'
        s = Served(bot_name=bad)
        try:
            page = get(s.base + "/")[2]
        finally:
            s.close()
        self.assertNotIn(bad, page)
        self.assertIn(html.escape(bad, quote=True), page)
        self.assertEqual(page.count("<script>"), 1)

    def test_render_page_fills_placeholders_once(self):
        class B:
            cfg = {"bot_name": "{{VERSION}}{{MAX}}<x>"}
        page = render_page(B(), 123)
        self.assertIn("<title>{{VERSION}}{{MAX}}&lt;x&gt;</title>", page)
        self.assertIn('data-max-bytes="123"', page)
        self.assertNotIn("{{BOT}}", page)


class BindTests(unittest.TestCase):
    def _serve(self, host):
        cfg = test_cfg()
        cfg["web"]["host"] = host
        bot = Bot(cfg)
        web = WebAdapter(bot); web.start(background=True)
        return bot, web

    def _check(self, connect_host, port):
        h = f"[{connect_host}]" if ":" in connect_host else connect_host
        code, hdr, page = get(f"http://{h}:{port}/")
        self.assertEqual(code, 200)
        code, hdr, body = get(f"http://{h}:{port}/health")
        self.assertEqual(json.loads(body)["status"], "ok")

    def test_default_host_is_loopback(self):
        self.assertEqual(config_mod.DEFAULTS["web"]["host"], "127.0.0.1")
        for name in ("config.json", "config.example.json"):
            p = ROOT / "config" / name
            if p.exists():
                self.assertEqual(json.loads(p.read_text())["web"]["host"], "127.0.0.1", name)

    def test_env_override_host_and_port(self):
        cfg = config_mod.load(path="/nonexistent.json", env={"BOT_WEB_HOST": "198.51.100.9", "BOT_WEB_PORT": "8123"})
        self.assertEqual((cfg["web"]["host"], cfg["web"]["port"]), ("198.51.100.9", 8123))

    def test_bind_non_loopback_ipv4(self):
        # Find this box's own non-loopback address without sending anything
        # (a UDP connect() only picks a route; no packet is sent).
        try:
            u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            u.connect(("192.0.2.1", 9)); ip = u.getsockname()[0]; u.close()
        except OSError as e:
            self.skipTest(f"no non-loopback IPv4 route: {e}")
        if ip.startswith("127.") or ip == "0.0.0.0":
            self.skipTest("only loopback available")
        bot, web = self._serve(ip)
        try:
            self.assertEqual(web.host, ip)
            self.assertEqual(web.url, f"http://{ip}:{web.port}/")
            self._check(ip, web.port)
            print(f"\n  bound and served on non-loopback {ip}:{web.port}")
        finally:
            web.stop(); bot.close()

    def test_bind_all_interfaces(self):
        bot, web = self._serve("0.0.0.0")
        try:
            self._check("127.0.0.1", web.port)
        finally:
            web.stop(); bot.close()

    def test_bind_ipv6(self):
        if not socket.has_ipv6:
            self.skipTest("no IPv6 in this Python")
        try:
            t = socket.socket(socket.AF_INET6); t.bind(("::1", 0)); t.close()
        except OSError as e:
            self.skipTest(f"::1 not available: {e}")
        for host in ("::1", "[::1]"):
            bot, web = self._serve(host)
            try:
                self.assertEqual(web.url, f"http://[::1]:{web.port}/")
                self._check("::1", web.port)
            finally:
                web.stop(); bot.close()


@unittest.skipUnless(shutil.which("node"), "node not on PATH (page-script tests need it)")
class PageScriptTests(unittest.TestCase):
    """Runs the page's own JavaScript (stand-in DOM, real fetch to this server)."""

    def run_ui(self, base, *args):
        r = subprocess.run(["node", str(HARNESS), base, *args], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["html_api_used"], [])
        return out

    def test_message_reply_rendered_as_text(self):
        hostile = '<img src=x onerror=alert(1)> & <b>bold</b>'
        s = Served(reply=hostile)
        try:
            out = self.run_ui(s.base, "message", "hello <script>")
        finally:
            s.close()
        self.assertIn({"method": "POST", "url": "/message"}, out["requests"])
        self.assertIn("  <pre> " + json.dumps(hostile), out["reply_text_tree"])
        self.assertTrue(out["reply_text_tree"][1].startswith('  <div.status> "HTTP 200'))
        self.assertIn("model server reachable", out["health_line"])

    def test_photo_upload_goes_to_photo_endpoint(self):
        import tempfile, os
        s = Served()
        fd, p = tempfile.mkstemp(suffix=".png", prefix="bottest-ui-")
        os.write(fd, b"\x89PNG\r\n\x1a\n...."); os.close(fd)
        try:
            out = self.run_ui(s.base, "photo", p, "image/png")
        finally:
            s.close(); os.unlink(p)
        self.assertIn({"method": "POST", "url": "/photo?user=web-ui&filename=" + os.path.basename(p)}, out["requests"])
        self.assertTrue(out["preview_shown"])
        self.assertIn('  <div.status.error> "status: unsupported"', out["reply_text_tree"])

    def test_4xx_reply_shown_as_error(self):
        import tempfile, os
        s = Served(web={"enabled": True, "host": "127.0.0.1", "port": 0, "max_body_bytes": 10})
        fd, p = tempfile.mkstemp(suffix=".png", prefix="bottest-ui-")
        os.write(fd, b"x" * 50); os.close(fd)
        try:
            out = self.run_ui(s.base, "photo", p, "image/png")
        finally:
            s.close(); os.unlink(p)
        # The page refuses before uploading: file is over the limit it was given.
        self.assertEqual([r for r in out["requests"] if r["method"] == "POST"], [])
        self.assertIn("the limit is 10 bytes", " ".join(out["reply_text_tree"]))

    def test_5xx_reply_shown_as_error(self):
        s = Served()
        def boom(*a, **k):
            raise RuntimeError("secret detail")
        s.bot.handle_text = boom
        try:
            out = self.run_ui(s.base, "message", "hi")
        finally:
            s.close()
        tree = "\n".join(out["reply_text_tree"])
        self.assertIn('HTTP 500', tree)
        self.assertIn('Error: internal error: RuntimeError', tree)
        self.assertNotIn("secret detail", tree)

    def _run_with_api_base(self, api_base, *args):
        import os
        s = Served()
        try:
            r = subprocess.run(["node", str(HARNESS), s.base, *args], capture_output=True, text=True,
                               timeout=120, env={**os.environ, "UI_API_BASE": api_base})
        finally:
            s.close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["html_api_used"], [])
        return out

    def test_bot_unreachable_shown_as_error(self):
        from tests.helpers import free_port
        out = self._run_with_api_base(f"http://127.0.0.1:{free_port()}", "message", "hi")
        tree = "\n".join(out["reply_text_tree"])
        self.assertIn("Could not reach the bot", tree)
        self.assertEqual(out["health_line"], "health check failed")

    def test_non_json_error_page_shown_as_text(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading

        class Proxy(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass
            def _reply(self):
                b = b"<h1>502 Bad Gateway</h1>"
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    self.rfile.read(n)
                self.send_response(502); self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
            do_GET = do_POST = _reply

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            out = self._run_with_api_base(f"http://127.0.0.1:{srv.server_address[1]}", "message", "hi")
        finally:
            srv.shutdown(); srv.server_close()
        tree = out["reply_text_tree"]
        self.assertTrue(tree[1].startswith('  <div.status> "HTTP 502'), tree)
        self.assertIn('  <div.error> "The server did not send JSON."', tree)
        self.assertIn('  <pre> "<h1>502 Bad Gateway</h1>"', tree)

if __name__ == "__main__":
    unittest.main()

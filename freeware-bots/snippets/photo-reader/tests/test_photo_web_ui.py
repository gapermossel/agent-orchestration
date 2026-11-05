"""Photo-reader web page tests (FAKE tesseract + FakeOllama, labelled).

They prove the page shows the photo reply (OCR text, description, timings,
errors) as plain text even when OCR/model output contains HTML, and that the
photo JSON reply is the same as from the frozen v0.1.1 adapter. They do NOT
prove real OCR or a real vision model (see the real-run log for that)."""
import json
import os
import shutil
import subprocess
import unittest
import urllib.request

from tests.helpers import ROOT, FakeOllama, tracked_tmp
from tests.test_photo_reader import fake_tesseract, photo_cfg, tiny_png
from tests import legacy_web_v0_1_1 as legacy
from bot.core import Bot
from bot.adapters.web import WebAdapter
from http.server import ThreadingHTTPServer
import threading

HARNESS = ROOT / "tests" / "ui_harness.js"
HOSTILE_OCR = "<b>FAKE</b> & <script>alert(1)</script>"
HOSTILE_DESC = '<img src=x onerror=alert(2)> a "sign" & more'


def _strip_times(obj):
    """Drop measured times (they differ run to run); keep everything else."""
    if isinstance(obj, dict):
        return {k: _strip_times(v) for k, v in obj.items()
                if k not in ("elapsed_s", "ollama_timing_s")}
    return obj


class PhotoServed:
    def __init__(self):
        self.fake = FakeOllama(models=["qwen3-vl:8b"], reply=HOSTILE_DESC)
        tess, _ = fake_tesseract(text=HOSTILE_OCR)
        self.bot = Bot(photo_cfg(self.fake.url, tess=tess))
        self.web = WebAdapter(self.bot); self.web.start(background=True)
        self.base = f"http://127.0.0.1:{self.web.port}"

    def close(self):
        self.web.stop(); self.bot.close(); self.fake.close()


class PhotoApiUnchangedTest(unittest.TestCase):
    def test_photo_reply_same_as_v0_1_1(self):
        s = PhotoServed()
        old = ThreadingHTTPServer(("127.0.0.1", 0), legacy.make_handler(s.bot))
        threading.Thread(target=old.serve_forever, daemon=True).start()
        try:
            out = []
            for base in (f"http://127.0.0.1:{old.server_address[1]}", s.base):
                req = urllib.request.Request(base + "/photo?user=a&filename=x.png", data=tiny_png(),
                                             headers={"Content-Type": "image/png"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    out.append((r.status, r.headers["Content-Type"], _strip_times(json.loads(r.read()))))
            self.assertEqual(out[0], out[1])
            self.assertEqual(out[1][2]["status"], "ok")
            self.assertEqual(out[1][2]["ocr"]["text"], HOSTILE_OCR)
            self.assertEqual(out[1][2]["description"]["text"], HOSTILE_DESC)
        finally:
            old.shutdown(); old.server_close(); s.close()


@unittest.skipUnless(shutil.which("node"), "node not on PATH (page-script tests need it)")
class PhotoPageScriptTest(unittest.TestCase):
    def test_photo_reply_rendered_as_text(self):
        s = PhotoServed()
        p = os.path.join(tracked_tmp("bottest-ui-"), "sign.png")
        with open(p, "wb") as f:
            f.write(tiny_png())
        try:
            r = subprocess.run(["node", str(HARNESS), s.base, "photo", p, "image/png"],
                               capture_output=True, text=True, timeout=120)
        finally:
            s.close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        tree = out["reply_text_tree"]
        self.assertEqual(out["html_api_used"], [])
        self.assertIn({"method": "POST", "url": "/photo?user=web-ui&filename=sign.png"}, out["requests"])
        self.assertIn("    <pre> " + json.dumps(HOSTILE_OCR), tree)
        self.assertIn("    <pre> " + json.dumps(HOSTILE_DESC), tree)
        joined = "\n".join(tree)
        for title in ("Text in photo (OCR)", "Description"):
            self.assertIn(json.dumps(title), joined)
        self.assertIn("qwen3-vl:8b", joined)
        # Fake Ollama sends no timing/token numbers: no empty "model timing"/"tokens" rows.
        self.assertNotIn('"model timing"', joined)
        self.assertNotIn('"tokens"', joined)
        self.assertIn("working", " ".join(out["working_states_seen"]))
        self.assertIn("ocr", out["health_line"])


if __name__ == "__main__":
    unittest.main()

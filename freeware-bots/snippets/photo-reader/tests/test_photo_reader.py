"""Photo-reader job tests.

FAKE pieces are labelled: fake_tesseract() is a shell script that imitates the
tesseract CLI, and FakeOllama imitates the Ollama API. They prove this bot's
plumbing (arguments, base64 image upload, blocked/ok handling), NOT real OCR
or a real vision model. The Real* tests use the real tools and are skipped
when those are not on the box."""
import json
import os
import shutil
import stat
import struct
import tempfile
import unittest
import urllib.request
import zlib

from tests.helpers import ROOT, FakeOllama, free_port, test_cfg, tracked_tmp
from bot.core import Bot
from bot.adapters.web import WebAdapter
from bot.jobs.photo_reader import sniff


def tiny_png():
    raw = b"\x00\xff\xff\xff"
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def fake_tesseract(langs="eng", text="FAKE OCR TEXT"):
    d = tracked_tmp("faketess-")   # removed when the test run ends
    log = os.path.join(d, "args.log")
    p = os.path.join(d, "tesseract")
    with open(p, "w") as f:
        f.write(f"""#!/bin/sh
echo "$@" >> {log}
case "$1" in
  --version) echo "tesseract 0.0-FAKE"; exit 0;;
  --list-langs) echo 'List of available languages in "/fake/" (1):'; for l in {langs}; do echo $l; done; exit 0;;
esac
[ -f "$1" ] || {{ echo "no input" >&2; exit 1; }}
echo "{text}"
""")
    os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
    return p, log


def photo_cfg(ollama_url=None, tess="tesseract-not-installed-xyz", model="qwen3-vl:8b", mode="both"):
    cfg = test_cfg(ollama_url or f"http://127.0.0.1:{free_port()}")
    cfg["job"] = "bot.jobs.photo_reader:PhotoReaderJob"
    cfg["template_version"] = "0.1.2"
    cfg["photo"] = {"mode": mode, "ocr": {"tesseract_cmd": tess}, "vision": {"model": model}}
    return cfg


class SniffTests(unittest.TestCase):
    def test_types(self):
        self.assertEqual(sniff(tiny_png()), "png")
        self.assertEqual(sniff(b"\xff\xd8\xff\xe0rest"), "jpg")
        self.assertEqual(sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "webp")
        self.assertIsNone(sniff(b"hello world"))


class PhotoReaderTests(unittest.TestCase):
    def tearDown(self):
        if hasattr(self, "bot"):
            self.bot.close()

    def test_rejects_non_image(self):
        self.bot = Bot(photo_cfg())
        self.assertEqual(self.bot.handle_photo("t", "u", b"not an image")["status"], "rejected")

    def test_blocked_when_nothing_available(self):
        self.bot = Bot(photo_cfg())
        r = self.bot.handle_photo("t", "u", tiny_png())
        self.assertEqual(r["status"], "blocked")
        self.assertIn("tesseract binary not found", r["ocr"]["reason"])
        self.assertIn("Ollama not reachable", r["description"]["reason"])
        self.assertIn("qwen3-vl:8b", r["description"]["reason"])

    def test_ocr_missing_language_data(self):
        tess, _ = fake_tesseract(langs="osd")
        self.bot = Bot(photo_cfg(tess=tess, mode="ocr"))
        r = self.bot.handle_photo("t", "u", tiny_png())
        self.assertEqual(r["ocr"]["status"], "blocked")
        self.assertIn("eng.traineddata", r["ocr"]["reason"])

    def test_ocr_plumbing_with_fake_tesseract(self):
        tess, log = fake_tesseract()
        cfg = photo_cfg(tess=tess, mode="ocr")
        cfg["photo"]["ocr"]["tessdata_dir"] = "/fake/tessdata"
        self.bot = Bot(cfg)
        r = self.bot.handle_photo("t", "u", tiny_png())
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["ocr"]["text"], "FAKE OCR TEXT")
        args = open(log).read().splitlines()[-1]
        self.assertIn("stdout -l eng --psm 3 --tessdata-dir /fake/tessdata", args)

    def test_vision_plumbing_with_fake_ollama(self):
        fake = FakeOllama(models=["qwen3-vl:8b"], reply="A fake description.")
        try:
            self.bot = Bot(photo_cfg(fake.url, mode="describe"))
            png = tiny_png()
            r = self.bot.handle_photo("t", "u", png)
            self.assertEqual((r["status"], r["description"]["text"]), ("ok", "A fake description."))
            body = fake.requests[-1][2]
            import base64
            self.assertEqual(base64.b64decode(body["images"][0]), png)
            self.assertEqual(body["model"], "qwen3-vl:8b")
            self.assertIs(body["think"], False)
            self.assertIn("elapsed_s", r["description"])
        finally:
            fake.close()

    def test_vision_model_missing(self):
        fake = FakeOllama(models=["qwen3:8b"])
        try:
            self.bot = Bot(photo_cfg(fake.url, mode="describe"))
            r = self.bot.handle_photo("t", "u", tiny_png())
            self.assertEqual(r["description"]["status"], "blocked")
            self.assertIn("vision model 'qwen3-vl:8b' not present", r["description"]["reason"])
        finally:
            fake.close()

    def test_partial_and_web_end_to_end(self):
        tess, _ = fake_tesseract()
        self.bot = Bot(photo_cfg(tess=tess))
        web = WebAdapter(self.bot); web.start(background=True)
        try:
            base = f"http://127.0.0.1:{web.port}"
            req = urllib.request.Request(base + "/photo?user=a&filename=x.png", data=tiny_png(),
                                         headers={"Content-Type": "image/png"})
            r = json.loads(urllib.request.urlopen(req, timeout=10).read())
            self.assertEqual(r["status"], "partial")
            self.assertEqual(r["ocr"]["status"], "ok")
            self.assertEqual(r["description"]["status"], "blocked")
            h = json.loads(urllib.request.urlopen(base + "/health", timeout=10).read())
            self.assertEqual(h["template_version"], "0.1.2")
            self.assertTrue(h["job_health"]["ocr"]["ready"])
            self.assertFalse(h["job_health"]["vision"]["ready"])
        finally:
            web.stop()


class TemplateVersionTest(unittest.TestCase):
    def test_recorded(self):
        self.assertEqual((ROOT / "TEMPLATE_VERSION").read_text().strip(), "TEMPLATE_VERSION=0.1.2")
        cfg = json.loads((ROOT / "config" / "config.example.json").read_text())
        self.assertEqual(cfg["template_version"], "0.1.2")


SAMPLES = ROOT / "samples"


class RealToolsProbe(unittest.TestCase):
    """Uses the REAL tesseract and REAL Ollama vision model if present; skipped
    otherwise. Prints what the real tools returned, for the report."""
    def test_real_tesseract(self):
        if not shutil.which("tesseract"):
            self.skipTest("real tesseract not on PATH")
        bot = Bot(photo_cfg(tess="tesseract", mode="ocr"))
        try:
            ok, msg = bot.job.ocr_ready()
            if not ok:
                self.skipTest(msg)
            r = bot.job.read_photo((SAMPLES / "sample1-sign.png").read_bytes())
        finally:
            bot.close()
        print(f"\n  real OCR ({r['ocr'].get('engine')}, {r['ocr'].get('elapsed_s')}s): {r['ocr'].get('text')!r}")
        self.assertEqual(r["ocr"]["status"], "ok", r)
        self.assertIn("Gate closes", r["ocr"]["text"])

    def test_real_ollama_vision(self):
        url = os.environ.get("BOT_OLLAMA_URL", "http://127.0.0.1:11434")
        cfg = photo_cfg(url, mode="describe")
        cfg["photo"]["vision"].update({"think": False, "timeout_s": 900})
        bot = Bot(cfg)
        try:
            ok, msg = bot.job.vision_ready()
            if not ok:
                self.skipTest(msg)
            r = bot.job.read_photo((SAMPLES / "sample3-house-no-text.png").read_bytes())
        finally:
            bot.close()
        d = r["description"]
        print(f"\n  real vision ({d.get('model')}, think={d.get('think')}, {d.get('elapsed_s')}s): {d.get('text')!r}")
        self.assertEqual(d["status"], "ok", r)
        self.assertTrue(d["text"].strip())


if __name__ == "__main__":
    unittest.main()

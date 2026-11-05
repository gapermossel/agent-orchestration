"""Photo-reader job: photo in -> OCR text (Tesseract CLI) and/or image
description (Ollama vision model) out.

Nothing is downloaded. If the tesseract binary, its language data, Ollama, or
the vision model is missing, that half of the answer comes back with
status "blocked" and names exactly what is missing."""
import os
import re
import shutil
import subprocess
import tempfile
import time

from ..ollama_client import OllamaError, OllamaUnavailable
from .base import Job

MAGIC = [
    (b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"), (b"GIF87a", "gif"), (b"GIF89a", "gif"),
    (b"BM", "bmp"), (b"II*\x00", "tif"), (b"MM\x00*", "tif"),
]

DEFAULTS = {
    "mode": "both",  # both | ocr | describe
    "ocr": {"engine": "tesseract", "tesseract_cmd": "tesseract", "lang": "eng", "tessdata_dir": None,
            "psm": 3, "timeout_s": 60},
    # think=False asks qwen3-vl to skip its reasoning step (faster on CPU).
    # timeout_s is long because the box runs the model on CPU only.
    "vision": {"model": "qwen3-vl:8b", "think": False, "timeout_s": 900,
               "prompt": "Describe this image in two or three plain English sentences. "
                         "If it contains text, say what kind of document or sign it is."},
}


def sniff(data):
    for sig, kind in MAGIC:
        if data.startswith(sig):
            return kind
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


class PhotoReaderJob(Job):
    name = "photo-reader"

    def __init__(self, bot):
        super().__init__(bot)
        p = bot.cfg.get("photo", {})
        self.mode = p.get("mode", DEFAULTS["mode"])
        self.ocr_cfg = {**DEFAULTS["ocr"], **p.get("ocr", {})}
        self.vis_cfg = {**DEFAULTS["vision"], **p.get("vision", {})}

    # ---------- readiness ----------
    def ocr_ready(self):
        c = self.ocr_cfg
        if c["engine"] != "tesseract":
            return False, f"OCR engine '{c['engine']}' not supported in v0.1 (only tesseract)"
        exe = shutil.which(c["tesseract_cmd"])
        if not exe:
            return False, f"tesseract binary not found ('{c['tesseract_cmd']}' not on PATH)"
        try:
            ver = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10)
            version = (ver.stdout + ver.stderr).splitlines()[0].strip()
            cmd = [exe, "--list-langs"] + (["--tessdata-dir", c["tessdata_dir"]] if c["tessdata_dir"] else [])
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError, IndexError) as e:
            return False, f"tesseract not runnable: {e}"
        langs = [l.strip() for l in out.stdout.splitlines()[1:] if l.strip()]
        missing = [l for l in c["lang"].split("+") if l not in langs]
        if missing:
            where = c["tessdata_dir"] or "default tessdata dir"
            return False, f"{version}: language data missing: " + ", ".join(f"{m}.traineddata" for m in missing) + f" (in {where})"
        return True, version

    def vision_ready(self):
        model = self.vis_cfg["model"]
        try:
            if self.bot.ollama.has_model(model):
                return True, f"{model} at {self.bot.ollama.base_url}"
            return False, f"vision model '{model}' not present in Ollama at {self.bot.ollama.base_url} (not pulled)"
        except OllamaUnavailable as e:
            return False, f"{e}; vision model '{model}' needed"
        except OllamaError as e:
            return False, str(e)

    def health(self):
        o_ok, o_msg = self.ocr_ready()
        v_ok, v_msg = self.vision_ready()
        return {"mode": self.mode,
                "ocr": {"ready": o_ok, "detail": o_msg},
                "vision": {"ready": v_ok, "detail": v_msg}}

    # ---------- work ----------
    def run_ocr(self, data, kind):
        ok, msg = self.ocr_ready()
        if not ok:
            return {"status": "blocked", "reason": msg}
        c = self.ocr_cfg
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, f"in.{kind}")
            with open(path, "wb") as f:
                f.write(data)
            cmd = [shutil.which(c["tesseract_cmd"]), path, "stdout", "-l", c["lang"], "--psm", str(c["psm"])]
            if c["tessdata_dir"]:
                cmd += ["--tessdata-dir", c["tessdata_dir"]]
            t0 = time.monotonic()
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=c["timeout_s"])
            except subprocess.TimeoutExpired:
                return {"status": "error", "reason": f"tesseract timed out after {c['timeout_s']}s"}
        if r.returncode != 0:
            return {"status": "error", "reason": f"tesseract exit {r.returncode}: {r.stderr.strip()[:300]}"}
        text = re.sub(r"\n{3,}", "\n\n", r.stdout).strip()
        return {"status": "ok", "engine": msg, "text": text, "elapsed_s": round(time.monotonic() - t0, 2)}

    def run_vision(self, data):
        ok, msg = self.vision_ready()
        if not ok:
            return {"status": "blocked", "reason": msg}
        c = self.vis_cfg
        t0 = time.monotonic()
        try:
            out = self.bot.ollama.generate(c["model"], c["prompt"], images=[data],
                                           think=c.get("think"), timeout_s=c.get("timeout_s"))
        except OllamaError as e:
            return {"status": "error", "reason": str(e), "elapsed_s": round(time.monotonic() - t0, 2)}
        meta = getattr(self.bot.ollama, "last_response", {}) or {}
        res = {"status": "ok", "model": c["model"], "think": c.get("think"), "text": out.strip(),
               "elapsed_s": round(time.monotonic() - t0, 2)}
        ns = {k: meta.get(k) for k in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration")}
        res["ollama_timing_s"] = {k.replace("_duration", ""): round(v / 1e9, 2) for k, v in ns.items() if isinstance(v, (int, float))}
        res["tokens"] = {"prompt": meta.get("prompt_eval_count"), "output": meta.get("eval_count")}
        if meta.get("thinking"):
            res["thinking_chars"] = len(meta["thinking"])  # model still returned reasoning text; not shown to user
        return res

    def read_photo(self, data, mode=None):
        mode = mode or self.mode
        kind = sniff(data)
        if not kind:
            return {"status": "rejected", "text": "That file is not a PNG, JPEG, GIF, BMP, TIFF or WEBP image."}
        t0 = time.monotonic()
        res = {"image_type": kind, "bytes": len(data), "mode": mode}
        if mode in ("both", "ocr"):
            res["ocr"] = self.run_ocr(data, kind)
        if mode in ("both", "describe"):
            res["description"] = self.run_vision(data)
        parts = [res[k] for k in ("ocr", "description") if k in res]
        oks = sum(p["status"] == "ok" for p in parts)
        res["status"] = "ok" if oks == len(parts) else ("partial" if oks else "blocked")
        res["text"] = self.render(res)
        res["elapsed_s"] = round(time.monotonic() - t0, 2)
        return res

    @staticmethod
    def render(res):
        lines = []
        if "ocr" in res:
            o = res["ocr"]
            lines.append("Text in photo:\n" + (o["text"] or "(no text found)") if o["status"] == "ok"
                         else f"Text in photo: {o['status'].upper()}: {o['reason']}")
        if "description" in res:
            v = res["description"]
            lines.append("Description:\n" + v["text"] if v["status"] == "ok"
                         else f"Description: {v['status'].upper()}: {v['reason']}")
        return "\n\n".join(lines)

    def handle_photo(self, channel, user, data, filename=None):
        self.bot.log.info("photo-reader: %s (%d bytes)", filename, len(data))
        return self.read_photo(data)

    def handle_text(self, channel, user, text):
        return {"text": "Send me a photo and I will return the text in it and a short description.",
                "status": "help"}

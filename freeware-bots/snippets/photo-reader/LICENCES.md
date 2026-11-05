# Licences (photo-reader 0.1.2)

Template licences apply (`../_template/LICENCES.md`).

| Component | Licence | Notes |
|---|---|---|
| **Photo-reader code (this folder)** | **MIT** (see `LICENSE`, "Copyright (c) 2026 Wilrich Lightfoot") | Author decision. |
| Tesseract 5.5.0 (box, Debian package) | Apache-2.0 | separate program called by CLI; not bundled. Pin is 5.5.4 (same licence). |
| Tesseract `eng` / `osd` traineddata (Debian packages) | Apache-2.0 | from the tesseract-ocr tessdata project; UNVERIFIED this session (Debian copyright file not checked) |
| Leptonica 1.84.1 (box, used by Tesseract) | BSD-2-Clause-style (Leptonica licence) | UNVERIFIED this session |
| Qwen3-VL-8B (`qwen3-vl:8b`) | Apache-2.0 | `ollama show` licence block reads "Apache License Version 2.0" |
| PaddleOCR v3.7.0 | Apache-2.0 | not used |
| Pillow 12.3.0 (test images only) | MIT-CMU (HPND) | box tool, not in the bot's runtime path |
| DejaVu Sans font (test images only) | Bitstream Vera / DejaVu free licence | box font, used to draw samples |

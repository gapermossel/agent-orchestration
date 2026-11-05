# Photo-reader bot v0.1.2

Licence: MIT (`LICENSE`). TEMPLATE_VERSION=0.1.2 (built from `../template`; see `TEMPLATE_VERSION`).

Send a photo; get back (1) the text in it (OCR, Tesseract CLI) and/or (2) a short
description (local vision model via Ollama). Python 3 standard library only.


## Web page (v0.1.2, from the template)
Open `http://<host>:<port>/` in a browser. The page has:
- a file picker that uploads a photo to `POST /photo`;
- a text box that sends a message to `POST /message`.

The reply shows on the page as plain text (for photo bots: the text found in the photo, the description, timings and any error). While the bot works the page shows "working… N s", and it waits up to 20 minutes, because a description on a CPU can take a minute or more. The page has no outside files: no CDN, no web fonts, all CSS/JS inline. It also calls `GET /health` to show whether the model server and tools are ready.

The JSON API is unchanged (`GET /health`, `POST /message`, `POST /photo`); `tests/test_web_api_unchanged.py` compares it with a frozen copy of the v0.1.1 adapter.

**Bind address.** Set `web.host` / `web.port` in `config/config.json`, or the env vars `BOT_WEB_HOST` / `BOT_WEB_PORT` (they win over the file). The default is `127.0.0.1` (this computer only). Examples:

    # only this computer (default)
    python3 -m bot --config config/config.json --adapters web
    # a Tailscale address (use the machine's own 100.x address)
    BOT_WEB_HOST=<TAILSCALE_IP> BOT_WEB_PORT=8091 python3 -m bot --config config/config.json --adapters web
    # every interface (LAN too; be careful)
    BOT_WEB_HOST=0.0.0.0 python3 -m bot --config config/config.json --adapters web

IPv6 addresses work too (e.g. `BOT_WEB_HOST=fd7a:115c:a1e0::1`, with or without `[ ]`). The host must be an address this machine owns, or the bot stops with `Cannot assign requested address`.

**There is no login.** Anyone who can reach the address and port can use the bot. Bind to a Tailscale address only on a tailnet you trust, and never to a public address. When the host is not loopback, the log shows a warning.

**Upload limit.** `web.max_body_bytes` (default 10485760 = 10 MB). Bigger uploads get HTTP 413, and the page refuses them before uploading.

## Run
    cd photo-reader
    python3 -m bot --config config/config.json --adapters web     # web adapter on 127.0.0.1:8091
    curl -s http://127.0.0.1:8091/health
    curl -s --data-binary @samples/sample1-sign.png -H 'Content-Type: image/png' 'http://127.0.0.1:8091/photo?user=me&filename=sample1-sign.png'

One-off from the command line:

    python3 -m bot.photo_cli --config config/config.json [--mode both|ocr|describe] IMAGE...

Use Ollama on the Windows host: `BOT_OLLAMA_URL=http://<windows-host-ip>:11434 python3 -m bot ...`

## Config (`config/config.json`, section `photo`)
- `mode`: `both` | `ocr` | `describe`
- `ocr.tesseract_cmd` (default `tesseract`), `ocr.lang` (default `eng`, needs `eng.traineddata`), `ocr.tessdata_dir`, `ocr.psm`
- `vision.model` (default `qwen3-vl:8b`), `vision.prompt`, `vision.think` (default false), `vision.timeout_s` (default 900; CPU is slow)

Accepted images: PNG, JPEG, GIF, BMP, TIFF, WEBP (checked by file signature); max 10 MiB via web.

## Reply shape
JSON: `status` (`ok` | `partial` | `blocked` | `rejected`), `ocr` {status, text | reason},
`description` {status, text | reason, model, think, elapsed_s, ollama_timing_s, tokens}, `elapsed_s`, `text` (the human-readable message a chat adapter sends).

## Python versions
Tested on Python 3.13.5 (the box). Target machines may run Python 3.14; this code has **not been run on 3.14 yet**. A static check (2026-10-30) found nothing it uses that 3.14 removed: no `cgi`, `imghdr`, `audioop`, `telnetlib`; asyncio is used only via `asyncio.run`, never `get_event_loop()`. Run the test suite once on 3.14 before relying on it. The discord.py library already fails on 3.13+ (needs `audioop`), as noted in PINNED-VERSIONS.md.

## Test
    python3 -m unittest discover -s tests -v

`tests/test_photo_web_ui.py` checks that the page shows OCR text and descriptions as plain text (hostile HTML in fake OCR and model output) and that the photo JSON reply matches the v0.1.1 adapter. Its page-script test needs `node` (tests only) and is skipped without it.

`fake_tesseract` and `FakeOllama` in the tests are **fakes** that check this bot's plumbing only.
The `RealToolsProbe` tests use the real tesseract (OCR of sample1) and the real Ollama vision model (sample3). They are skipped while those are missing.

Sample images: `python3 samples/make_samples.py` (uses Pillow already on the box, only to draw test pictures).

Update / rollback, chat adapters, memory, logging: as in the template README (`../_template/README.md`).

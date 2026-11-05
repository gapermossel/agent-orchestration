# Freeware bot template v0.1.2

Base for every freeware bot. Python 3 standard library only; no pip installs. Licence: MIT (`LICENSE`).

## Layout
- `bot/core.py`: Bot = config + logging + memory + Ollama client + one job module
- `bot/jobs/`: job modules (`chat.py` = default text chat via Ollama). A bot sets `"job": "module:Class"` in config.
- `bot/adapters/web.py`: HTTP adapter (**tested**): web page at `GET /` (v0.1.2), plus the JSON API `GET /health`, `POST /message` (JSON `{"user","text"}`), `POST /photo` (raw image bytes, `?user=&filename=`)
- `bot/adapters/telegram_adapter.py`: imports python-telegram-bot from the library source tree. **Tested offline only** (placeholder token, stand-in messages, nothing sent); never connected to real Telegram.
- `bot/adapters/discord_adapter.py`, `matrix_adapter.py`: **UNTESTED STUBS** that do not load on the box yet (discord.py: `audioop` missing on Python 3.13; matrix-nio: `aiohttp_socks`, h2, jsonschema, unpaddedbase64, pycryptodome missing). The adapter refuses to start with a clear message.
- `bot/ollama_client.py`: Ollama REST client
- `bot/memory.py`: SQLite memory; `bot/logging_setup.py`: rotating log with token redaction
- `config/config.example.json` → copy to `config/config.json` (git-ignored local settings)
- `update.sh`, `rollback.sh`, `tests/`, `patches/`, `PINNED-VERSIONS.md`, `LICENCES.md`, `CHANGELOG.md`

## Run
    cd _template
    python3 -m bot --config config/config.json --adapters web
    curl -s http://127.0.0.1:8088/health

Point at Ollama on the Windows host: `BOT_OLLAMA_URL=http://<windows-host-ip>:11434 python3 -m bot ...`
(Ollama there must listen on the LAN: `OLLAMA_HOST=0.0.0.0`).

Tokens: set `TELEGRAM_BOT_TOKEN`, `DISCORD_BOT_TOKEN`, `MATRIX_HOMESERVER`/`MATRIX_USER_ID`/`MATRIX_ACCESS_TOKEN` in the environment. Never put them in config files.

## Web page (v0.1.2)
Open `http://<host>:<port>/` in a browser. The page has:
- a file picker that uploads a photo to `POST /photo`;
- a text box that sends a message to `POST /message`.

The reply shows on the page as plain text (for photo bots: the text found in the photo, the description, timings and any error). While the bot works the page shows "working… N s", and it waits up to 20 minutes, because a description on a CPU can take a minute or more. The page has no outside files: no CDN, no web fonts, all CSS/JS inline. It also calls `GET /health` to show whether the model server and tools are ready.

The JSON API is unchanged (`GET /health`, `POST /message`, `POST /photo`); `tests/test_web_api_unchanged.py` compares it with a frozen copy of the v0.1.1 adapter.

**Bind address.** Set `web.host` / `web.port` in `config/config.json`, or the env vars `BOT_WEB_HOST` / `BOT_WEB_PORT` (they win over the file). The default is `127.0.0.1` (this computer only). Examples:

    # only this computer (default)
    python3 -m bot --config config/config.json --adapters web
    # a Tailscale address (use the machine's own 100.x address)
    BOT_WEB_HOST=100.x.y.z BOT_WEB_PORT=8091 python3 -m bot --config config/config.json --adapters web
    # every interface (LAN too; be careful)
    BOT_WEB_HOST=0.0.0.0 python3 -m bot --config config/config.json --adapters web

IPv6 addresses work too (e.g. `BOT_WEB_HOST=fd7a:115c:a1e0::1`, with or without `[ ]`). The host must be an address this machine owns, or the bot stops with `Cannot assign requested address`.

**There is no login.** Anyone who can reach the address and port can use the bot. Bind to a Tailscale address only on a tailnet you trust, and never to a public address. When the host is not loopback, the log shows a warning.

**Upload limit.** `web.max_body_bytes` (default 10485760 = 10 MB). Bigger uploads get HTTP 413, and the page refuses them before uploading.

## Python versions
Tested on Python 3.13.5 (the box). Target machines may run Python 3.14; this code has **not been run on 3.14 yet**. A static check (2026-10-30) found nothing it uses that 3.14 removed: no `cgi`, `imghdr`, `audioop`, `telnetlib`; asyncio is used only via `asyncio.run`, never `get_event_loop()`. Run the test suite once on 3.14 before relying on it. The discord.py library already fails on 3.13+ (needs `audioop`), as noted in PINNED-VERSIONS.md.

## Test
    python3 -m unittest discover -s tests -v

`tests/test_web_ui.py` checks the page. Its page-script tests run the page's own JavaScript under Node in a stand-in DOM (`tests/ui_harness.js`; not a real browser) and are skipped if `node` is not installed. The bot itself never needs Node.

`FakeOllama` in the tests is a fake server that checks our request/response handling; it is not a model.
`RealOllamaProbe` talks to the real Ollama (default http://127.0.0.1:11434, or `BOT_OLLAMA_URL`) and is skipped when none is reachable. All other tests use a closed port, so they never reach a real model by accident.

## Update / rollback (local only, no network)
    ./update.sh /path/to/new-release-dir            # or release.tar.gz (+ optional release.tar.gz.sha256)
    ./rollback.sh                                   # back to the previous version
The new release's tests run before anything is replaced (`--skip-tests` to skip). `data/` and `config/config.json` are kept. History: `.releases/HISTORY`.

## Making a new bot
Copy this folder, set `TEMPLATE_VERSION` file to this VERSION, add `bot/jobs/<job>.py`, set `"job"` in config, add tests.

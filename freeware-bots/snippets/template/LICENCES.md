# Licences (template 0.1.2)

Licence values for library components are (read from each tree's LICENSE file).

| Component | Licence | Notes |
|---|---|---|
| **Template code (this folder)** | **MIT** (see `LICENSE`, "Copyright (c) 2026 Wilrich Lightfoot") | Author decision. No third-party code copied in. |
| Python standard library | PSF-2.0 | runtime only |
| Web page (v0.1.2, inside `bot/adapters/web.py`) | MIT (template code) | written for this template; no third-party CSS/JS, no CDN, no fonts |
| Node.js (tests only, box tool) | MIT | runs the page-script tests; not shipped, not needed at run time |
| Ollama v0.40.13 | MIT | separate program, talked to over HTTP; not bundled |
| python-telegram-bot v22.8 | LGPL-3.0-only (LICENSE.dual: GPLv3 or LGPLv3) | imported unchanged from library source, not bundled. It is a separate library used unmodified by MIT code, which LGPL allows. If a modified copy is ever shipped, its changes must be published under LGPL. |
| discord.py v2.7.1 | MIT | imported unchanged (does not load yet) |
| matrix-nio 0.26.0 | ISC | imported unchanged (does not load yet) |
| httpx 0.28.1 / httpcore | BSD-3-Clause | licence from package metadata, UNVERIFIED this session |
| aiohttp 3.14.5 | Apache-2.0 (with MIT parts) | as above, UNVERIFIED |
| aiofiles 25.1.0 | Apache-2.0 | as above, UNVERIFIED |
| Qwen3-8B (default chat model name only; not downloaded) | Apache-2.0 | |

Banned components (n8n, Rasa Pro, Coqui XTTS, Open WebUI, LobeHub, Watchtower,
AutoGen), paid/cloud AI APIs and WhatsApp are not used.

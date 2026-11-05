# Freeware bots

Small self-hosted bots that run on your own computer with a local model through [Ollama](https://ollama.com). Python 3 standard library only for the core; chat-platform adapters use their usual libraries.

## snippets/template/
The shared bot skeleton: config loader (file plus `BOT_*` environment overrides), a minimal Ollama REST client, per-user chat memory in SQLite, a `/health` page, a no-dependency web page, and adapters for Telegram, Discord and Matrix. Includes one-command `update.sh` / `rollback.sh` and a unittest suite.

## snippets/photo-reader/
Built on the template. Send a photo and get back the text in it (Tesseract OCR) and a short description from a local vision model (`qwen3-vl:8b` via Ollama). If OCR or the model is missing it still answers and says exactly what is missing.

## Run with Ollama
    ollama pull qwen3-vl:8b          # photo-reader; any chat model for the template
    cd snippets/photo-reader
    cp config/config.example.json config/config.json
    python3 -m bot --config config/config.json --adapters web
    # open http://127.0.0.1:8091/

Ollama elsewhere on your network: `BOT_OLLAMA_URL=http://<LAN_IP>:11434`. The web page has no login, so bind only to 127.0.0.1 or a private network you trust. Chat tokens are read from environment variables named in the config, never stored in it.

## Licence
Each bot keeps its own `LICENSE` (MIT) and `LICENCES.md` (third-party components and their licences).

The vendored upstream sources are not included; see `NOTES-vendor-stack.md`.

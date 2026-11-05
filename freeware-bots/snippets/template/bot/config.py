"""Config loading. JSON file + environment overrides. Secrets are never stored in
the file: the file only names the environment variable that holds each token."""
import copy
import json
import os
from pathlib import Path

from . import ROOT

DEFAULTS = {
    "bot_name": "template-bot",
    "data_dir": "data",
    "log_level": "INFO",
    "library_src": "./vendor/src",
    "ollama": {
        "base_url": "http://127.0.0.1:11434",
        "chat_model": "qwen3:8b",
        "timeout_s": 120,
    },
    "memory": {"backend": "sqlite", "path": "data/memory.sqlite3", "history_turns": 6},
    "web": {"enabled": True, "host": "127.0.0.1", "port": 8088, "max_body_bytes": 10485760},
    "telegram": {"enabled": False, "token_env": "TELEGRAM_BOT_TOKEN"},
    "discord": {"enabled": False, "token_env": "DISCORD_BOT_TOKEN"},
    "matrix": {
        "enabled": False,
        "homeserver_env": "MATRIX_HOMESERVER",
        "user_id_env": "MATRIX_USER_ID",
        "access_token_env": "MATRIX_ACCESS_TOKEN",
    },
}

# Environment variables that override config values (no secrets here; tokens
# are read by the adapters from the env var named in the config).
ENV_OVERRIDES = {
    "BOT_OLLAMA_URL": ("ollama", "base_url"),
    "BOT_WEB_HOST": ("web", "host"),
    "BOT_WEB_PORT": ("web", "port"),
    "BOT_LOG_LEVEL": ("log_level",),
    "BOT_DATA_DIR": ("data_dir",),
}


def _merge(base, extra):
    out = dict(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _set(cfg, path, value):
    node = cfg
    for key in path[:-1]:
        node = node.setdefault(key, {})
    old = node.get(path[-1])
    if isinstance(old, bool):
        value = value.lower() in ("1", "true", "yes")
    elif isinstance(old, int):
        value = int(value)
    node[path[-1]] = value


def resolve_path(cfg, p):
    p = Path(p)
    return p if p.is_absolute() else (ROOT / p)


def load(path=None, env=None, extra_defaults=None):
    env = os.environ if env is None else env
    # deepcopy: callers may change nested values (e.g. cfg['web']['host']) without
    # changing DEFAULTS for every later load (bug in v0.1.1, fixed in v0.1.2).
    cfg = _merge(copy.deepcopy(DEFAULTS), copy.deepcopy(extra_defaults or {}))
    path = path or env.get("BOT_CONFIG") or (ROOT / "config" / "config.json")
    path = Path(path)
    if path.exists():
        cfg = _merge(cfg, json.loads(path.read_text()))
    for var, keypath in ENV_OVERRIDES.items():
        if env.get(var):
            _set(cfg, keypath, env[var])
    cfg["_config_path"] = str(path)
    return cfg

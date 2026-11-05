"""Channel adapters. web is tested on the box. telegram is tested offline only
(no real Telegram connection). discord and matrix are written against the
pinned library clients but do not import on the box yet (see README)."""
import sys
from pathlib import Path


class AdapterUnavailable(Exception):
    pass


LIB_PATHS = {
    "telegram": "python-telegram-bot/src",
    "discord": "discord.py",
    "nio": "matrix-nio/src",
}


def import_library(cfg, module):
    """Import a chat library from the pinned library source tree (no pip)."""
    p = Path(cfg["library_src"]) / LIB_PATHS[module]
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))
    try:
        return __import__(module)
    except ImportError as e:
        raise AdapterUnavailable(f"{module} from {p} not importable: {e}") from e


def require_env(env, name):
    val = env.get(name)
    if not val:
        raise AdapterUnavailable(f"environment variable {name} is not set")
    return val

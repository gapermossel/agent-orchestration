"""Run: python3 -m bot [--config path] [--adapters web,telegram,...]"""
import argparse
import os

from .adapters import AdapterUnavailable
from .core import Bot
from . import config as config_mod

ADAPTERS = {
    "web": ("bot.adapters.web", "WebAdapter"),
    "telegram": ("bot.adapters.telegram_adapter", "TelegramAdapter"),
    "discord": ("bot.adapters.discord_adapter", "DiscordAdapter"),
    "matrix": ("bot.adapters.matrix_adapter", "MatrixAdapter"),
}


def build_adapter(name, bot):
    import importlib
    mod, cls = ADAPTERS[name]
    return getattr(importlib.import_module(mod), cls)(bot)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bot")
    ap.add_argument("--config")
    ap.add_argument("--adapters", help="comma list; default = enabled in config")
    a = ap.parse_args(argv)
    cfg = config_mod.load(a.config)
    bot = Bot(cfg)
    names = a.adapters.split(",") if a.adapters else [n for n in ADAPTERS if cfg.get(n, {}).get("enabled")]
    started = []
    for n in names:
        try:
            ad = build_adapter(n, bot)
        except AdapterUnavailable as e:
            bot.log.error("adapter %s unavailable: %s", n, e)
            continue
        started.append(ad)
    if not started:
        bot.log.error("no adapter could start")
        return 2
    for ad in started[:-1]:
        ad.start(background=True)  # only the web adapter supports this cleanly
    started[-1].start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

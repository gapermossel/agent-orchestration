"""Read one or more photos from the command line and print the JSON result.
Usage: python3 -m bot.photo_cli [--config config/config.json] [--mode both|ocr|describe] IMAGE..."""
import argparse
import json

from . import config as config_mod
from .core import Bot


def main(argv=None):
    ap = argparse.ArgumentParser(prog="photo_cli")
    ap.add_argument("--config")
    ap.add_argument("--mode", choices=["both", "ocr", "describe"])
    ap.add_argument("images", nargs="+")
    a = ap.parse_args(argv)
    bot = Bot(config_mod.load(a.config))
    for path in a.images:
        with open(path, "rb") as f:
            data = f.read()
        res = bot.job.read_photo(data, a.mode)
        print(json.dumps({"input": path, **res}, ensure_ascii=False, indent=2))
    bot.close()


if __name__ == "__main__":
    main()

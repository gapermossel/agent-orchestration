"""Logging: rotating file in data_dir/logs plus stderr. A filter masks the values
of any token environment variables named in the config, so a token can never
reach the log even if some library prints it."""
import logging
import logging.handlers
import os

from .config import resolve_path


class RedactFilter(logging.Filter):
    def __init__(self, secrets):
        super().__init__()
        self.secrets = [s for s in secrets if s and len(s) >= 6]

    def filter(self, record):
        if self.secrets:
            msg = record.getMessage()
            for s in self.secrets:
                msg = msg.replace(s, "***REDACTED***")
            record.msg, record.args = msg, None
        return True


def secret_values(cfg, env=None):
    env = os.environ if env is None else env
    vals = []
    for section in ("telegram", "discord", "matrix"):
        for k, v in cfg.get(section, {}).items():
            if k.endswith("token_env") and env.get(v):
                vals.append(env[v])
    return vals


def setup(cfg, env=None):
    logs = resolve_path(cfg, cfg["data_dir"]) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("bot")
    logger.setLevel(cfg.get("log_level", "INFO"))
    for h in list(logger.handlers):
        h.close()
        logger.removeHandler(h)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    red = RedactFilter(secret_values(cfg, env))
    fh = logging.handlers.RotatingFileHandler(logs / "bot.log", maxBytes=1_000_000, backupCount=3)
    sh = logging.StreamHandler()
    for h in (fh, sh):
        h.setFormatter(fmt)
        h.addFilter(red)
        logger.addHandler(h)
    return logger

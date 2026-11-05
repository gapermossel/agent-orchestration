"""Job modules. A bot built from this template sets config "job" to
"module.path:ClassName". The template ships ChatJob (text chat via Ollama)."""
import importlib


def load_job(spec):
    mod, _, cls = spec.partition(":")
    return getattr(importlib.import_module(mod), cls)

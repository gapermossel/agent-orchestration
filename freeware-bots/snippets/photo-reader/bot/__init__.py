"""Freeware bot template. Standard library only."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
__version__ = (ROOT / "VERSION").read_text().strip()

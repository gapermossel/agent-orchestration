"""SQLite schema and connection setup for an offline livestock record book.

Excerpt from a desktop/phone livestock app (Python + Flet UI + SQLite,
English/Afrikaans). Shown here as a self-contained excerpt; names and data are
placeholders.

Design points:
- WAL mode + busy timeout, so the UI thread and a background export can share
  one file safely.
- CHECK constraints mirror the app-level validation, so a bad row is refused
  even if a future code path skips the validator.
- Every row carries updated_at and device_id. That is what lets two copies of
  the same book (phone and computer) be merged later without silent overwrites.
- A visual ear tag is unique per farm and species, not globally.
- Referential integrity is switched on for every connection in connect()
  (SQLite leaves it off by default): deleting a farm cascades to its camps,
  animals and events, and deleting a camp just un-assigns its animals.
"""
from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Optional

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    name  TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS farm (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT,
    brand_mark TEXT,
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS camp (
    id INTEGER PRIMARY KEY,
    farm_id INTEGER NOT NULL REFERENCES farm(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    device_id TEXT
);

CREATE TABLE IF NOT EXISTS animal (
    id INTEGER PRIMARY KEY,
    farm_id INTEGER NOT NULL REFERENCES farm(id) ON DELETE CASCADE,
    camp_id INTEGER REFERENCES camp(id) ON DELETE SET NULL,
    species TEXT NOT NULL CHECK(species IN ('cattle','sheep','goat')),
    tag_visual TEXT NOT NULL,
    sex TEXT NOT NULL DEFAULT 'unknown' CHECK(sex IN ('female','male','unknown')),
    breed TEXT,
    dob TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active','sold','dead','missing')),
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    device_id TEXT,
    UNIQUE(farm_id, species, tag_visual)
);

CREATE TABLE IF NOT EXISTS event (
    id INTEGER PRIMARY KEY,
    farm_id INTEGER NOT NULL REFERENCES farm(id) ON DELETE CASCADE,
    animal_id INTEGER NOT NULL REFERENCES animal(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK(event_type IN (
        'birth','vaccination','treatment','weight','movement',
        'sale','death','purchase','other')),
    event_date TEXT NOT NULL,
    product TEXT,
    next_due_date TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    device_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_animal_farm_status_species ON animal(farm_id, status, species);
CREATE INDEX IF NOT EXISTS idx_event_animal_date ON event(animal_id, event_date);
-- "What is due this week?" is the most common query on the phone.
CREATE INDEX IF NOT EXISTS idx_event_due ON event(farm_id, event_type, next_due_date);
"""


class Database:
    def __init__(self, path: Path | str = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self.device_id = ""

    def connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(SCHEMA_SQL)
        # A stable per-book device id, created once and stored in the file
        # itself, so a copied book keeps its identity on a new machine.
        row = conn.execute("SELECT value FROM meta WHERE name='device_id'").fetchone()
        if row:
            self.device_id = row["value"]
        else:
            self.device_id = f"dev-{uuid.uuid4().hex[:6]}"
            conn.execute("INSERT INTO meta(name, value) VALUES('device_id', ?)", (self.device_id,))
            conn.commit()
        self._conn = conn
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self.connect()

    def get_meta(self, name: str, default: Optional[str] = None) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM meta WHERE name=?", (name,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, name: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(name, value) VALUES(?, ?) "
            "ON CONFLICT(name) DO UPDATE SET value=excluded.value",
            (name, value),
        )
        self.conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


if __name__ == "__main__":
    db = Database()
    c = db.conn
    now = "2026-01-01T00:00:00.000Z"
    c.execute("INSERT INTO farm(name, created_at, updated_at) VALUES('Sample Farm', ?, ?)", (now, now))
    c.execute("INSERT INTO animal(farm_id, species, tag_visual, created_at, updated_at) "
              "VALUES(1, 'cattle', 'C-001', ?, ?)", (now, now))
    for bad in (
        ("cattle", "C-001"),   # duplicate tag for the same species
        ("horse", "H-001"),    # species outside the CHECK list
    ):
        try:
            c.execute("INSERT INTO animal(farm_id, species, tag_visual, created_at, updated_at) "
                      "VALUES(1, ?, ?, ?, ?)", (*bad, now, now))
        except sqlite3.IntegrityError as e:
            print("refused:", e)
    print("device id stored:", db.get_meta("device_id") == db.device_id)
    c.execute("DELETE FROM farm WHERE id = 1")
    print("cascade removed animals:", c.execute("SELECT COUNT(*) FROM animal").fetchone()[0] == 0)

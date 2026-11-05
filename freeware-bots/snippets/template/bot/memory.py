"""Simple conversation memory in SQLite (standard library sqlite3)."""
import sqlite3
import threading
import time
from pathlib import Path


class Memory:
    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, ts REAL,"
            " channel TEXT, user TEXT, role TEXT, text TEXT)")
        self._db.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)")
        self._db.commit()

    def add(self, channel, user, role, text):
        with self._lock:
            self._db.execute("INSERT INTO messages (ts, channel, user, role, text) VALUES (?,?,?,?,?)",
                             (time.time(), channel, str(user), role, text))
            self._db.commit()

    def recent(self, channel, user, n=6):
        with self._lock:
            rows = self._db.execute(
                "SELECT role, text FROM messages WHERE channel=? AND user=? ORDER BY id DESC LIMIT ?",
                (channel, str(user), n)).fetchall()
        return [{"role": r, "content": t} for r, t in reversed(rows)]

    def set(self, k, v):
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?,?)", (k, v))
            self._db.commit()

    def get(self, k, default=None):
        with self._lock:
            row = self._db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return row[0] if row else default

    def count(self):
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

    def close(self):
        self._db.close()

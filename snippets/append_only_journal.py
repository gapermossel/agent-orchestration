"""Append-only accounting journal enforced by SQLite triggers.

Excerpt from a desktop bookkeeping app (Python + SQLite), reduced to two
tables so it runs on its own. Shown here as a self-contained excerpt.

Design rules:
* Posted journals are never edited or deleted: UPDATE and DELETE triggers
  abort unconditionally. Corrections are new reversing entries.
* INSERT is allowed only while the posting module holds a capability object.
  A SQL function, journal_guard(kind), answers 1 only while that exact object
  is registered for this connection, so a stray INSERT from elsewhere aborts.
* On every open the trigger SQL is compared with the expected text. A missing
  or altered trigger raises LedgerTampered instead of being silently re-created.
"""

from __future__ import annotations

import contextlib
import sqlite3
import weakref


class LedgerTampered(Exception):
    """A database guard (trigger) is missing or altered."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS journal (
  id    TEXT NOT NULL UNIQUE,
  date  TEXT NOT NULL,
  memo  TEXT NOT NULL DEFAULT ''
) STRICT;
CREATE TABLE IF NOT EXISTS journal_line (
  journal_id   TEXT NOT NULL REFERENCES journal(id),
  account_id   TEXT NOT NULL,
  debit_cents  INTEGER NOT NULL DEFAULT 0 CHECK (debit_cents >= 0),
  credit_cents INTEGER NOT NULL DEFAULT 0 CHECK (credit_cents >= 0),
  CHECK ((debit_cents = 0) <> (credit_cents = 0))
) STRICT;
"""

# name -> SQL. Compared verbatim on every open (tamper check).
GUARD_TRIGGERS: dict[str, str] = {
    "g_journal_insert":
        "CREATE TRIGGER g_journal_insert BEFORE INSERT ON journal "
        "WHEN journal_guard('post') IS NOT 1 "
        "BEGIN SELECT RAISE(ABORT, 'journal is written only by post()'); END",
    "g_journal_update":
        "CREATE TRIGGER g_journal_update BEFORE UPDATE ON journal "
        "BEGIN SELECT RAISE(ABORT, 'posted journal is never edited'); END",
    "g_journal_delete":
        "CREATE TRIGGER g_journal_delete BEFORE DELETE ON journal "
        "BEGIN SELECT RAISE(ABORT, 'posted journal is never deleted'); END",
    "g_journal_line_insert":
        "CREATE TRIGGER g_journal_line_insert BEFORE INSERT ON journal_line "
        "WHEN journal_guard('post') IS NOT 1 "
        "BEGIN SELECT RAISE(ABORT, 'journal_line is written only by post()'); END",
    "g_journal_line_update":
        "CREATE TRIGGER g_journal_line_update BEFORE UPDATE ON journal_line "
        "BEGIN SELECT RAISE(ABORT, 'posted journal_line is never edited'); END",
    "g_journal_line_delete":
        "CREATE TRIGGER g_journal_line_delete BEFORE DELETE ON journal_line "
        "BEGIN SELECT RAISE(ABORT, 'posted journal_line is never deleted'); END",
}

# The open guards of each live connection, by id(connection): {kind: capability object}.
# An entry is dropped by weakref.finalize when its connection is garbage-collected.
_GUARDS: dict[int, dict[str, object]] = {}
_CAPABILITIES: dict[str, object] = {}


class LedgerConnection(sqlite3.Connection):
    """sqlite3 connection opened by connect(); it carries no guard flag of its own."""


@contextlib.contextmanager
def writer(conn: LedgerConnection, kind: str, cap: object):
    """Open the guard for `kind` on this connection. Only the holder of `cap` can."""
    if cap is None or _CAPABILITIES.get(kind) is not cap:
        raise LedgerTampered(f"no capability for writer '{kind}'")
    state = _GUARDS.get(id(conn)) if isinstance(conn, LedgerConnection) else None
    if state is None:
        raise LedgerTampered("connection was not opened by connect()")
    if kind in state:
        raise LedgerTampered(f"nested writer context for '{kind}'")
    state[kind] = cap
    try:
        yield
    finally:
        state.pop(kind, None)


def _verify_triggers(conn: sqlite3.Connection) -> None:
    have = {r[0]: r[1] for r in conn.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")}
    for name, sql in GUARD_TRIGGERS.items():
        if have.get(name) != sql:
            raise LedgerTampered(f"guard trigger {name} is missing or altered; refusing to open the books")


def connect(path: str = ":memory:") -> LedgerConnection:
    conn = sqlite3.connect(path, factory=LedgerConnection, isolation_level=None)
    _GUARDS[id(conn)] = {}
    weakref.finalize(conn, _GUARDS.pop, id(conn), None)
    ref = weakref.ref(conn)

    def journal_guard(kind: str) -> int:
        c = ref()
        held = _GUARDS.get(id(c), {}).get(kind) if c is not None else None
        return 1 if held is not None and _CAPABILITIES.get(kind) is held else 0

    conn.create_function("journal_guard", 1, journal_guard, deterministic=False)
    fresh = conn.execute("PRAGMA user_version").fetchone()[0] == 0
    if fresh:
        conn.executescript(SCHEMA + ";\n".join(GUARD_TRIGGERS.values()) + ";\nPRAGMA user_version = 1;")
    _verify_triggers(conn)                      # tamper check before anything else
    return conn


# --- the posting module: the only holder of the 'post' capability ----------------
_POST_CAP = object()
_CAPABILITIES["post"] = _POST_CAP


def post(conn: LedgerConnection, journal_id: str, date: str, lines: list[tuple[str, int, int]]) -> None:
    """Write one balanced journal atomically."""
    if sum(d for _, d, _ in lines) != sum(c for _, _, c in lines):
        raise ValueError("journal does not balance")
    with writer(conn, "post", _POST_CAP):
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("INSERT INTO journal(id, date) VALUES (?, ?)", (journal_id, date))
            conn.executemany("INSERT INTO journal_line VALUES (?, ?, ?, ?)",
                             [(journal_id, a, d, c) for a, d, c in lines])
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise


if __name__ == "__main__":
    db = connect()
    post(db, "J1", "2026-09-02", [("1000", 115000, 0), ("4000", 0, 100000), ("2200", 0, 15000)])
    for attempt in ("INSERT INTO journal(id, date) VALUES ('J2', '2026-09-03')",
                    "UPDATE journal SET memo = 'edited' WHERE id = 'J1'",
                    "DELETE FROM journal_line"):
        try:
            db.execute(attempt)
        except sqlite3.DatabaseError as e:
            print("refused:", e)
    db.execute("DROP TRIGGER g_journal_update")
    try:
        _verify_triggers(db)
    except LedgerTampered as e:
        print("tamper check:", e)

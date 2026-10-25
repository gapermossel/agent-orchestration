"""Offline sync between two copies of a livestock book (e.g. phone and computer).

Excerpt from a desktop/phone livestock app (Python + Flet UI + SQLite,
English/Afrikaans). Simplified to animals only and shown here as a
self-contained excerpt; uses livestock_db.py from this folder.

There is no server. One device writes a "herd file" (a zip holding JSON, a
manifest and a SHA-256 checksum) and the other device reads it in. Rules:
- A file that fails its checksum or has an unknown format version is refused.
- The same animal (species + visual tag) changed on both sides is never
  silently overwritten. It becomes a Conflict, and the farmer picks which side
  to keep. The newer side is offered as the default.
- Identical updated_at stamps mean nothing changed, so a re-import does nothing.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from livestock_db import Database

PAYLOAD_NAME, MANIFEST_NAME, CHECKSUM_NAME = "herd.json", "manifest.json", "checksum.sha256"
FORMAT_VERSION = 1
ANIMAL_FIELDS = ("species", "tag_visual", "sex", "breed", "dob", "status", "notes", "updated_at", "device_id")


def write_herd_file(db: Database, farm_id: int, exported_at: str) -> bytes:
    rows = [dict(r) for r in db.conn.execute("SELECT * FROM animal WHERE farm_id=?", (farm_id,))]
    payload = {"format_version": FORMAT_VERSION, "exported_at": exported_at,
               "source_device_id": db.device_id, "animals": rows}
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    manifest = {"format_version": FORMAT_VERSION, "exported_at": exported_at, "counts": {"animals": len(rows)}}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(PAYLOAD_NAME, body)
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))
        zf.writestr(CHECKSUM_NAME, hashlib.sha256(body).hexdigest() + "\n")
    return buf.getvalue()


def read_herd_file(data: bytes) -> Dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        if PAYLOAD_NAME not in names:
            raise ValueError("Not a herd file")
        body = zf.read(PAYLOAD_NAME)
        if CHECKSUM_NAME in names:
            expected = zf.read(CHECKSUM_NAME).decode().split()[0]
            if hashlib.sha256(body).hexdigest() != expected:
                raise ValueError("Herd file checksum failed")
    payload = json.loads(body.decode("utf-8"))
    if payload.get("format_version") != FORMAT_VERSION:
        raise ValueError("Unsupported herd file version")
    return payload


@dataclass
class Conflict:
    tag: str
    species: str
    incoming_updated_at: str
    local_updated_at: str
    incoming_row: Dict[str, Any] = field(default_factory=dict)
    local_row: Dict[str, Any] = field(default_factory=dict)
    default_keep: str = "incoming"          # "incoming" | "local": the newer side


@dataclass
class MergeResult:
    inserted: int = 0
    updated: int = 0
    conflicts: List[Conflict] = field(default_factory=list)


def merge_animals(db: Database, farm_id: int, payload: Dict[str, Any],
                  resolve: Optional[Callable[[Conflict], str]] = None) -> MergeResult:
    """Merge incoming animals. Without resolve(), conflicts are recorded and local rows kept."""
    result = MergeResult()
    conn = db.conn
    local = {(r["species"], r["tag_visual"]): dict(r)
             for r in conn.execute("SELECT * FROM animal WHERE farm_id=?", (farm_id,))}
    for ra in payload.get("animals") or []:
        ident = (ra["species"], ra["tag_visual"])
        la = local.get(ident)
        if la is None:
            cols = ("farm_id", "created_at") + ANIMAL_FIELDS
            values = [farm_id, ra.get("created_at") or ra["updated_at"]] + [ra.get(c) for c in ANIMAL_FIELDS]
            conn.execute(f"INSERT INTO animal({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})", values)
            result.inserted += 1
            continue
        ra_u, la_u = ra.get("updated_at") or "", la.get("updated_at") or ""
        if ra_u == la_u:
            continue                        # same stamp: nothing changed on either side
        if ra_u and la_u:                   # changed on both sides: the farmer decides
            c = Conflict(ra["tag_visual"], ra["species"], ra_u, la_u, ra, la,
                         "incoming" if ra_u > la_u else "local")
            result.conflicts.append(c)
            keep = (resolve(c) or c.default_keep) if resolve else "local"
            if keep != "incoming":
                continue
        elif not ra_u:
            continue                        # incoming row has no stamp: never overwrite local
        sets = ", ".join(f"{c}=?" for c in ANIMAL_FIELDS)
        conn.execute(f"UPDATE animal SET {sets} WHERE id=?", [ra.get(c) for c in ANIMAL_FIELDS] + [la["id"]])
        result.updated += 1
    conn.commit()
    return result


if __name__ == "__main__":
    def book(notes_and_stamp: tuple) -> Database:
        db = Database()
        db.conn.execute("INSERT INTO farm(name, created_at, updated_at) VALUES('Sample Farm', 't0', 't0')")
        db.conn.execute("INSERT INTO animal(farm_id, species, tag_visual, notes, created_at, updated_at) "
                        "VALUES(1, 'cattle', 'C-001', ?, 't0', ?)", notes_and_stamp)
        db.conn.commit()
        return db

    phone = book(("lame left hind", "2026-03-02T08:00:00.000Z"))
    phone.conn.execute("INSERT INTO animal(farm_id, species, tag_visual, created_at, updated_at) "
                       "VALUES(1, 'sheep', 'S-010', 't0', '2026-03-01T09:00:00.000Z')")
    computer = book(("treated", "2026-03-01T17:00:00.000Z"))

    data = write_herd_file(phone, 1, "2026-03-02T09:00:00.000Z")
    r = merge_animals(computer, 1, read_herd_file(data))
    print("inserted", r.inserted, "updated", r.updated, "conflicts", [(c.tag, c.default_keep) for c in r.conflicts])
    r = merge_animals(computer, 1, read_herd_file(data), resolve=lambda c: c.default_keep)
    print("after choosing newer:", computer.conn.execute("SELECT notes FROM animal WHERE tag_visual='C-001'").fetchone()[0])
    # Rebuild the zip with an edited payload but the original checksum.
    try:
        bad = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(bad, "w") as dst:
            for n in src.namelist():
                b = src.read(n)
                dst.writestr(n, b.replace(b"lame", b"fine") if n == PAYLOAD_NAME else b)
        read_herd_file(bad.getvalue())
    except ValueError as e:
        print("refused:", e)

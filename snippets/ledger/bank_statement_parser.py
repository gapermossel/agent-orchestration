"""Strict bank-statement CSV parser with a running-balance proof.

Excerpt from a desktop bookkeeping app (Python + SQLite). Shown here as a
self-contained excerpt; the app ships one parser per bank, and a parser ships
only together with a synthetic test file for every layout it accepts.

Design rules:
* A file is accepted only if, after optional preamble lines, a header row
  matches a known layout exactly (case, spaces, quotes and a trailing ':'
  ignored). Unknown layouts and unknown preamble lines are refused.
* Amounts are parsed to integer cents; "1 150.00 DR", "0.45CR", "1,150.00"
  and a decimal comma are normalised here, not in the ledger.
* Where the file has a balance column, every line must follow from the
  previous balance plus its amount, or the whole file is refused.
* Some downloads list newest first; the parser detects that and reverses.
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import re
from dataclasses import dataclass, field

from ledger_money import LedgerError, parse_rands


@dataclass
class Parsed:
    rows: list[dict]
    opening_balance_cents: int | None
    closing_balance_cents: int | None
    layout: str = ""
    meta: dict = field(default_factory=dict)


_AMOUNT_RE = re.compile(r"^[-+]?\d+(\.\d{1,2})?$")


def parse_amount(text: str, what: str, line_no: int) -> int:
    """'11500.00', '-5 750.00', '1,150.00', '1 150.00 DR', '0.45CR' -> signed cents."""
    s = (text or "").strip().strip("'").strip().upper()
    sign = 1
    if s.endswith("DR"):
        sign, s = -1, s[:-2].strip()
    elif s.endswith("CR"):
        s = s[:-2].strip()
    s = s.replace("\u00a0", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(",", "")                        # thousands comma with a decimal point
    elif s.count(",") == 1 and re.fullmatch(r"[-+]?\d+,\d{2}", s):
        s = s.replace(",", ".")                        # decimal comma
    if not _AMOUNT_RE.match(s):
        raise LedgerError(f"line {line_no}: {what} {text!r} is not an amount")
    cents = parse_rands(s)
    if sign < 0 and cents < 0:
        raise LedgerError(f"line {line_no}: {what} {text!r} is negative and DR")
    return sign * cents


@dataclass(frozen=True)
class Layout:
    name: str
    header: tuple[tuple[str, ...], ...]        # allowed normalised titles per column
    roles: tuple[str, ...]                     # role per column
    date_format: str
    preamble: tuple[str, ...] = ()             # allowed normalised first cells of preamble lines
    tail_joins_description: bool = False       # last column may hold unquoted commas


LAYOUTS = (
    Layout("simple", (("date",), ("amount",), ("balance",), ("description",), ("reference",)),
           ("date", "amount", "balance", "description", "reference"), "%Y/%m/%d"),
    Layout("transaction_history", (("date",), ("amount",), ("balance",), ("description",)),
           ("date", "amount", "balance", "description"), "%Y/%m/%d",
           ("account transaction history", "name", "account", "balance", "download date"),
           tail_joins_description=True),
)


def _norm(cell: str) -> str:
    c = re.sub(r"\s+", " ", (cell or "").replace("\ufeff", "").strip().strip("'\"").strip().lower())
    return c[:-1].strip() if c.endswith(":") else c


def _trim(rec: list[str]) -> list[str]:
    rec = list(rec)
    while rec and not rec[-1].strip():
        rec.pop()
    return rec


def _match_layout(rec: list[str]) -> Layout | None:
    cells = [_norm(c) for c in _trim(rec)]
    for lay in LAYOUTS:
        if len(cells) == len(lay.header) and all(c in ok for c, ok in zip(cells, lay.header)):
            return lay
    return None


def _running_ok(rows: list[dict], balances: list) -> bool:
    return all(balances[i] == balances[i - 1] + rows[i]["amount_cents"] for i in range(1, len(rows)))


def parse_statement(text: str) -> Parsed:
    recs = list(csv.reader(io.StringIO(text.replace("\r\n", "\n").replace("\r", "\n"), newline="")))
    layout, preamble, start = None, [], 0
    for i, rec in enumerate(recs):
        if not any(c.strip() for c in rec):
            continue
        layout = _match_layout(rec)
        if layout:
            start = i + 1
            break
        preamble.append((i + 1, _trim(rec)))
    if layout is None:
        raise LedgerError("header not recognised: no known layout found; unknown layout refused")
    meta: dict = {}
    for n, rec in preamble:
        label = _norm(rec[0])
        if label not in layout.preamble or label in meta:
            raise LedgerError(f"line {n}: preamble line {rec[0]!r} is not part of the {layout.name} layout")
        meta[label] = [c.strip() for c in rec[1:]]

    rows, balances, width = [], [], len(layout.header)
    for n, rec in enumerate(recs[start:], start=start + 1):
        if not rec or all(not c.strip() for c in rec):
            continue
        if layout.tail_joins_description and len(rec) > width:
            rec = rec[:width - 1] + [",".join(rec[width - 1:]).rstrip(", ")]
        if not len(_trim(rec)) <= width <= len(rec):
            raise LedgerError(f"line {n}: expected {width} columns ({layout.name} layout), got {len(rec)}")
        f = dict(zip(layout.roles, (list(rec) + [""] * width)[:width]))
        try:
            d = _dt.datetime.strptime(f["date"].strip().strip("'"), layout.date_format).date()
        except ValueError:
            raise LedgerError(f"line {n}: date {f['date']!r} does not match {layout.date_format}") from None
        rows.append({"booked_date": d.isoformat(), "amount_cents": parse_amount(f["amount"], "amount", n),
                     "description": re.sub(r"\s+", " ", f["description"].strip()),
                     "bank_ref": f.get("reference", "").strip()})
        balances.append(parse_amount(f["balance"], "balance", n) if f["balance"].strip() else None)
    if not rows:
        raise LedgerError("statement has no transaction lines")

    dates = [r["booked_date"] for r in rows]
    if dates[0] > dates[-1] or (dates[0] == dates[-1] and None not in balances
                                and not _running_ok(rows, balances) and _running_ok(rows[::-1], balances[::-1])):
        rows.reverse(); balances.reverse(); dates.reverse()       # newest-first download
        meta["file_order"] = "newest first"
    if dates != sorted(dates):
        raise LedgerError("lines are not in date order")

    opening = closing = None
    if all(b is not None for b in balances):
        opening = running = balances[0] - rows[0]["amount_cents"]
        for i, (r, b) in enumerate(zip(rows, balances)):
            running += r["amount_cents"]
            if running != b:
                raise LedgerError(f"line {i + 1} of {len(rows)}: balance {b} does not follow from the previous "
                                  f"balance and the amount (expected {running}); file refused")
        closing = balances[-1]
    elif any(b is not None for b in balances):
        raise LedgerError("balance column is filled on some lines only; file refused")
    return Parsed(rows, opening, closing, layout.name, meta)


if __name__ == "__main__":
    sample = ("Date,Amount,Balance,Description,Reference\n"
              "2026/09/02,11500.00,36500.00,Payment received,REF001\n"
              "2026/09/05,-5 750.00,30750.00,Supplier payment,REF002\n")
    p = parse_statement(sample)
    print(p.layout, p.opening_balance_cents, p.closing_balance_cents, len(p.rows))

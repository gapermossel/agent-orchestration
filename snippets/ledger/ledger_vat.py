"""Effective-dated VAT lookup and tax-on-post check.

Excerpt from a desktop bookkeeping app (Python + SQLite). Shown here as a
self-contained excerpt; in the app the rate table is a JSON file shipped with
the program, and every statutory table carries effective_from / effective_to /
source fields.

Design rules:
* The rate is looked up by the journal date, never by "today". Exactly one
  row must cover the date; zero or two rows is a refusal, not a guess.
* Every journal line carries a tax type. Rated types are recomputed from the
  exclusive amount and must agree with the VAT line within 1 cent.
* Input VAT over R5 000 (exclusive) needs a stored document before posting.
"""

from __future__ import annotations

import datetime as _dt

from ledger_money import LedgerError, PostRefused, Rate, require_cents


class StatutoryMissing(LedgerError):
    """No statutory table covers the requested date."""


class DocumentRequired(PostRefused):
    """Input VAT over the threshold without a stored tax invoice."""


# In the app this is loaded from a JSON file; the rows below are illustrative.
VAT_RATES = {
    "source": "published VAT rate history (illustrative copy)",
    "rows": [
        {"effective_from": "1993-04-07", "effective_to": "2018-03-31", "rate_percent": 14},
        {"effective_from": "2018-04-01", "effective_to": None, "rate_percent": 15},
    ],
}

TAX_TYPES = frozenset({
    "output_standard", "output_capital", "output_zero", "output_zero_export", "output_exempt",
    "input_standard", "input_capital", "input_import", "reverse_charge", "manual_adjustment",
})
OUTPUT_RATED = ("output_standard", "output_capital")
INPUT_RATED = ("input_standard", "input_capital")
ZERO_TYPES = ("output_zero", "output_zero_export", "output_exempt")
DOC_THRESHOLD_CENTS = 500000          # R5 000 exclusive; "over" means strictly greater
TOLERANCE_CENTS = 1


def _check_date(date: str) -> str:
    _dt.date.fromisoformat(date)       # raises ValueError on anything that is not YYYY-MM-DD
    return date


def _covers(row: dict, date: str) -> bool:
    start, end = row.get("effective_from"), row.get("effective_to")
    return start is not None and start <= date and (end is None or date <= end)


def vat_rate(date: str) -> Rate:
    _check_date(date)
    rows = [r for r in VAT_RATES["rows"] if _covers(r, date)]
    if len(rows) != 1:
        raise StatutoryMissing(f"no single VAT rate row covers {date}")
    return Rate(rows[0]["rate_percent"])


def compute(tax_type: str, exclusive_cents: int, date: str) -> int:
    """VAT on an exclusive amount for the journal date."""
    require_cents(exclusive_cents)
    if tax_type in OUTPUT_RATED or tax_type in INPUT_RATED or tax_type == "reverse_charge":
        return vat_rate(date).on_exclusive(exclusive_cents)
    if tax_type in ZERO_TYPES:
        return 0
    if tax_type == "input_import":
        raise PostRefused("input_import VAT is the amount on the bill of entry; it is not recomputed")
    if tax_type == "manual_adjustment":
        raise PostRefused("manual_adjustment has no rate check")
    raise PostRefused(f"unknown tax type {tax_type!r}")


def split_inclusive(inclusive_cents: int, date: str) -> int:
    """VAT fraction of an inclusive amount: incl x r / (100 + r)."""
    return vat_rate(date).from_inclusive(inclusive_cents)


def check_line(tax_type: str, exclusive_cents: int, vat_cents: int, date: str,
               has_document: bool = False) -> None:
    """Refuse a post whose VAT line does not follow from its base amount."""
    if tax_type not in TAX_TYPES:
        raise PostRefused(f"unknown tax type {tax_type!r}")
    require_cents(vat_cents, "VAT")
    if tax_type in INPUT_RATED and exclusive_cents > DOC_THRESHOLD_CENTS and not has_document:
        raise DocumentRequired("input VAT over R5 000 exclusive needs a stored tax invoice")
    if tax_type in ("input_import", "manual_adjustment"):
        return
    expected = compute(tax_type, exclusive_cents, date)
    if abs(expected - vat_cents) > TOLERANCE_CENTS:
        raise PostRefused(f"{tax_type}: VAT {vat_cents} does not follow from base {exclusive_cents} "
                          f"at {vat_rate(date)!r} on {date} (expected {expected})")


if __name__ == "__main__":
    print(vat_rate("2017-06-30"), vat_rate("2026-09-15"))          # Rate(14%) Rate(15%)
    print(compute("output_standard", 100000, "2026-09-15"))         # 15000
    print(split_inclusive(115000, "2026-09-15"))                    # 15000
    check_line("output_standard", 100000, 15000, "2026-09-15")      # passes silently

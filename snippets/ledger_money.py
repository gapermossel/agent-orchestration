"""Integer money for a small double-entry ledger.

Excerpt from a desktop bookkeeping app (Python + SQLite) built for a small
South African business. Shown here as a self-contained excerpt.

Design rules:
* Money is an integer number of cents. ``Cents`` is an ``int`` subclass that
  is built from a rand string only ("1150.00", "1 150.00", "R1 150.00").
  A float, Decimal or bool argument raises ``TypeError``; there is no path by
  which binary floating point can enter the books.
* ``Rate`` is a whole-number percentage (VAT 15, UIF 1, ...) with integer,
  round-half-away-from-zero arithmetic.
"""

from __future__ import annotations

import re


class LedgerError(Exception):
    """Base class for every refusal the ledger raises."""


class PostRefused(LedgerError):
    """A draft journal cannot be posted (unbalanced, bad line, tax mismatch, ...)."""


# Thousands separators accepted inside a rand string: ASCII space, NBSP,
# narrow NBSP, thin space. Commas are refused (ambiguous decimal mark).
_SEP = "\u0020\u00a0\u202f\u2009"
_RAND_RE = re.compile(r"^(?P<sign>[-+]?)(?:R\s*)?(?P<whole>\d+)(?:\.(?P<frac>\d{1,2}))?$")


def _reject_non_integral(value: object) -> None:
    if isinstance(value, bool):
        raise TypeError("Cents: bool is not money")
    if isinstance(value, float):
        raise TypeError("Cents: float is refused; pass a string such as '1150.00'")
    if not isinstance(value, (int, str)):          # Decimal, Fraction, numpy floats, bytes ...
        raise TypeError(f"Cents: {type(value).__name__} is refused; pass a string")


class Cents(int):
    """Integer cents. ``Cents("1 150.00") == 115000``."""

    def __new__(cls, value: str) -> "Cents":
        _reject_non_integral(value)
        if not isinstance(value, str):
            raise TypeError("Cents(...) takes a rand string only; use Cents.of(int_cents) for integer cents")
        return int.__new__(cls, parse_rands(value))

    @classmethod
    def of(cls, cents: int) -> "Cents":
        """Wrap a value that is already integer cents (not rands)."""
        _reject_non_integral(cents)
        if not isinstance(cents, int):
            raise TypeError("Cents.of takes int cents")
        return int.__new__(cls, int(cents))

    def __repr__(self) -> str:
        return f"Cents({format_cents(int(self))!r})"


def parse_rands(text: str) -> int:
    """Parse a rand string to integer cents without touching float."""
    if not isinstance(text, str):
        raise TypeError("parse_rands takes a string")
    s = text.strip()
    for ch in _SEP:
        s = s.replace(ch, "")
    m = _RAND_RE.match(s)
    if not m:
        raise ValueError(f"not a rand amount: {text!r} (digits, optional space thousands, '.' and at most 2 decimals)")
    whole = int(m.group("whole"))
    frac = (m.group("frac") or "").ljust(2, "0")
    cents = whole * 100 + int(frac or "0")
    return -cents if m.group("sign") == "-" else cents


def format_cents(cents: int, sep: str = " ") -> str:
    """115000 -> '1 150.00' (South African style, space thousands)."""
    _reject_non_integral(cents)
    if not isinstance(cents, int):
        raise TypeError("format_cents takes int cents")
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(int(cents)), 100)
    return f"{sign}{whole:,}".replace(",", sep) + f".{frac:02d}"


def require_cents(value: object, what: str = "amount") -> int:
    """Accept an int (cents) for ledger storage; refuse float/bool/str/Decimal."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise PostRefused(f"{what} must be integer cents, got {type(value).__name__}")
    return int(value)


def div_round_half_up(numerator: int, denominator: int) -> int:
    """Integer division rounding half away from zero."""
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    sign = -1 if numerator < 0 else 1
    q, r = divmod(abs(numerator), denominator)
    if r * 2 >= denominator:
        q += 1
    return sign * q


class Rate:
    """A whole-number percentage (no float)."""

    __slots__ = ("percent",)

    def __init__(self, percent: int):
        if isinstance(percent, bool) or not isinstance(percent, int):
            raise TypeError("Rate takes an int percent")
        if percent < 0 or percent > 100:
            raise ValueError("Rate percent out of range")
        self.percent = percent

    def on_exclusive(self, exclusive_cents: int) -> int:
        """Tax on an exclusive amount: excl * r / 100."""
        require_cents(exclusive_cents)
        return div_round_half_up(exclusive_cents * self.percent, 100)

    def from_inclusive(self, inclusive_cents: int) -> int:
        """Tax fraction of an inclusive amount: incl * r / (100 + r)."""
        require_cents(inclusive_cents)
        return div_round_half_up(inclusive_cents * self.percent, 100 + self.percent)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Rate) and other.percent == self.percent

    def __hash__(self) -> int:
        return hash(self.percent)

    def __repr__(self) -> str:
        return f"Rate({self.percent}%)"

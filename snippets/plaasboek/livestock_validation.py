"""Input validation for an offline livestock record book.

Excerpt from a desktop/phone livestock app (Python + Flet UI + SQLite,
English/Afrikaans). Shown here as a self-contained excerpt.

Every check raises ValidationError with the name of the form field, so the UI
can put the message under the right input. Money is kept as a 2-decimal
string (Decimal under the hood), never as a float. Dates accept the formats
people actually type and are stored as ISO dates.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

SPECIES = ("cattle", "sheep", "goat")
SEXES = ("female", "male", "unknown")
STATUSES = ("active", "sold", "dead", "missing")

# Allowed status changes. Sold and dead are terminal in normal use; undoing
# them is a separate, deliberate action in settings.
STATUS_TRANSITIONS = {
    "active": {"active", "sold", "dead", "missing"},
    "missing": {"missing", "active", "sold", "dead"},
    "sold": {"sold"},
    "dead": {"dead"},
}


class ValidationError(Exception):
    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(message)
        self.field = field
        self.message = message


def parse_money(value) -> str:
    """'R 1 250,5' / '1250.50' / 1250 -> '1250.50'. Negative amounts are refused."""
    if value is None or str(value).strip() == "":
        raise ValidationError("Amount is required", "amount")
    text = str(value).strip().replace("R", "").replace(" ", "").replace(",", ".")
    try:
        d = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValidationError("Invalid amount", "amount")
    if d < 0:
        raise ValidationError("Amount must be zero or more", "amount")
    return f"{d.quantize(Decimal('0.01'))}"


def parse_date(value, field: str = "date", allow_empty: bool = False) -> Optional[str]:
    if value is None or str(value).strip() == "":
        if allow_empty:
            return None
        raise ValidationError(f"{field} is required", field)
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValidationError(f"Invalid {field} (use YYYY-MM-DD)", field)


def no_future_dob(dob: Optional[str]) -> Optional[str]:
    if dob and date.fromisoformat(dob) > date.today():
        raise ValidationError("Date of birth cannot be in the future", "dob")
    return dob


def require_tag(tag: Optional[str]) -> str:
    t = (tag or "").strip()
    if not t:
        raise ValidationError("Tag is required", "tag_visual")
    if len(t) > 64:
        raise ValidationError("Tag is too long", "tag_visual")
    return t


def require_choice(value: Optional[str], allowed: tuple, field: str, default: str = "") -> str:
    v = (value or default).strip().lower()
    if v not in allowed:
        raise ValidationError(f"Invalid {field}: choose one of {', '.join(allowed)}", field)
    return v


def can_transition(old: str, new: str) -> bool:
    return new in STATUS_TRANSITIONS.get(old, set())


def utc_now_iso() -> str:
    # Millisecond precision so two copies edited in the same second still
    # differ, which the merge step relies on to detect a conflict.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def parse_result(fn, *args, **kwargs) -> Tuple[bool, Optional[str], Optional[object]]:
    """Run a validator and return (ok, message, value) instead of raising."""
    try:
        return True, None, fn(*args, **kwargs)
    except ValidationError as e:
        return False, e.message, None


if __name__ == "__main__":
    print(parse_money("R 1 250,5"))                      # 1250.50
    print(parse_date("03/02/2026"))                      # 2026-02-03
    print(parse_result(parse_money, "-5"))               # (False, 'Amount must be zero or more', None)
    print(parse_result(require_choice, "horse", SPECIES, "species")[1])
    print(can_transition("active", "sold"), can_transition("sold", "active"))  # True False

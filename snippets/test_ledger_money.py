"""Unit tests for the money, VAT and statement-parser excerpts (pytest).

Excerpt from the test suite of a desktop bookkeeping app (Python + SQLite).
Run from this folder with:  python3 -m pytest -q test_ledger_money.py
All amounts and statement lines below are synthetic.
"""

import decimal
import pathlib
import re

import pytest

from bank_statement_parser import parse_statement
from ledger_money import Cents, LedgerError, PostRefused, Rate, format_cents
from ledger_vat import DocumentRequired, StatutoryMissing, check_line, vat_rate


def test_cents_from_string():
    assert Cents("1150.00") == 115000
    assert Cents("1 150.00") == 115000
    assert Cents("1\u00a0150.00") == 115000      # NBSP, as bank exports use
    assert Cents("R1 150.00") == 115000
    assert Cents("-12.34") == -1234


def test_float_is_refused():
    with pytest.raises(TypeError):
        Cents(1150.00)
    with pytest.raises(TypeError):
        Cents.of(115000.0)


@pytest.mark.parametrize("bad", [True, decimal.Decimal("1150.00"), 115000, None, b"1150.00"])
def test_non_string_constructor_refused(bad):
    with pytest.raises(TypeError):
        Cents(bad)


@pytest.mark.parametrize("bad", ["1,150.00", "1150.001", "", "abc", "1.2.3", "1150.00 DR"])
def test_malformed_strings_refused(bad):
    with pytest.raises(ValueError):
        Cents(bad)


def test_format_cents():
    assert format_cents(115000) == "1 150.00"
    assert format_cents(-5) == "-0.05"


def test_rate_integer_rounding():
    r = Rate(15)
    assert r.on_exclusive(100000) == 15000
    assert r.from_inclusive(115000) == 15000
    assert r.on_exclusive(3) == 0          # 0.45 -> 0
    assert r.on_exclusive(10) == 2         # 1.5 -> 2 (half up)
    assert r.on_exclusive(-10) == -2       # half away from zero
    with pytest.raises(PostRefused):
        r.on_exclusive(100.0)


def test_vat_rate_follows_the_journal_date():
    assert vat_rate("2018-03-31") == Rate(14)
    assert vat_rate("2018-04-01") == Rate(15)
    with pytest.raises(StatutoryMissing):
        vat_rate("1990-01-01")


def test_vat_line_must_follow_from_base():
    check_line("output_standard", 100000, 15001, "2026-09-15")      # within 1 cent
    with pytest.raises(PostRefused, match="does not follow"):
        check_line("output_standard", 100000, 14000, "2026-09-15")
    with pytest.raises(DocumentRequired):
        check_line("input_standard", 500001, 75000, "2026-09-15")


def test_statement_running_balance_is_proved():
    good = "Date,Amount,Balance,Description,Reference\n2026/09/02,100.00,1100.00,In,R1\n2026/09/03,-50.00,1050.00,Out,R2\n"
    p = parse_statement(good)
    assert (p.opening_balance_cents, p.closing_balance_cents) == (100000, 105000)
    with pytest.raises(LedgerError, match="does not follow"):
        parse_statement(good.replace("1050.00", "1049.00"))


def test_newest_first_download_is_reversed():
    text = ("ACCOUNT TRANSACTION HISTORY\nDate,Amount,Balance,Description\n"
            "2026/09/03,-50.00,1050.00,Card purchase, store 12\n2026/09/02,100.00,1100.00,Deposit\n")
    p = parse_statement(text)
    assert [r["booked_date"] for r in p.rows] == ["2026-09-02", "2026-09-03"]
    assert p.rows[1]["description"] == "Card purchase, store 12"
    assert p.meta["file_order"] == "newest first"


def test_unknown_layout_refused():
    with pytest.raises(LedgerError, match="unknown layout"):
        parse_statement("When,How much,Note\n2026/09/02,1.00,x\n")


def test_no_network_imports_in_ledger_code():
    """Static guard: the ledger is offline-only."""
    banned = re.compile(r"^\s*(import|from)\s+(socket|urllib|http|requests|httpx|aiohttp|ftplib|smtplib)\b", re.M)
    for f in pathlib.Path(__file__).parent.glob("*.py"):
        if f.name.startswith("test_"):
            continue
        assert not banned.search(f.read_text()), f"network import in {f.name}"

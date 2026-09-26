from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.invoice import Invoice
from app.schemas.money import parse_date, parse_money


def base(**over):
    inv = {
        "invoice_number": "INV-1", "invoice_date": "2026-09-01", "due_date": "2026-09-30", "currency": "EUR",
        "vendor": {"name": "Acme"}, "line_items": [{"description": "Thing", "quantity": 2, "unit_price": "10.00",
                                                    "amount": "20.00"}],
        "totals": {"subtotal": "20.00", "tax": "0", "total": "20.00"},
    }
    inv.update(over)
    return inv


@pytest.mark.parametrize("raw,expected", [
    ("1,234.50", "1234.50"), ("1.234,50", "1234.50"), ("€ 99", "99"), ("$2,500.00", "2500.00"),
    ("12,000", "12000"), ("1.234.567", "1234567"), ("(12.00)", "-12.00"), (19.9, "19.9"),
])
def test_parse_money(raw, expected):
    assert parse_money(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", ["abc", "", True])
def test_parse_money_rejects(raw):
    with pytest.raises(ValueError):
        parse_money(raw)


def test_parse_date_formats():
    assert str(parse_date("14.09.2026")) == "2026-09-14"
    assert str(parse_date("09/14/2026", prefer_mdy=True)) == "2026-09-14"
    assert str(parse_date("March 3rd, 2026")) == "2026-03-03"
    with pytest.raises(ValueError):
        parse_date("next Tuesday")


def test_valid_invoice_and_money_serialised_as_strings():
    inv = Invoice.model_validate(base())
    out = inv.model_dump(mode="json")
    assert out["totals"]["total"] == "20.00" and out["line_items"][0]["quantity"] == "2"


@pytest.mark.parametrize("override,field", [
    ({"currency": "XYZ"}, "currency"),
    ({"invoice_date": "not a date"}, "invoice_date"),
    ({"line_items": []}, "line_items"),
    ({"line_items": [{"description": "x", "quantity": 0, "unit_price": 1, "amount": 0}]}, "line_items.0.quantity"),
    ({"line_items": [{"description": "x", "quantity": 1, "unit_price": -5, "amount": -5}]}, "line_items.0.unit_price"),
    ({"vendor": {"name": ""}}, "vendor.name"),
    ({"vendor": {"name": "A", "email": "not-an-email"}}, "vendor.email"),
    ({"surprise": "field"}, "surprise"),
])
def test_invalid_invoices_rejected(override, field):
    with pytest.raises(ValidationError) as exc:
        Invoice.model_validate(base(**override))
    locs = {".".join(str(p) for p in e["loc"]) for e in exc.value.errors()}
    assert field in locs


def test_due_date_before_invoice_date_rejected():
    with pytest.raises(ValidationError, match="due_date is before invoice_date"):
        Invoice.model_validate(base(due_date="2026-08-01"))


def test_currency_symbol_normalised():
    assert Invoice.model_validate(base(currency="€")).currency == "EUR"

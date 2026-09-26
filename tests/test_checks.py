from datetime import date
from decimal import Decimal

from app.schemas.invoice import Invoice
from app.validate.checks import run_checks

TOL = Decimal("0.02")
TODAY = date(2026, 9, 26)


def inv(lines, subtotal, total, tax="0", discount="0", tax_rate=None, invoice_date="2026-09-01"):
    return Invoice.model_validate({
        "invoice_number": "X", "invoice_date": invoice_date, "currency": "EUR", "vendor": {"name": "V"},
        "line_items": [{"description": f"l{i}", "quantity": q, "unit_price": p, "amount": a}
                       for i, (q, p, a) in enumerate(lines)],
        "totals": {"subtotal": subtotal, "tax": tax, "discount": discount, "tax_rate": tax_rate, "total": total},
    })


def codes(invoice):
    return {f.code for f in run_checks(invoice, TOL, TODAY)}


def test_consistent_invoice_has_no_flags():
    assert codes(inv([(2, "10", "20"), (1, "5.50", "5.50")], "25.50", "30.86", tax="5.36", tax_rate=21)) == set()


def test_rounding_within_tolerance_is_ok():
    assert codes(inv([(3, "0.333", "1.00")], "1.00", "1.00")) == set()


def test_line_amount_mismatch():
    assert "line_amount_mismatch" in codes(inv([(2, "10", "25")], "25", "25"))


def test_subtotal_mismatch():
    assert "subtotal_mismatch" in codes(inv([(1, "10", "10")], "12", "12"))


def test_total_mismatch_reports_difference():
    flags = run_checks(inv([(1, "100", "100")], "100", "140", tax="0"), TOL, TODAY)
    f = next(f for f in flags if f.code == "total_mismatch")
    assert f.severity == "error" and "+40.00" in f.message


def test_discount_is_subtracted():
    assert codes(inv([(1, "100", "100")], "100", "90", discount="10")) == set()


def test_tax_rate_mismatch():
    assert "tax_rate_mismatch" in codes(inv([(1, "100", "100")], "100", "130", tax="30", tax_rate=21))


def test_future_date_and_non_positive_total():
    c = codes(inv([(1, "0", "0")], "0", "0", invoice_date="2027-01-01"))
    assert {"date_in_future", "non_positive_total"} <= c

"""Arithmetic and sanity checks. Problems are flagged, never silently corrected:
the extracted invoice always shows what is printed on the document."""
from datetime import date, timedelta
from decimal import Decimal

from app.schemas.api import Flag
from app.schemas.invoice import Invoice


def run_checks(inv: Invoice, tolerance: Decimal, today: date | None = None) -> list[Flag]:
    today = today or date.today()
    flags: list[Flag] = []
    t = inv.totals

    for i, li in enumerate(inv.line_items):
        expected = li.quantity * li.unit_price
        if abs(expected - li.amount) > tolerance:
            flags.append(Flag(field=f"line_items[{i}].amount", code="line_amount_mismatch", severity="warning",
                              message=f"{li.quantity} × {li.unit_price} = {expected:.2f}, but the line says {li.amount:.2f}."))

    lines_sum = sum((li.amount for li in inv.line_items), Decimal("0"))
    if abs(lines_sum - t.subtotal) > tolerance:
        flags.append(Flag(field="totals.subtotal", code="subtotal_mismatch", severity="error",
                          message=f"Line items add up to {lines_sum:.2f}, but the subtotal says {t.subtotal:.2f}."))

    if t.tax_rate is not None:
        expected_tax = (t.subtotal - t.discount) * t.tax_rate / 100
        if abs(expected_tax - t.tax) > tolerance:
            flags.append(Flag(field="totals.tax", code="tax_rate_mismatch", severity="warning",
                              message=f"{t.tax_rate}% of {t.subtotal - t.discount:.2f} is {expected_tax:.2f}, "
                                      f"but the tax says {t.tax:.2f}."))

    expected_total = t.subtotal - t.discount + t.tax
    if abs(expected_total - t.total) > tolerance:
        flags.append(Flag(field="totals.total", code="total_mismatch", severity="error",
                          message=f"Subtotal − discount + tax = {expected_total:.2f}, but the total says "
                                  f"{t.total:.2f} (difference {t.total - expected_total:+.2f})."))

    if t.total <= 0:
        flags.append(Flag(field="totals.total", code="non_positive_total", severity="warning",
                          message="The total is zero or negative. Is this a credit note?"))
    if inv.invoice_date > today + timedelta(days=1):
        flags.append(Flag(field="invoice_date", code="date_in_future", severity="warning",
                          message=f"The invoice date {inv.invoice_date} is in the future."))
    return flags

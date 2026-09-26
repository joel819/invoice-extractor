import pytest

from app.errors import ExtractionFailed
from app.extract.pdf_text import read_pdf
from app.extract.rule_extractor import extract, is_ambiguous_date
from tests.conftest import sample

# Answer key for the 5 bundled samples (see scripts/make_sample_invoices.py).
EXPECTED = {
    "01-clean-simple.pdf": dict(number="AF-2026-0142", date="2026-09-03", due="2026-10-03", currency="EUR",
                                vendor="Alder & Finch Design Studio", lines=3, subtotal="2200.00",
                                discount="0.00", tax="462.00", total="2662.00"),
    "02-multi-line-tax.pdf": dict(number="NG-448913", date="2026-09-14", due="2026-09-28", currency="EUR",
                                  vendor="Northgate Buerobedarf GmbH", lines=12, subtotal="4324.35",
                                  discount="216.22", tax="780.54", total="4888.67"),
    "03-two-pages.pdf": dict(number="HLC-2026-0917", date="2026-09-17", due="2026-10-17", currency="GBP",
                             vendor="Harbour Lane Catering Ltd", lines=30, subtotal="11281.00",
                             discount="0.00", tax="2256.20", total="13537.20"),
    "04-math-error.pdf": dict(number="BIS-00731", date="2026-09-10", due="2026-09-24", currency="EUR",
                              vendor="Brightline IT Services", lines=4, subtotal="1210.00",
                              discount="0.00", tax="278.30", total="1528.30"),  # printed total, not "fixed"
    "05-us-format-usd.pdf": dict(number="CR-1187", date="2026-09-14", due="2026-10-14", currency="USD",
                                 vendor="Cedar Ridge Consulting LLC", lines=4, subtotal="9336.40",
                                 discount="0.00", tax="770.25", total="10106.65"),
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_samples_extract_correctly(name):
    exp = EXPECTED[name]
    inv, _ = extract(read_pdf(sample(name), 20).text)
    d = inv.model_dump(mode="json")
    assert (d["invoice_number"], d["invoice_date"], d["due_date"], d["currency"], d["vendor"]["name"]) == (
        exp["number"], exp["date"], exp["due"], exp["currency"], exp["vendor"])
    assert len(d["line_items"]) == exp["lines"]
    t = d["totals"]
    assert (t["subtotal"], t["discount"], t["tax"], t["total"]) == (
        exp["subtotal"], exp["discount"], exp["tax"], exp["total"])


def test_vendor_details_and_bill_to():
    inv, _ = extract(read_pdf(sample("01-clean-simple.pdf"), 20).text)
    assert inv.vendor.tax_id == "NL859301762B01"
    assert inv.vendor.email == "hello@alderfinch.example"
    assert inv.bill_to.startswith("Kestrel Outdoor Supply")


def test_line_items_from_both_pages():
    inv, _ = extract(read_pdf(sample("03-two-pages.pdf"), 20).text)
    assert inv.line_items[0].description == "Welcome drinks reception"
    assert inv.line_items[-1].description == "Venue kitchen deep clean"


def test_ambiguous_dates():
    assert is_ambiguous_date("03/04/2026") and not is_ambiguous_date("14/09/2026")
    assert not is_ambiguous_date("2026-09-03") and not is_ambiguous_date(None)


def test_non_invoice_text_fails_clearly():
    with pytest.raises(ExtractionFailed) as exc:
        extract("Meeting notes\n\nWe discussed the roadmap for next quarter.")
    assert exc.value.not_invoice

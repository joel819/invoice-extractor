from decimal import Decimal

from app.extract.pdf_text import read_pdf
from app.extract.rule_extractor import extract
from app.validate.checks import run_checks
from app.validate.confidence import score
from tests.conftest import sample


def _prepare(name):
    text = read_pdf(sample(name), 20).text
    inv, unc = extract(text)
    return text, inv, unc


def test_clean_invoice_is_fully_confident():
    text, inv, unc = _prepare("01-clean-simple.pdf")
    conf, extra = score(inv, text, run_checks(inv, Decimal("0.02")), unc)
    assert extra == [] and min(conf.values()) >= 0.9


def test_hallucinated_value_gets_low_confidence_and_flag():
    text, inv, unc = _prepare("01-clean-simple.pdf")
    inv.vendor.name = "Totally Different Vendor Ltd"  # what a hallucinating model might return
    inv.totals.total = Decimal("9999.99")
    conf, extra = score(inv, text, [], unc)
    assert conf["vendor.name"] < 0.7 and conf["totals.total"] < 0.7
    assert {f.field for f in extra} == {"vendor.name", "totals.total"}


def test_eu_number_format_is_found_in_text():
    text, inv, unc = _prepare("02-multi-line-tax.pdf")  # amounts printed like 1.298,00
    conf, extra = score(inv, text, [], unc)
    assert extra == []


def test_failed_check_lowers_involved_fields_only():
    text, inv, unc = _prepare("04-math-error.pdf")
    flags = run_checks(inv, Decimal("0.02"))
    conf, _ = score(inv, text, flags, unc)
    assert conf["totals.total"] < 0.7 and conf["totals.subtotal"] < 0.7
    assert conf["vendor.name"] == 1.0
    assert "totals.discount" in conf and conf["totals.discount"] >= 0.7  # zero discount isn't implicated


def test_self_reported_uncertainty_lowers_confidence():
    text, inv, _ = _prepare("01-clean-simple.pdf")
    conf, _ = score(inv, text, [], ["invoice_date"])
    assert conf["invoice_date"] == 0.7

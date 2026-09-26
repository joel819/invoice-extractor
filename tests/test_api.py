import pytest
from pypdf import PdfWriter

from tests.conftest import make_pdf, sample


def test_extract_clean_invoice(post):
    r = post(sample("01-clean-simple.pdf"), "01-clean-simple.pdf")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["mode"] == "demo" and body["flags"] == []
    assert body["invoice"]["vendor"]["name"] == "Alder & Finch Design Studio"
    assert body["confidence"]["totals.total"] == 1.0 and body["id"]


def test_math_error_needs_review_and_is_not_fixed(post):
    body = post(sample("04-math-error.pdf"), "04-math-error.pdf").json()
    assert body["status"] == "needs_review"
    assert body["invoice"]["totals"]["total"] == "1528.30"  # what's printed, not the corrected 1488.30
    assert [f["code"] for f in body["flags"]] == ["total_mismatch"]
    assert "totals.total" in body["low_confidence_fields"]


@pytest.mark.parametrize("name", ["02-multi-line-tax.pdf", "03-two-pages.pdf", "05-us-format-usd.pdf"])
def test_other_samples_ok(post, name):
    assert post(sample(name), name).json()["status"] == "ok"


def test_history(client, post):
    post(sample("01-clean-simple.pdf"))
    post(sample("04-math-error.pdf"))
    hist = client.get("/extractions").json()
    assert [h["invoice_number"] for h in hist] == ["BIS-00731", "AF-2026-0142"]
    one = client.get(f"/extractions/{hist[0]['id']}").json()
    assert one["flags"][0]["code"] == "total_mismatch"
    assert client.get("/extractions/999").status_code == 404


# ---- rejections: every one returns {error, message, details} ----

def _err(r, status, code):
    assert r.status_code == status, r.text
    body = r.json()
    assert body["error"] == code and body["message"]
    return body


def test_missing_file(client):
    _err(client.post("/extract"), 400, "invalid_request")


def test_empty_file(post):
    _err(post(b""), 400, "empty_file")


def test_wrong_extension(post):
    _err(post(b"hello", "notes.txt", "text/plain"), 415, "not_a_pdf")


def test_fake_pdf(post):
    _err(post(b"this is not a pdf", "fake.pdf"), 415, "not_a_pdf")


def test_too_large(post, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    _err(post(sample("01-clean-simple.pdf")), 413, "file_too_large")


def test_scanned_pdf_without_text(post):
    w = PdfWriter()
    w.add_blank_page(width=595, height=842)
    from io import BytesIO

    buf = BytesIO()
    w.write(buf)
    body = _err(post(buf.getvalue()), 422, "no_text_layer")
    assert "OCR" in body["message"]


def test_corrupt_pdf(post):
    _err(post(b"%PDF-1.4\n garbage garbage"), 422, "unreadable_pdf")


def test_encrypted_pdf(post):
    from io import BytesIO

    from pypdf import PdfReader

    w = PdfWriter(clone_from=PdfReader(BytesIO(sample("01-clean-simple.pdf"))))
    w.encrypt("secret")
    buf = BytesIO()
    w.write(buf)
    _err(post(buf.getvalue()), 422, "encrypted_pdf")


def test_not_an_invoice(post):
    _err(post(make_pdf(["Team offsite agenda", "", "09:00 Coffee and welcome", "10:00 Roadmap review"])),
         422, "not_an_invoice")


def test_invoice_missing_required_fields_lists_them(post):
    pdf = make_pdf(["Some Vendor Ltd", "INVOICE", "Invoice No: 77",
                    "Widget                     2        5.00         10.00"])
    body = _err(post(pdf), 422, "extraction_failed")
    fields = {d["field"] for d in body["details"]}
    assert {"invoice_date", "currency"} <= fields


def test_samples_endpoint(client):
    names = client.get("/samples").json()
    assert len(names) == 5
    assert client.get(f"/samples/{names[0]}").content.startswith(b"%PDF")
    assert client.get("/samples/..%2Fmain.py").status_code == 404


def test_index_and_health(client):
    assert "Invoice Extractor" in client.get("/").text
    assert client.get("/health").json()["demo_mode"] is True

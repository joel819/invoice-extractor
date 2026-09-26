"""PDF bytes -> validated invoice JSON with confidence and flags."""
import hashlib
import logging
import time
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import ExtractionFailed, InvoiceError
from app.extract import get_llm_extractor, rule_extractor
from app.extract.llm_extractor import LLMUnavailable
from app.extract.pdf_text import read_pdf
from app.models import Extraction
from app.schemas.api import ExtractionOut
from app.validate.checks import run_checks
from app.validate.confidence import score

log = logging.getLogger("uvicorn.error")


def validate_upload(filename: str, data: bytes) -> None:
    limit = get_settings().max_upload_mb * 1024 * 1024
    if not data:
        raise InvoiceError(400, "empty_file", "The uploaded file is empty.")
    if len(data) > limit:
        raise InvoiceError(413, "file_too_large", f"The file is larger than {limit // 1048576} MB.")
    if not filename.lower().endswith(".pdf"):
        raise InvoiceError(415, "not_a_pdf", f"'{filename}' is not a .pdf file. Only PDF invoices are accepted.")


def _extract(text: str):
    """Returns (invoice, uncertain, mode). LLM first when configured; rules otherwise or on LLM failure."""
    llm = get_llm_extractor()
    if llm is not None:
        try:
            inv, unc = llm.extract(text)
            return inv, unc, "groq"
        except LLMUnavailable as exc:
            log.warning("LLM unavailable, using rule extractor: %s", exc)
            mode = "fallback"
        except ExtractionFailed as exc:
            if exc.not_invoice:
                raise
            log.warning("LLM output failed validation, using rule extractor: %s", exc.details)
            mode = "fallback"
    else:
        mode = "demo"
    inv, unc = rule_extractor.extract(text)
    return inv, unc, mode


def process(db: Session, filename: str, data: bytes) -> ExtractionOut:
    s = get_settings()
    start = time.perf_counter()
    validate_upload(filename, data)
    pdf = read_pdf(data, s.max_pages)
    try:
        invoice, uncertain, mode = _extract(pdf.text)
    except ExtractionFailed as exc:
        if exc.not_invoice:
            raise InvoiceError(422, "not_an_invoice", f"This doesn't look like an invoice: {exc}") from None
        raise InvoiceError(422, "extraction_failed",
                           f"{exc} Check that the PDF is an invoice with line items and a total.",
                           exc.details) from None

    flags = run_checks(invoice, Decimal(s.money_tolerance))
    confidence, extra = score(invoice, pdf.text, flags, uncertain)
    flags += extra
    low = sorted(f for f, c in confidence.items() if c < s.low_confidence_threshold)
    status = "needs_review" if low or any(f.severity == "error" for f in flags) else "ok"

    result = ExtractionOut(
        filename=filename, status=status, mode=mode, pages=len(pdf.pages),
        processing_ms=int((time.perf_counter() - start) * 1000),
        invoice=invoice, confidence=confidence, low_confidence_fields=low, flags=flags,
    )
    row = Extraction(filename=filename, sha256=hashlib.sha256(data).hexdigest(), status=status, mode=mode,
                     pages=result.pages, processing_ms=result.processing_ms, result_json="")
    db.add(row)
    db.flush()
    result.id, result.created_at = row.id, row.created_at
    row.result_json = result.model_dump_json()
    db.commit()
    return result

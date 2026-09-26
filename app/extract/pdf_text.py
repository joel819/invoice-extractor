"""PDF -> text, keeping table rows on one line (pypdf layout mode)."""
import re
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.errors import InvoiceError

_BLANKS = re.compile(r"\n{3,}")
_WIDE = re.compile(r" {6,}")


@dataclass
class PdfText:
    pages: list[str]

    @property
    def text(self) -> str:
        return "\n\n".join(f"--- page {i} ---\n{p}" for i, p in enumerate(self.pages, start=1))


def _tidy(page: str) -> str:
    lines = [ln.rstrip() for ln in page.replace("\x00", "").splitlines()]
    text = "\n".join(lines).strip("\n")
    text = _WIDE.sub("     ", text)  # keep columns apart, drop wasted width
    return _BLANKS.sub("\n\n", text)


def _page_text(page) -> str:
    """Layout mode keeps table rows on one line; some pages (e.g. with no content stream)
    break it, so fall back to plain extraction, then to nothing."""
    for kwargs in ({"extraction_mode": "layout"}, {}):
        try:
            return page.extract_text(**kwargs) or ""
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
    return ""


def read_pdf(data: bytes, max_pages: int) -> PdfText:
    if not data.startswith(b"%PDF"):
        raise InvoiceError(415, "not_a_pdf", "The file is not a PDF (it doesn't start with the %PDF header).")
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise InvoiceError(422, "encrypted_pdf", "The PDF is password-protected. Upload an unlocked copy.")
        if len(reader.pages) > max_pages:
            raise InvoiceError(422, "too_many_pages",
                               f"The PDF has {len(reader.pages)} pages; the limit is {max_pages}.")
        pages = [_tidy(_page_text(p)) for p in reader.pages]
    except InvoiceError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise InvoiceError(422, "unreadable_pdf", f"The PDF could not be read: {exc}") from None
    if sum(len(p.strip()) for p in pages) < 20:
        raise InvoiceError(
            422, "no_text_layer",
            "No text could be extracted. This looks like a scanned or image-only PDF, which needs OCR "
            "(not supported). Export the invoice as a text PDF instead.",
        )
    return PdfText(pages)

"""Demo-mode extractor: no API key needed.

Parses common invoice layouts with patterns: "Label: value" header fields, a table of
description / qty / unit price / amount rows, and "label  amount" totals. It handles the
sample invoices and similar layouts; unusual layouts are what the LLM extractor is for.
"""
import re

from pydantic import ValidationError

from app.errors import ExtractionFailed
from app.schemas.invoice import Invoice
from app.schemas.money import parse_date

NUM = r"-?[€$£]?\s?\d[\d.,]*"
ROW = re.compile(rf"^(?P<desc>\S.*?)\s{{2,}}(?P<qty>\d+(?:[.,]\d+)?)\s{{2,}}(?P<unit>{NUM})\s{{2,}}(?P<amount>{NUM})\s*$")
TOTAL_ROW = re.compile(rf"^\s*(?P<label>[A-Za-z][A-Za-z0-9 .,()%/-]*?)\s{{2,}}(?P<value>{NUM})\s*$")
LABELLED = re.compile(r"^\s*(?P<label>[A-Za-z][A-Za-z #/.-]{1,40}?)\s*:\s*(?P<value>\S.*?)\s*$")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PERCENT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
TAX_ID_LABEL = re.compile(r"\b(VAT|USt|Tax ID|TIN|EIN|GST|ABN)\b", re.I)
ISO = re.compile(r"\b(EUR|USD|GBP|CHF|SEK|NOK|DKK|PLN|CZK|CAD|AUD|JPY|NGN|TRY)\b")
HEADER_WORDS = {"description", "qty", "quantity", "unit", "price", "amount"}


def _find_label(fields: dict[str, str], *patterns: str) -> str | None:
    for pat in patterns:
        for label, value in fields.items():
            if re.fullmatch(pat, label):
                return value
    return None


def extract(text: str) -> tuple[Invoice, list[str]]:
    """Returns (invoice, uncertain_fields). Raises ExtractionFailed."""
    lines = [ln for ln in text.splitlines() if not ln.startswith("--- page ")]
    content = [ln.strip() for ln in lines if ln.strip()]
    if not content:
        raise ExtractionFailed("The document is empty.", not_invoice=True)
    uncertain: list[str] = []

    fields: dict[str, str] = {}
    for ln in content:
        m = LABELLED.match(ln)
        if m and not ROW.match(ln):
            fields.setdefault(m["label"].strip().lower(), m["value"])

    # Vendor block: the lines at the top of the page, before "INVOICE" / the first header field.
    vendor_lines: list[str] = []
    for ln in content:
        if ln.upper() in ("INVOICE", "TAX INVOICE") or re.match(r"(?i)invoice\s*(no|number|#)", ln):
            break
        vendor_lines.append(ln)
    tax_id = email = None
    address = []
    for ln in vendor_lines[1:]:
        if EMAIL.search(ln):
            email = EMAIL.search(ln).group()
        elif TAX_ID_LABEL.search(ln) and ":" in ln:
            tax_id = ln.rsplit(":", 1)[1].strip()
        else:
            address.append(ln)

    bill_to: list[str] = []
    for i, ln in enumerate(lines):
        if re.match(r"(?i)\s*(bill(ed)? to|invoice to|customer)\s*:?\s*$", ln):
            for nxt in lines[i + 1:]:
                if not nxt.strip():
                    break
                bill_to.append(nxt.strip())
            break

    items, totals = [], {}
    for ln in content:
        row = ROW.match(ln)
        if row and not set(row["desc"].lower().split()) <= HEADER_WORDS:
            items.append({"description": row["desc"], "quantity": row["qty"],
                          "unit_price": row["unit"], "amount": row["amount"]})
            continue
        tot = TOTAL_ROW.match(ln)
        if not tot:
            continue
        label, value = tot["label"].strip(), tot["value"]
        low = label.lower()
        if low.startswith("subtotal") or low.startswith("sub-total") or low.startswith("net amount"):
            totals["subtotal"] = value
        elif low.startswith("discount"):
            totals["discount"] = value.lstrip("-")
        elif re.match(r"(vat|tax|sales tax|gst|ust|mwst)\b", low):
            totals["tax"] = value
            if pct := PERCENT.search(label):
                totals["tax_rate"] = pct.group(1).replace(",", ".")
        elif re.match(r"(total|amount due|balance due|grand total)\b", low):
            totals["total"] = value
            if iso := ISO.search(label):
                fields.setdefault("_currency", iso.group())

    currency = fields.get("_currency") or fields.get("currency")
    if not currency:
        iso = ISO.search(text)
        currency = iso.group() if iso else next((s for s in "€$£" if s in text), None)
        uncertain.append("currency")
    prefer_mdy = currency in ("USD", "$")

    def date_field(*patterns: str) -> str | None:
        raw = _find_label(fields, *patterns)
        if raw is None:
            return None
        try:
            return parse_date(raw, prefer_mdy=prefer_mdy).isoformat()
        except ValueError:
            return raw  # let schema validation report it

    if "subtotal" not in totals and items:
        uncertain.append("totals.subtotal")
    raw = {
        "invoice_number": _find_label(fields, r"invoice\s*(no\.?|number|#|id)", r"invoice", r"(no\.?|number|#)"),
        "invoice_date": date_field(r"invoice date", r"date of issue", r"issue date", r"date", r"invoice date.*"),
        "due_date": date_field(r"due date", r"payment due", r"due", r"due by", r"payment due date"),
        "currency": currency,
        "vendor": {"name": vendor_lines[0] if vendor_lines else "", "address": ", ".join(address) or None,
                   "tax_id": tax_id, "email": email},
        "bill_to": ", ".join(bill_to) or None,
        "line_items": items,
        "totals": {"subtotal": totals.get("subtotal"), "discount": totals.get("discount", "0"),
                   "tax": totals.get("tax", "0"), "tax_rate": totals.get("tax_rate"),
                   "total": totals.get("total")},
    }
    if raw["totals"]["subtotal"] is None and items:
        raw["totals"]["subtotal"] = str(sum_amounts(items))
    for key, patterns in (("invoice_date", (r"invoice date", r"date of issue", r"issue date", r"date")),
                          ("due_date", (r"due date", r"payment due", r"due"))):
        if is_ambiguous_date(_find_label(fields, *patterns)):
            uncertain.append(key)  # day/month order was inferred from the currency

    try:
        return Invoice.model_validate(raw), uncertain
    except ValidationError as exc:
        details = [{"field": ".".join(str(p) for p in e["loc"]), "problem": e["msg"]} for e in exc.errors()]
        looks_like_invoice = bool(items) or "total" in totals
        raise ExtractionFailed("Required invoice fields could not be extracted.", details,
                               not_invoice=not looks_like_invoice) from None


def is_ambiguous_date(raw: str | None) -> bool:
    """03/04/2026 could be 3 April or 4 March; 14/09/2026 can't."""
    m = re.fullmatch(r"\s*(\d{1,2})[/.-](\d{1,2})[/.-]\d{2,4}\s*", raw or "")
    return bool(m) and int(m[1]) <= 12 and int(m[2]) <= 12 and m[1] != m[2]


def sum_amounts(items: list[dict]):
    from app.schemas.money import parse_money

    return sum(parse_money(i["amount"]) for i in items)

"""Per-field confidence (0..1). A field is trusted less when:
- its value can't be found in the PDF text (a likely hallucination or misread),
- it is involved in a failed arithmetic check,
- the extractor itself reported it as a guess.
"""
import re
from datetime import date
from decimal import Decimal
from typing import Any

from app.schemas.api import Flag
from app.schemas.invoice import Invoice

NOT_FOUND = 0.45
FAILED_CHECK = 0.6
SELF_REPORTED = 0.7
CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£"}
# Fields whose absence from the text is normal (they default to 0 / null).
DEFAULTABLE = {"totals.discount", "totals.tax"}


def _norm(s: str) -> str:
    return re.sub(r"[^0-9a-z]", "", s.lower())


def _money_forms(d: Decimal) -> list[str]:
    us = f"{abs(d):,.2f}"
    eu = us.replace(",", "X").replace(".", ",").replace("X", ".")
    return [us, eu, f"{abs(d):.2f}", f"{abs(d):.2f}".replace(".", ",")]


def _date_forms(d: date) -> list[str]:
    return [d.isoformat(), d.strftime("%d.%m.%Y"), d.strftime("%d/%m/%Y"), d.strftime("%m/%d/%Y"),
            d.strftime("%d-%m-%Y"), f"{d.day} {d.strftime('%B %Y')}", f"{d.strftime('%B')} {d.day}, {d.year}",
            f"{d.day} {d.strftime('%b %Y')}", f"{d.strftime('%b')} {d.day}, {d.year}"]


def leaves(inv: Invoice) -> dict[str, Any]:
    out: dict[str, Any] = {}

    def walk(prefix: str, obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(f"{prefix}.{k}" if prefix else k, v)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(f"{prefix}[{i}]", v)
        else:
            out[prefix] = obj

    walk("", inv.model_dump(mode="python"))
    return out


def found_in_text(path: str, value: Any, text: str, norm_text: str) -> bool:
    if isinstance(value, Decimal):
        if path.endswith("quantity") or path.endswith("tax_rate"):
            return re.search(rf"(?<![\d.,]){re.escape(f'{value.normalize():f}')}(?![\d])", text) is not None
        return any(f in text for f in _money_forms(value))
    if isinstance(value, date):
        return any(f in text for f in _date_forms(value))
    if path == "currency":
        return value in text or CURRENCY_SYMBOLS.get(value, "\0") in text
    n = _norm(str(value))
    return bool(n) and n in norm_text


def score(inv: Invoice, text: str, flags: list[Flag], uncertain: list[str]) -> tuple[dict[str, float], list[Flag]]:
    """Returns (confidence per field, extra 'not found' flags)."""
    norm_text = _norm(text)
    failed = {f.field for f in flags}
    # a total mismatch implicates every term of the sum
    if "totals.total" in failed:
        failed |= {"totals.subtotal"} | {f"totals.{k}" for k in ("tax", "discount") if getattr(inv.totals, k)}
    uncertain_set = set(uncertain)
    conf: dict[str, float] = {}
    extra: list[Flag] = []
    for path, value in leaves(inv).items():
        if value is None:
            continue
        c = 1.0
        if not found_in_text(path, value, text, norm_text):
            if path in DEFAULTABLE and value == 0:
                c *= 0.9
            else:
                c *= NOT_FOUND
                extra.append(Flag(field=path, code="not_found_in_text", severity="warning",
                                  message=f"The value {value} does not appear in the document text."))
        if path in failed:
            c *= FAILED_CHECK
        if path in uncertain_set:
            c *= SELF_REPORTED
        conf[path] = round(c, 2)
    return conf, extra

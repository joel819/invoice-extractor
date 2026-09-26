"""Parse money and dates the way they appear on real invoices."""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

_MONEY_JUNK = re.compile(r"[^\d,.\-()]")

DATE_FORMATS_DMY = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d %B %Y", "%d %b %Y",
                    "%B %d, %Y", "%b %d, %Y", "%B %d %Y")
DATE_FORMATS_MDY = ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y", "%B %d %Y",
                    "%d %B %Y", "%d %b %Y", "%d.%m.%Y")


def parse_money(value: object) -> Decimal:
    """'1,234.50', '1.234,50', '€ 99', '(12.00)', 1234.5 -> Decimal. Raises ValueError."""
    if isinstance(value, bool):
        raise ValueError("not a number")
    if isinstance(value, int | float | Decimal):
        return Decimal(str(value))
    s = _MONEY_JUNK.sub("", str(value).strip())
    negative = s.startswith("(") and s.endswith(")") or s.startswith("-")
    s = s.strip("()-")
    if not s or not any(c.isdigit() for c in s):
        raise ValueError(f"not a money amount: {value!r}")
    if "," in s and "." in s:
        # the right-most separator is the decimal point
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = f"{head.replace(',', '')}.{tail}" if len(tail) in (1, 2) else s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")  # 1.234.567 (EU thousands, no decimals)
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"not a money amount: {value!r}") from None
    return -d if negative else d


def parse_date(value: object, prefer_mdy: bool = False) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", str(value).strip())
    for fmt in DATE_FORMATS_MDY if prefer_mdy else DATE_FORMATS_DMY:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date: {value!r}")

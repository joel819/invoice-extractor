"""Generate the 5 sample invoices in sample_invoices/ (committed, so you only need this
to regenerate them). All companies, people and numbers are fictional.

Usage: python -m scripts.make_sample_invoices
"""
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from reportlab.lib.pagesizes import A4, LETTER
from reportlab.pdfgen.canvas import Canvas

OUT = Path(__file__).resolve().parent.parent / "sample_invoices"
CENT = Decimal("0.01")


def r2(d: Decimal) -> Decimal:
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(d: Decimal, eu: bool = False) -> str:
    s = f"{r2(d):,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") if eu else s


@dataclass
class Spec:
    filename: str
    vendor: list[str]  # name first, then address/tax/email lines
    meta: list[tuple[str, str]]  # (label, value)
    bill_to: list[str]
    items: list[tuple[str, str, str]]  # (description, qty, unit price)
    currency: str
    tax_label: str
    tax_rate: Decimal
    discount_rate: Decimal = Decimal("0")
    eu_numbers: bool = False
    total_label: str = "Total"
    total_error: Decimal = Decimal("0")  # added to the printed total to simulate a wrong invoice
    pagesize: tuple = A4
    footer: list[str] = field(default_factory=list)
    rows_per_page: int = 22


def render(spec: Spec) -> dict:
    """Draw the invoice and return the true values (used by tests as the answer key)."""
    eu = spec.eu_numbers
    lines = []
    for desc, qty, price in spec.items:
        q, p = Decimal(qty), Decimal(price)
        lines.append((desc, q, p, r2(q * p)))
    subtotal = sum((a for *_, a in lines), Decimal("0"))
    discount = r2(subtotal * spec.discount_rate / 100)
    tax = r2((subtotal - discount) * spec.tax_rate / 100)
    total = subtotal - discount + tax
    printed_total = total + spec.total_error

    w, h = spec.pagesize
    c = Canvas(str(OUT / spec.filename), pagesize=spec.pagesize)
    c.setTitle(f"Invoice {spec.meta[0][1]}")
    left, right = 50, w - 50
    cols = [left, right - 250, right - 160, right]  # description, qty, unit, amount (right-aligned)

    def header(y: float) -> float:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(cols[0], y, "Description")
        c.drawRightString(cols[1] + 20, y, "Qty")
        c.drawRightString(cols[2] + 40, y, "Unit Price")
        c.drawRightString(cols[3], y, "Amount")
        c.line(left, y - 5, right, y - 5)
        return y - 20

    y = h - 60
    c.setFont("Helvetica-Bold", 16)
    c.drawString(left, y, spec.vendor[0])
    c.setFont("Helvetica", 10)
    for ln in spec.vendor[1:]:
        y -= 14
        c.drawString(left, y, ln)
    y -= 34
    c.setFont("Helvetica-Bold", 20)
    c.drawString(left, y, "INVOICE")
    c.setFont("Helvetica", 10)
    for label, value in spec.meta:
        y -= 15
        c.drawString(left, y, f"{label}: {value}")
    y -= 28
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, "Bill To:")
    c.setFont("Helvetica", 10)
    for ln in spec.bill_to:
        y -= 14
        c.drawString(left, y, ln)
    y = header(y - 30)

    c.setFont("Helvetica", 10)
    page_rows = 0
    for desc, q, p, a in lines:
        if page_rows == spec.rows_per_page:
            c.setFont("Helvetica-Oblique", 9)
            c.drawString(left, 40, "Continued on next page")
            c.showPage()
            y = header(h - 60)
            c.setFont("Helvetica", 10)
            page_rows = 0
        c.drawString(cols[0], y, desc)
        c.drawRightString(cols[1] + 20, y, f"{q.normalize():f}")
        c.drawRightString(cols[2] + 40, y, fmt(p, eu))
        c.drawRightString(cols[3], y, fmt(a, eu))
        y -= 16
        page_rows += 1

    c.line(left, y + 8, right, y + 8)
    y -= 10
    rows = [("Subtotal", subtotal)]
    if discount:
        rows.append((f"Discount ({spec.discount_rate.normalize():f}%)", -discount))
    rows.append((f"{spec.tax_label} ({spec.tax_rate.normalize():f}%)", tax))
    for label, val in rows:
        c.drawRightString(cols[2] + 40, y, label)
        c.drawRightString(cols[3], y, ("-" if val < 0 else "") + fmt(abs(val), eu))
        y -= 16
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(cols[2] + 40, y, f"{spec.total_label} ({spec.currency})")
    c.drawRightString(cols[3], y, fmt(printed_total, eu))
    c.setFont("Helvetica", 9)
    y -= 40
    for ln in spec.footer:
        c.drawString(left, y, ln)
        y -= 12
    c.save()
    return {"subtotal": subtotal, "discount": discount, "tax": tax, "total": total, "printed_total": printed_total,
            "lines": len(lines)}


SPECS = [
    Spec(
        "01-clean-simple.pdf",
        ["Alder & Finch Design Studio", "Keizersgracht 112, 1015 CV Amsterdam, Netherlands",
         "VAT ID: NL859301762B01", "Email: hello@alderfinch.example"],
        [("Invoice No", "AF-2026-0142"), ("Invoice Date", "2026-09-03"), ("Due Date", "2026-10-03")],
        ["Kestrel Outdoor Supply B.V.", "Marktstraat 8, 3511 AB Utrecht, Netherlands"],
        [("Brand identity workshop (half day)", "1", "1200.00"),
         ("Logo design, three concepts", "1", "850.00"),
         ("Business card layout", "2", "75.00")],
        "EUR", "VAT", Decimal("21"),
        footer=["Payment by bank transfer within 30 days. IBAN NL00 FAKE 0123 4567 89."],
    ),
    Spec(
        "02-multi-line-tax.pdf",
        ["Northgate Buerobedarf GmbH", "Industriestrasse 45, 70565 Stuttgart, Germany",
         "USt-IdNr / VAT ID: DE284519637", "Email: rechnung@northgate.example"],
        [("Invoice No", "NG-448913"), ("Invoice Date", "14.09.2026"), ("Due Date", "28.09.2026")],
        ["Brightwater Analytics GmbH", "Koenigstrasse 20, 70173 Stuttgart, Germany"],
        [("A4 copy paper 80g, box of 5 reams", "12", "24.90"),
         ("Ballpoint pens blue, pack of 50", "4", "18.50"),
         ("Lever arch files, pack of 10", "6", "32.00"),
         ("Whiteboard markers assorted, set of 8", "5", "11.75"),
         ("Ergonomic office chair Model S3", "3", "289.00"),
         ("Height-adjustable desk 160x80", "2", "649.00"),
         ("Monitor arm, dual", "4", "89.90"),
         ("Desk lamp LED", "6", "39.95"),
         ("Sticky notes 76x76, pack of 12", "10", "7.40"),
         ("Laser toner cartridge black", "4", "112.00"),
         ("Paper shredder P-4", "1", "234.50"),
         ("Delivery and assembly", "1", "180.00")],
        "EUR", "VAT", Decimal("19"), discount_rate=Decimal("5"), eu_numbers=True,
        footer=["Zahlbar innerhalb von 14 Tagen. Payable within 14 days."],
    ),
    Spec(
        "03-two-pages.pdf",
        ["Harbour Lane Catering Ltd", "Unit 4, 17 Harbour Lane, London SE1 9PX, United Kingdom",
         "VAT Reg No: GB 417 2285 03", "Email: accounts@harbourlane.example"],
        [("Invoice No", "HLC-2026-0917"), ("Invoice Date", "17/09/2026"), ("Due Date", "17/10/2026")],
        ["Brightwater Analytics Ltd", "88 Wharf Road, London N1 7GR, United Kingdom"],
        [(d, str(n), p) for d, n, p in [
            ("Welcome drinks reception", 120, "6.50"), ("Canape selection, 6 pieces", 120, "9.75"),
            ("Seasonal soup", 120, "4.20"), ("Artisan bread basket", 30, "5.50"),
            ("Roast chicken main", 70, "16.80"), ("Wild mushroom risotto main", 35, "14.90"),
            ("Vegan lentil wellington", 15, "15.40"), ("Seasonal vegetables", 120, "3.10"),
            ("Dessert trio", 120, "7.25"), ("Cheese board", 20, "18.00"),
            ("Coffee and tea service", 120, "2.80"), ("Soft drinks package", 120, "3.50"),
            ("House wine, bottle", 40, "19.50"), ("Sparkling water, bottle", 60, "2.90"),
            ("Late-night snack boxes", 80, "5.60"), ("Birthday cake, 3 tiers", 1, "185.00"),
            ("Waiting staff, per hour", 48, "18.50"), ("Bar staff, per hour", 16, "19.50"),
            ("Chef on site, per hour", 12, "32.00"), ("Kitchen porter, per hour", 12, "14.50"),
            ("Glassware hire", 240, "0.45"), ("Crockery and cutlery hire", 120, "1.90"),
            ("Linen tablecloths", 15, "8.50"), ("Napkins, linen", 120, "0.80"),
            ("Buffet table hire", 4, "22.00"), ("Chafing dishes hire", 8, "12.00"),
            ("Ice, 10kg bag", 6, "4.50"), ("Delivery and collection", 1, "95.00"),
            ("Waste removal", 1, "45.00"), ("Venue kitchen deep clean", 1, "120.00")]],
        "GBP", "VAT", Decimal("20"),
        footer=["Thank you for your business. Payment within 30 days to sort code 00-00-00."],
    ),
    Spec(
        "04-math-error.pdf",
        ["Brightline IT Services", "22 Fenian Street, Dublin 2, D02 X285, Ireland",
         "VAT No: IE 3928471LH", "Email: billing@brightline.example"],
        [("Invoice No", "BIS-00731"), ("Invoice Date", "2026-09-10"), ("Due Date", "2026-09-24")],
        ["Kestrel Outdoor Supply B.V.", "Marktstraat 8, 3511 AB Utrecht, Netherlands"],
        [("Managed IT support, September", "1", "650.00"),
         ("Laptop setup and imaging", "4", "45.00"),
         ("Microsoft 365 licences", "10", "12.50"),
         ("On-site visit, hours", "3", "85.00")],
        "EUR", "VAT", Decimal("23"), total_error=Decimal("40.00"),
        footer=["Late payments incur interest under the statutory late payment rules."],
    ),
    Spec(
        "05-us-format-usd.pdf",
        ["Cedar Ridge Consulting LLC", "1550 Wynkoop Street, Suite 300, Denver, CO 80202, USA",
         "EIN: 84-3920175", "Email: ar@cedarridge.example"],
        [("Invoice #", "CR-1187"), ("Date", "09/14/2026"), ("Payment Due", "10/14/2026")],
        ["Brightwater Analytics Inc.", "400 Market Street, San Francisco, CA 94111, USA"],
        [("Data strategy assessment", "1", "4500.00"),
         ("Stakeholder interviews, hours", "12", "175.00"),
         ("Dashboard prototype", "1", "2250.00"),
         ("Travel expenses (at cost)", "1", "486.40")],
        "USD", "Sales Tax", Decimal("8.25"), total_label="Amount Due", pagesize=LETTER,
        footer=["Please make checks payable to Cedar Ridge Consulting LLC. Net 30."],
    ),
]


def build() -> dict[str, dict]:
    OUT.mkdir(exist_ok=True)
    return {s.filename: render(s) for s in SPECS}


if __name__ == "__main__":
    for name, truth in build().items():
        print(f"{name:<26} lines={truth['lines']:<3} total={truth['printed_total']}")

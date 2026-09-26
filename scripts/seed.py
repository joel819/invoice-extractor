"""Run the 5 sample invoices through the pipeline so the history isn't empty on first start.
Skips any sample that was already extracted (by file hash).

Usage: python -m scripts.seed
"""
import hashlib
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.models import Extraction
from app.pipeline import process

SAMPLES = Path(__file__).resolve().parent.parent / "sample_invoices"


def seed(verbose: bool = True) -> int:
    init_db()
    done = 0
    with SessionLocal() as db:
        for pdf in sorted(SAMPLES.glob("*.pdf")):
            data = pdf.read_bytes()
            if db.scalar(select(Extraction.id).where(Extraction.sha256 == hashlib.sha256(data).hexdigest())):
                continue
            r = process(db, pdf.name, data)
            done += 1
            if verbose:
                print(f"  {pdf.name:<26} {r.status:<13} {r.invoice.totals.total} {r.invoice.currency}  "
                      f"flags={len(r.flags)}")
    if verbose:
        print(f"Extracted {done} sample invoice(s).")
    return done


if __name__ == "__main__":
    seed()

"""Tests run fully offline (no API key). Env is set before the app is imported and overrides any .env."""
import os
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="invoice-tests-")
os.environ.update(DATA_DIR=_tmp, DATABASE_URL="", SEED_ON_STARTUP="false", GROQ_API_KEY="")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine, init_db  # noqa: E402
from main import app  # noqa: E402

SAMPLES = Path(__file__).resolve().parent.parent / "sample_invoices"


def sample(name: str) -> bytes:
    return (SAMPLES / name).read_bytes()


@pytest.fixture(autouse=True)
def _fresh_db():
    init_db()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def post(client):
    def _post(data: bytes, name: str = "invoice.pdf", ctype: str = "application/pdf"):
        return client.post("/extract", files={"file": (name, data, ctype)})

    return _post


def make_pdf(lines: list[str]) -> bytes:
    """A small text PDF built on the fly (reportlab)."""
    from io import BytesIO

    from reportlab.pdfgen.canvas import Canvas

    buf = BytesIO()
    c = Canvas(buf)
    y = 800
    for ln in lines:
        c.drawString(50, y, ln)
        y -= 16
    c.save()
    return buf.getvalue()

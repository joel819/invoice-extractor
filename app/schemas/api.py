from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.invoice import Invoice


class Flag(BaseModel):
    field: str  # dotted path, e.g. "totals.total" or "line_items[2].amount"
    code: str  # machine-readable, e.g. "total_mismatch"
    severity: Literal["warning", "error"]
    message: str


class ExtractionOut(BaseModel):
    id: int | None = None
    filename: str
    status: Literal["ok", "needs_review"]
    mode: Literal["groq", "demo", "fallback"]
    pages: int
    processing_ms: int
    invoice: Invoice
    confidence: dict[str, float]  # every leaf field -> 0..1
    low_confidence_fields: list[str]
    flags: list[Flag]
    created_at: datetime | None = None


class ErrorOut(BaseModel):
    error: str  # machine-readable code
    message: str  # human-readable explanation
    details: list[dict] = []


class ExtractionSummary(BaseModel):
    id: int
    created_at: datetime
    filename: str
    status: str
    mode: str
    vendor: str
    invoice_number: str
    total: str
    currency: str
    flags: int

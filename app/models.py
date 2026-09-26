from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Extraction(Base):
    __tablename__ = "extractions"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16))  # ok | needs_review
    mode: Mapped[str] = mapped_column(String(10))  # groq | demo | fallback
    pages: Mapped[int] = mapped_column(Integer)
    processing_ms: Mapped[int] = mapped_column(Integer)
    result_json: Mapped[str] = mapped_column(Text)  # the full ExtractionOut body

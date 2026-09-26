import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Extraction
from app.schemas.api import ExtractionOut, ExtractionSummary

router = APIRouter(prefix="/extractions", tags=["history"])


@router.get("", response_model=list[ExtractionSummary])
def list_extractions(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.scalars(select(Extraction).order_by(Extraction.id.desc()).limit(limit)).all()
    out = []
    for r in rows:
        body = json.loads(r.result_json)
        inv = body["invoice"]
        out.append(ExtractionSummary(
            id=r.id, created_at=r.created_at, filename=r.filename, status=r.status, mode=r.mode,
            vendor=inv["vendor"]["name"], invoice_number=inv["invoice_number"],
            total=inv["totals"]["total"], currency=inv["currency"], flags=len(body["flags"]),
        ))
    return out


@router.get("/{extraction_id}", response_model=ExtractionOut)
def get_extraction(extraction_id: int, db: Session = Depends(get_db)):
    row = db.get(Extraction, extraction_id)
    if row is None:
        raise HTTPException(404, "Extraction not found")
    return ExtractionOut.model_validate_json(row.result_json)

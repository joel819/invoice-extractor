from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.pipeline import process
from app.schemas.api import ErrorOut, ExtractionOut

router = APIRouter(tags=["extract"])

ERRORS = {code: {"model": ErrorOut} for code in (400, 413, 415, 422)}


@router.post("/extract", response_model=ExtractionOut, responses=ERRORS)
async def extract(file: UploadFile = File(..., description="A PDF invoice"),
                  db: Session = Depends(get_db)) -> ExtractionOut:
    """Upload a PDF invoice and get validated JSON back, with per-field confidence and flags.

    `status` is `needs_review` when any field is low-confidence or an arithmetic check fails."""
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)  # one byte past the limit is enough to detect an oversize file
    name = (file.filename or "upload.pdf").replace("\\", "/").rsplit("/", 1)[-1][:255]
    # PDF parsing and the LLM call are blocking; keep them off the event loop
    return await run_in_threadpool(process, db, name, data)

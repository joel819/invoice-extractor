from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/samples", tags=["demo"])
SAMPLES = Path(__file__).resolve().parents[2] / "sample_invoices"


@router.get("")
def list_samples() -> list[str]:
    """Demo helper: the bundled sample invoices."""
    return sorted(p.name for p in SAMPLES.glob("*.pdf"))


@router.get("/{name}")
def get_sample(name: str):
    path = SAMPLES / name
    if path.parent != SAMPLES or path.suffix != ".pdf" or not path.exists():
        raise HTTPException(404, "Sample not found")
    return FileResponse(path, media_type="application/pdf", filename=name, content_disposition_type="inline")

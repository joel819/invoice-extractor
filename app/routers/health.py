from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "demo_mode": s.demo_mode,
        "extractor": "rule-based (demo)" if s.demo_mode else s.groq_model,
        "max_upload_mb": s.max_upload_mb,
    }

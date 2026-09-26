import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.db import init_db
from app.errors import InvoiceError
from app.routers import extract, extractions, health, samples

log = logging.getLogger("uvicorn.error")
STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    init_db()
    if s.seed_on_startup:
        from scripts.seed import seed

        seed(verbose=False)
    if s.demo_mode:
        log.warning("DEMO MODE: no GROQ_API_KEY set. Using the rule-based extractor.")
    yield


def _error(status: int, error: str, message: str, details: list | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, "message": message, "details": details or []})


def create_app() -> FastAPI:
    app = FastAPI(
        title=get_settings().app_name,
        version="0.1.0",
        description="POST a PDF invoice, get validated JSON back: vendor, dates, line items, totals, "
                    "with per-field confidence and arithmetic checks.",
        lifespan=lifespan,
    )
    for r in (health.router, extract.router, extractions.router, samples.router):
        app.include_router(r)

    @app.exception_handler(InvoiceError)
    async def invoice_error(request: Request, exc: InvoiceError):
        return _error(exc.status_code, exc.error, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def request_error(request: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"]), "problem": e["msg"]} for e in exc.errors()]
        missing_file = any(d["field"] == "body.file" for d in details)
        msg = ("Send the PDF as multipart/form-data in a field named 'file'." if missing_file
               else "The request is invalid.")
        return _error(400 if missing_file else 422, "invalid_request", msg, details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return _error(exc.status_code, "http_error", str(exc.detail))

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    return app

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import router
from .config import get_settings
from .core.catalog import seed_catalog
from .db import SessionLocal, init_db

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with SessionLocal() as session:
        count = await seed_catalog(session)
    logging.getLogger("startup").info("node catalog seeded: %d types", count)
    yield


app = FastAPI(title="AI Workflow Copilot — Backend", version="1.0.0",
              lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def error_envelope(request: Request, exc: HTTPException):
    """Contract error model: { error: { code, message, recoverable } }"""
    detail = exc.detail if isinstance(exc.detail, dict) else {
        "code": "http_error", "message": str(exc.detail), "recoverable": False}
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


app.include_router(router)

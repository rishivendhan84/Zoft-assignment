import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.routes import router
from .config import get_settings
from .core.catalog import seed_catalog
from .core.events import get_bus
from .db import SessionLocal, init_db
from .models import Run

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with SessionLocal() as session:
        count = await seed_catalog(session)
        # settle runs orphaned by a restart: their tasks are gone, so no
        # 'done' would ever arrive — mark them failed and tell subscribers
        orphan_ids = (await session.execute(
            select(Run.id).where(Run.status == "running"))).scalars().all()
        if orphan_ids:
            await session.execute(
                update(Run).where(Run.id.in_(orphan_ids))
                .values(status="failed", error="interrupted by a server restart"))
            await session.commit()
    bus = get_bus()
    for run_id in orphan_ids:
        await bus.publish(run_id, "error", {
            "code": "run_interrupted", "recoverable": True,
            "message": "The server restarted mid-run. Nothing was saved — "
                       "you can retry the same message."})
        await bus.publish(run_id, "done", {"run_id": run_id, "status": "failed"})
    log = logging.getLogger("startup")
    log.info("node catalog seeded: %d types", count)
    if orphan_ids:
        log.info("settled %d orphaned runs", len(orphan_ids))
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


@app.exception_handler(StarletteHTTPException)
async def error_envelope(request: Request, exc: StarletteHTTPException):
    """Contract error model: { error: { code, message, recoverable } } —
    registered on the Starlette base class so framework-raised 404/405s
    are wrapped too, not just our own raises."""
    detail = exc.detail if isinstance(exc.detail, dict) else {
        "code": "http_error", "message": str(exc.detail), "recoverable": False}
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.exception_handler(RequestValidationError)
async def validation_envelope(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(p) for p in first.get("loc", []))
    return JSONResponse(status_code=422, content={"error": {
        "code": "validation_error",
        "message": f"{where}: {first.get('msg', 'invalid request')}",
        "recoverable": False}})


app.include_router(router)

import os
import pathlib

# default to a throwaway SQLite file; export DATABASE_URL to run the same
# suite against Postgres (e.g. postgresql+asyncpg://copilot:copilot@localhost/copilot)
TEST_DB = pathlib.Path(__file__).parent / "test_copilot.db"
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{TEST_DB}")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db import Base, engine
from app.main import app


@pytest_asyncio.fixture
async def client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    await engine.dispose()
    if TEST_DB.exists():
        TEST_DB.unlink()

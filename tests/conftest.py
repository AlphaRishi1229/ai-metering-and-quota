import os

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/metering_test"
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)

import asyncio
import asyncpg
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.main import app
from app.database import get_db, Base


async def _create_test_db():
    # ponytail: asyncpg direct connect to admin DB; sqlalchemy can't CREATE DATABASE
    conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/postgres")
    try:
        await conn.execute("CREATE DATABASE metering_test")
    except asyncpg.exceptions.DuplicateDatabaseError:
        pass
    finally:
        await conn.close()


# Run once at collection time — sync so it doesn't tie to any pytest event loop
asyncio.run(_create_test_db())


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(test_engine):
    # Separate session for test assertions — not shared with the client
    AsyncTestSession = async_sessionmaker(test_engine, expire_on_commit=False)
    async with AsyncTestSession() as session:
        yield session


@pytest_asyncio.fixture
async def client(test_engine):
    # Each HTTP request gets a fresh session (matches production get_db behaviour)
    AsyncTestSession = async_sessionmaker(test_engine, expire_on_commit=False)

    async def override_get_db():
        async with AsyncTestSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.config import settings
from app.database import engine, Base
from app.routers import users, generate, inspection

logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Create all DB tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    provider_name = "claude" if settings.USE_REAL_LLM else "mock"
    logger.info("AI Metering Service started | provider=%s log_level=%s", provider_name, settings.LOG_LEVEL.upper())
    yield
    logger.info("AI Metering Service shutting down")


app = FastAPI(title="AI Metering Service", lifespan=lifespan)
app.include_router(users.router)
app.include_router(generate.router)
app.include_router(inspection.router)

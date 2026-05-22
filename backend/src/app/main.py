from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Any

import redis.asyncio as aioredis
import structlog
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.routers.channels import router as channels_router
from app.routers.messages import router as messages_router
from app.routers.users import router as users_router
from app.routers.ws import router as ws_router

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logger.info("starting up", environment=settings.ENVIRONMENT)

    yield

    logger.info("shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="chat-engine API",
        version="0.1.0",
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(channels_router, prefix="/api")
    app.include_router(messages_router, prefix="/api")
    app.include_router(users_router, prefix="/api")
    app.include_router(ws_router)  # no prefix — path is /ws/{channel_id}

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["health"])
    async def ready(
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> Any:
        details: dict[str, str] = {}

        try:
            await session.execute(text("SELECT 1"))
        except Exception as exc:
            details["db"] = str(exc)

        try:
            redis_client = aioredis.from_url(settings.REDIS_URL)
            await redis_client.ping()
            await redis_client.aclose()
        except Exception as exc:
            details["redis"] = str(exc)

        if details:
            return JSONResponse(
                status_code=503,
                content={"status": "degraded", "details": details},
            )
        return {"status": "ok"}

    return app


app = create_app()

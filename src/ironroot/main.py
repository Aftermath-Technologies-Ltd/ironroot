# Author: Bradley R. Kinnard
"""fastapi application entrypoint."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Load .env BEFORE importing settings or any module that reads env vars.
# `pydantic-settings` also reads `.env` but pre-loading here keeps LLM
# adapters and other env-driven dependencies seeing the same values.
load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from ironroot.api.router import api_router  # noqa: E402
from ironroot.logging.configure import get_logger  # noqa: E402
from ironroot.settings import get_settings  # noqa: E402

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """startup and shutdown events."""
    logger.info("ironroot starting", version="0.1.0")
    yield
    logger.info("ironroot shutting down")


def create_app() -> FastAPI:
    """factory that builds the fastapi app with all middleware and routes."""
    app = FastAPI(
        title="IRONROOT",
        description="Irreversible Research Ecology for Robust Agent Evolution",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # CORS: explicit localhost set in debug, settings-driven allowlist in
    # production. Never `["*"]` together with allow_credentials=True — that
    # combination is rejected by the browser fetch spec.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()


def main() -> None:
    """cli entrypoint for running uvicorn."""
    import uvicorn

    uvicorn.run(
        "ironroot.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()

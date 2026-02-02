# Author: Bradley R. Kinnard
"""fastapi application entrypoint."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env before anything else (for LLM config vars)
load_dotenv()

from ironroot.api.router import api_router
from ironroot.logging.configure import get_logger
from ironroot.settings import get_settings

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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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

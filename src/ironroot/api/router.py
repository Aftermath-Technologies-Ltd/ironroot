# Author: Bradley R. Kinnard
"""central api router that aggregates all route modules."""

from fastapi import APIRouter

from ironroot.api.routes import (
    agents,
    artifacts,
    beliefs,
    health,
    reality,
    runs,
    strategies,
    tests,
    ui,
)

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(runs.router, prefix="/runs", tags=["runs"])
api_router.include_router(artifacts.router, prefix="/artifacts", tags=["artifacts"])
api_router.include_router(beliefs.router, prefix="/beliefs", tags=["beliefs"])
api_router.include_router(strategies.router, prefix="/strategies", tags=["strategies"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(tests.router, prefix="/tests", tags=["tests"])
api_router.include_router(ui.router, prefix="/ui", tags=["ui"])
api_router.include_router(reality.router, prefix="/reality", tags=["reality"])

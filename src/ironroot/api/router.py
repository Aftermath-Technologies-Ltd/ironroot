# Author: Bradley R. Kinnard
"""Central api router that aggregates all route modules.

Phase 3.4: every router below ``/api/v1`` (except ``/health``) is
gated by :func:`ironroot.api.auth.require_method_scope`, which picks
``read`` for GET/HEAD/OPTIONS and ``write`` for POST/PUT/PATCH/DELETE.
The ``/tokens`` admin endpoints add their own ``admin``-scope
dependency on top.
"""

from fastapi import APIRouter, Depends

from ironroot.api.auth import require_method_scope
from ironroot.api.routes import (
    agents,
    agi,
    artifacts,
    beliefs,
    health,
    reality,
    research,
    runs,
    strategies,
    tests,
    tokens,
    ui,
)

api_router = APIRouter()

# `/health` is intentionally unauthenticated: load balancers and
# operators need to probe readiness without provisioning credentials.
# Every other router carries the method-scoped auth dependency.
api_router.include_router(health.router, tags=["health"])

_authed = [Depends(require_method_scope)]

api_router.include_router(runs.router, prefix="/runs", tags=["runs"], dependencies=_authed)
api_router.include_router(
    artifacts.router, prefix="/artifacts", tags=["artifacts"], dependencies=_authed
)
api_router.include_router(
    beliefs.router, prefix="/beliefs", tags=["beliefs"], dependencies=_authed
)
api_router.include_router(
    strategies.router, prefix="/strategies", tags=["strategies"], dependencies=_authed
)
api_router.include_router(agents.router, prefix="/agents", tags=["agents"], dependencies=_authed)
api_router.include_router(tests.router, prefix="/tests", tags=["tests"], dependencies=_authed)
# The UI router contains a WebSocket route. The standard HTTP
# `require_method_scope` dependency would try to inspect a
# ``Request`` that does not exist on WebSocket connections, so we
# do NOT attach it here. The WebSocket forwards advisory events
# only (no writes); for v1 the security model is "production
# deploys put the WebSocket behind the same reverse proxy that
# fronts the API and rely on the proxy's auth". A per-connection
# bearer-token handshake is a follow-up item tracked in
# upgrade-plan §3 follow-ups.
api_router.include_router(ui.router, prefix="/ui", tags=["ui"])
api_router.include_router(
    reality.router, prefix="/reality", tags=["reality"], dependencies=_authed
)
api_router.include_router(agi.router, tags=["agi"], dependencies=_authed)
api_router.include_router(
    research.router, prefix="/research", tags=["research"], dependencies=_authed
)
# Admin-only token management. The router below also declares
# `require_scope(SCOPE_ADMIN)` per-route, so even if a future change
# accidentally drops the wrapper here the admin check still fires.
api_router.include_router(tokens.router, prefix="/tokens", tags=["tokens"])

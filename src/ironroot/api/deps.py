# Author: Bradley R. Kinnard
"""fastapi dependency injection."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.domain.ids import generate_id
from ironroot.settings import Settings, get_settings
from ironroot.storage.postgres import get_session_factory


async def get_request_id(
    x_request_id: Annotated[str | None, Header()] = None,
) -> str:
    """extracts or generates a request id for tracing."""
    return x_request_id or generate_id("run")[:24]


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """provides async db session for request scope."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


SettingsDep = Annotated[Settings, Depends(get_settings)]
RequestIdDep = Annotated[str, Depends(get_request_id)]
DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]

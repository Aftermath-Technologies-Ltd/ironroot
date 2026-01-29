# Author: Bradley R. Kinnard
"""fastapi dependency injection."""

from typing import Annotated

from fastapi import Depends, Header

from ironroot.domain.ids import generate_id
from ironroot.settings import Settings, get_settings


async def get_request_id(
    x_request_id: Annotated[str | None, Header()] = None,
) -> str:
    """extracts or generates a request id for tracing."""
    return x_request_id or generate_id("run")[:24]


SettingsDep = Annotated[Settings, Depends(get_settings)]
RequestIdDep = Annotated[str, Depends(get_request_id)]

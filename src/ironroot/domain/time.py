# Author: Bradley R. Kinnard
"""time utilities with deterministic replay support."""

import time
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC

# global override for deterministic testing
_frozen_time: float | None = None


def now_ms() -> int:
    """current time in milliseconds, respects frozen time for replay."""
    if _frozen_time is not None:
        return int(_frozen_time * 1000)
    return int(time.time() * 1000)


def now_iso() -> str:
    """current time as iso8601 string."""
    from datetime import datetime

    if _frozen_time is not None:
        dt = datetime.fromtimestamp(_frozen_time, tz=UTC)
    else:
        dt = datetime.now(tz=UTC)
    return dt.isoformat()


@contextmanager
def frozen_time(timestamp: float) -> Generator[None, None, None]:
    """context manager for deterministic time in tests and replay."""
    global _frozen_time
    old = _frozen_time
    _frozen_time = timestamp
    try:
        yield
    finally:
        _frozen_time = old

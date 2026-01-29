# Author: Bradley R. Kinnard
"""structured logging setup with structlog."""

import logging
import sys
from functools import lru_cache

import structlog
from structlog.stdlib import BoundLogger


def get_logger(name: str) -> BoundLogger:
    """returns a configured structlog logger, avoids handler spam."""
    logger: BoundLogger = structlog.get_logger(name)
    return logger


@lru_cache(maxsize=1)
def configure_logging(log_level: str = "INFO", json_format: bool = False) -> None:
    """one-time logging config, sets up structlog processors."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    # clear existing handlers
    root = logging.getLogger()
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    if json_format:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    root.setLevel(level)
    root.addHandler(handler)

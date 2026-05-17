"""Structured logging helpers with conservative redaction defaults."""

from __future__ import annotations

import json
from typing import Any

from stackchan_bridge.redaction import redact_fields


def log_structured(
    logger: Any,
    level: int,
    event: str,
    **fields: Any,
) -> None:
    payload = {"event": event, **redact_fields(fields)}
    message = json.dumps(payload, sort_keys=True)
    if level >= 40 and hasattr(logger, "error"):
        logger.error(message)
    elif level >= 30 and hasattr(logger, "warning"):
        logger.warning(message)
    elif level >= 30 and hasattr(logger, "warn"):
        logger.warn(message)
    elif hasattr(logger, "info"):
        logger.info(message)
    elif hasattr(logger, "log"):
        logger.log(level, message)

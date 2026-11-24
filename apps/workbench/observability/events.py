"""Sanitized Workbench operational events."""

import json
import logging

_logger = logging.getLogger("workbench.api")


def log_event(event: str, **metadata: str | int | float) -> None:
    """Emit operational metadata only, without request paths or payloads."""
    _logger.info(json.dumps({"event": event, **metadata}, separators=(",", ":")))

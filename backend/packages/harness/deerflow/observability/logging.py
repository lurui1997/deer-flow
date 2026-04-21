"""Structured logging for DeerFlow observability.

Provides JSON-formatted structured logging with trace context injection.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from deerflow.observability.tracing import get_current_trace_context


class StructuredLogFormatter(logging.Formatter):
    """JSON structured log formatter with trace context injection."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "source": {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            },
        }

        # Add trace context
        trace_context = get_current_trace_context()
        if trace_context:
            log_data["trace"] = {
                "trace_id": trace_context.trace_id,
                "span_id": trace_context.span_id,
                "parent_span_id": trace_context.parent_span_id,
            }

        # Add extra fields if present
        extra_fields = {}
        for key in getattr(record, "__dict__", {}):
            if key not in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "message",
                "asctime",
            }:
                extra_fields[key] = getattr(record, key)

        if extra_fields:
            log_data["extra"] = extra_fields

        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, default=str, ensure_ascii=False)


def get_observability_logger(name: str) -> logging.Logger:
    """Get an observability logger with structured formatting.

    Args:
        name: Logger name, typically module path.

    Returns:
        Configured logger with structured JSON formatter.
    """
    logger = logging.getLogger(f"deerflow.observability.{name}")

    # Only add handler if not already configured
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredLogFormatter())
        logger.addHandler(handler)
        logger.propagate = False

    return logger

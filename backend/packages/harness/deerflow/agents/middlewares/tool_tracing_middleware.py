"""ToolTracingMiddleware - Full lifecycle tracing for tool calls.

Observability middleware that traces every tool call with:
- Unique trace IDs and span IDs
- Detailed timing (start, end, duration)
- Arguments and results (sanitized)
- Error tracking and status
"""

from __future__ import annotations

import logging
import time
from typing import Any, override

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from deerflow.agents.worker_state import WorkerState
from deerflow.observability.metrics import MetricsCollector
from deerflow.observability.pipeline import ObservabilityEvent, emit_event
from deerflow.observability.tracing import TracingMixin, generate_span_id, get_current_trace_context
from deerflow.observability.types import ObservabilityEventType, ToolCallSpan

logger = logging.getLogger(__name__)

# Maximum result size to log (truncate larger results)
_MAX_RESULT_SIZE = 10000


class ToolTracingMiddleware(AgentMiddleware[WorkerState], TracingMixin):
    """Full lifecycle tracing for tool calls.

    This middleware wraps every tool call to capture:
    - Call arguments and metadata
    - Execution timing
    - Results or errors
    - Performance metrics

    Traces are emitted as observability events and recorded in metrics.
    """

    state_schema = WorkerState

    def __init__(
        self,
        max_result_size: int = _MAX_RESULT_SIZE,
        emit_events: bool = True,
        record_metrics: bool = True,
    ):
        """Initialize ToolTracingMiddleware.

        Args:
            max_result_size: Maximum result size to include in traces.
            emit_events: Whether to emit observability events.
            record_metrics: Whether to record metrics.
        """
        super().__init__()
        self._max_result_size = max_result_size
        self._emit_events = emit_events
        self._record_metrics = record_metrics

    def _create_span(self, request: ToolCallRequest) -> ToolCallSpan:
        """Create a tool call span."""
        trace_ctx = get_current_trace_context()
        tool_call = request.tool_call

        return ToolCallSpan(
            span_id=generate_span_id(),
            trace_id=trace_ctx.trace_id if trace_ctx else generate_span_id(),
            parent_span_id=trace_ctx.span_id if trace_ctx else None,
            tool_name=str(tool_call.get("name", "unknown")),
            tool_call_id=str(tool_call.get("id", "unknown")),
            arguments=self._sanitize_arguments(tool_call.get("args", {})),
            start_time=time.time(),
            status="pending",
        )

    def _sanitize_arguments(self, args: Any) -> dict:
        """Sanitize tool arguments for logging.

        Removes potentially sensitive fields while preserving structure.
        """
        if not isinstance(args, dict):
            return {"raw": str(args)[:1000]}

        sanitized = {}
        sensitive_keys = {"password", "token", "secret", "api_key", "auth"}

        for key, value in args.items():
            if any(sk in key.lower() for sk in sensitive_keys):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, str) and len(value) > 5000:
                sanitized[key] = value[:5000] + f"... ({len(value)} chars)"
            else:
                sanitized[key] = value

        return sanitized

    def _sanitize_result(self, result: Any) -> Any:
        """Sanitize tool result for logging."""
        if result is None:
            return None

        if isinstance(result, ToolMessage):
            content = result.content
            if isinstance(content, str) and len(content) > self._max_result_size:
                return content[: self._max_result_size] + f"... ({len(content)} chars)"
            return content

        if isinstance(result, Command):
            return {"type": "command", "goto": getattr(result, "goto", None)}

        result_str = str(result)
        if len(result_str) > self._max_result_size:
            return result_str[: self._max_result_size] + f"... ({len(result_str)} chars)"

        return result

    def _emit_tool_start(self, span: ToolCallSpan) -> None:
        """Emit tool call started event."""
        if not self._emit_events:
            return

        event = ObservabilityEvent(
            event_type=ObservabilityEventType.TOOL_CALL_STARTED,
            timestamp=span.start_time,
            trace_id=span.trace_id,
            span_id=span.span_id,
            payload={
                "tool_name": span.tool_name,
                "tool_call_id": span.tool_call_id,
                "arguments": span.arguments,
            },
        )
        emit_event(event)

    def _emit_tool_end(self, span: ToolCallSpan) -> None:
        """Emit tool call completed/failed event."""
        if not self._emit_events:
            return

        event_type = (
            ObservabilityEventType.TOOL_CALL_COMPLETED
            if span.status == "success"
            else ObservabilityEventType.TOOL_CALL_FAILED
        )

        payload: dict[str, Any] = {
            "tool_name": span.tool_name,
            "tool_call_id": span.tool_call_id,
            "duration_ms": span.duration_ms,
            "status": span.status,
        }

        if span.status == "success":
            payload["result_preview"] = self._sanitize_result(span.result)
        else:
            payload["error_message"] = span.error_message
            payload["error_type"] = type(span.error_message).__name__ if span.error_message else None

        event = ObservabilityEvent(
            event_type=event_type,
            timestamp=span.end_time or time.time(),
            trace_id=span.trace_id,
            span_id=span.span_id,
            payload=payload,
        )
        emit_event(event)

    def _record_metrics(self, span: ToolCallSpan) -> None:
        """Record tool call metrics."""
        if not self._record_metrics:
            return

        duration_sec = (span.duration_ms or 0) / 1000.0
        MetricsCollector.record_tool_call(
            tool_name=span.tool_name,
            duration_sec=duration_sec,
            status=span.status,
        )

    @override
    def wrap_tool_call(self, request: ToolCallRequest, handler):
        """Wrap tool call with tracing."""
        span = self._create_span(request)
        self._emit_tool_start(span)

        try:
            result = handler(request)
            span.status = "success"
            span.result = result
        except Exception as exc:
            span.status = "error"
            span.error_message = str(exc)
            logger.exception(
                "Tool execution failed: name=%s id=%s",
                span.tool_name,
                span.tool_call_id,
            )
            raise
        finally:
            span.end_time = time.time()
            span.duration_ms = int((span.end_time - span.start_time) * 1000)
            self._emit_tool_end(span)
            self._record_metrics(span)

        return result

    @override
    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        """Async version of wrap_tool_call."""
        span = self._create_span(request)
        self._emit_tool_start(span)

        try:
            result = await handler(request)
            span.status = "success"
            span.result = result
        except Exception as exc:
            span.status = "error"
            span.error_message = str(exc)
            logger.exception(
                "Tool execution failed (async): name=%s id=%s",
                span.tool_name,
                span.tool_call_id,
            )
            raise
        finally:
            span.end_time = time.time()
            span.duration_ms = int((span.end_time - span.start_time) * 1000)
            self._emit_tool_end(span)
            self._record_metrics(span)

        return result

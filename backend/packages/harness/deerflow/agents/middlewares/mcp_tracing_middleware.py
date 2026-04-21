"""MCPTracingMiddleware - Traces MCP (Model Context Protocol) tool calls.

Observability middleware for MCP tool calls:
- Detects MCP tool calls by prefix patterns
- Tracks MCP server health
- Records call latency and errors
- Supports MCP-specific metrics
"""

from __future__ import annotations

import logging
import time
from typing import Any, override

from langchain.agents.middleware import AgentMiddleware
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from deerflow.agents.worker_state import WorkerState
from deerflow.observability.metrics import MetricsCollector
from deerflow.observability.pipeline import ObservabilityEvent, emit_event
from deerflow.observability.tracing import TracingMixin, generate_span_id, get_current_trace_context
from deerflow.observability.types import MCPCallSpan, ObservabilityEventType

logger = logging.getLogger(__name__)

# MCP tool prefixes for detection
_MCP_TOOL_PREFIXES = [
    "mcp_",
    "github_",
    "postgres_",
    "slack_",
    "notion_",
    "linear_",
    "jira_",
    "confluence_",
    "gitlab_",
    "sentry_",
]

# Server name extraction patterns
_SERVER_PATTERNS = {
    "github": ["github_"],
    "postgres": ["postgres_", "pg_", "sql_"],
    "slack": ["slack_"],
    "notion": ["notion_"],
    "linear": ["linear_"],
    "jira": ["jira_", "jira_"],
    "confluence": ["confluence_"],
    "gitlab": ["gitlab_"],
    "sentry": ["sentry_"],
    "generic": ["mcp_"],
}


class MCPTracingMiddleware(AgentMiddleware[WorkerState], TracingMixin):
    """Traces MCP (Model Context Protocol) tool calls.

    This middleware detects MCP tool calls by their naming patterns and
    traces their execution with MCP-specific metadata.
    """

    state_schema = WorkerState

    def __init__(
        self,
        tool_prefixes: list[str] | None = None,
        emit_events: bool = True,
        record_metrics: bool = True,
    ):
        """Initialize MCPTracingMiddleware.

        Args:
            tool_prefixes: List of tool name prefixes indicating MCP tools.
            emit_events: Whether to emit observability events.
            record_metrics: Whether to record metrics.
        """
        super().__init__()
        self._tool_prefixes = tool_prefixes or _MCP_TOOL_PREFIXES
        self._emit_events = emit_events
        self._record_metrics = record_metrics

    def _is_mcp_tool(self, tool_name: str) -> bool:
        """Check if a tool name indicates an MCP tool."""
        return any(tool_name.startswith(prefix) for prefix in self._tool_prefixes)

    def _extract_server_name(self, tool_name: str) -> str:
        """Extract MCP server name from tool name."""
        for server, prefixes in _SERVER_PATTERNS.items():
            for prefix in prefixes:
                if tool_name.startswith(prefix):
                    return server
        return "unknown"

    def _extract_tool_name(self, tool_name: str) -> str:
        """Extract the actual tool name without server prefix."""
        for prefix in self._tool_prefixes:
            if tool_name.startswith(prefix):
                return tool_name[len(prefix) :]
        return tool_name

    def _create_span(self, request: ToolCallRequest) -> MCPCallSpan:
        """Create an MCP call span."""
        trace_ctx = get_current_trace_context()
        tool_name = str(request.tool_call.get("name", "unknown"))

        return MCPCallSpan(
            span_id=generate_span_id(),
            trace_id=trace_ctx.trace_id if trace_ctx else generate_span_id(),
            mcp_server_name=self._extract_server_name(tool_name),
            mcp_tool_name=self._extract_tool_name(tool_name),
            start_time=time.time(),
            request_params=self._sanitize_params(request.tool_call.get("args", {})),
        )

    def _sanitize_params(self, params: Any) -> dict:
        """Sanitize MCP request parameters."""
        if not isinstance(params, dict):
            return {"raw": str(params)[:1000]}

        sanitized = {}
        sensitive_keys = {"password", "token", "secret", "api_key", "auth", "credentials"}

        for key, value in params.items():
            if any(sk in key.lower() for sk in sensitive_keys):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, str) and len(value) > 5000:
                sanitized[key] = value[:5000] + f"... ({len(value)} chars)"
            else:
                sanitized[key] = value

        return sanitized

    def _emit_mcp_event(self, span: MCPCallSpan, event_type: str) -> None:
        """Emit MCP observability event."""
        if not self._emit_events:
            return

        payload: dict[str, Any] = {
            "server_name": span.mcp_server_name,
            "tool_name": span.mcp_tool_name,
            "duration_ms": span.duration_ms,
            "status": span.status,
        }

        if span.status == "error":
            payload["error_type"] = span.error_type
            payload["error_message"] = span.error_message

        event = ObservabilityEvent(
            event_type=event_type,
            timestamp=span.end_time or time.time(),
            trace_id=span.trace_id,
            span_id=span.span_id,
            payload=payload,
        )
        emit_event(event)

    def _record_metrics(self, span: MCPCallSpan) -> None:
        """Record MCP metrics."""
        if not self._record_metrics:
            return

        MetricsCollector.record_mcp_call(
            server_name=span.mcp_server_name,
            tool_name=span.mcp_tool_name,
            status=span.status,
        )

    @override
    def wrap_tool_call(self, request: ToolCallRequest, handler):
        """Wrap MCP tool call with tracing."""
        tool_name = str(request.tool_call.get("name", ""))

        if not self._is_mcp_tool(tool_name):
            return handler(request)

        span = self._create_span(request)

        try:
            result = handler(request)
            span.status = "success"
            span.response = result
        except Exception as exc:
            span.status = "error"
            span.error_type = type(exc).__name__
            span.error_message = str(exc)
            logger.exception(
                "MCP call failed: server=%s tool=%s",
                span.mcp_server_name,
                span.mcp_tool_name,
            )
            raise
        finally:
            span.end_time = time.time()
            span.duration_ms = int((span.end_time - span.start_time) * 1000)

            event_type = (
                ObservabilityEventType.MCP_CALL_COMPLETED
                if span.status == "success"
                else ObservabilityEventType.MCP_CALL_FAILED
            )
            self._emit_mcp_event(span, event_type)
            self._record_metrics(span)

        return result

    @override
    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        """Async version of wrap_tool_call."""
        tool_name = str(request.tool_call.get("name", ""))

        if not self._is_mcp_tool(tool_name):
            return await handler(request)

        span = self._create_span(request)

        try:
            result = await handler(request)
            span.status = "success"
            span.response = result
        except Exception as exc:
            span.status = "error"
            span.error_type = type(exc).__name__
            span.error_message = str(exc)
            logger.exception(
                "MCP call failed (async): server=%s tool=%s",
                span.mcp_server_name,
                span.mcp_tool_name,
            )
            raise
        finally:
            span.end_time = time.time()
            span.duration_ms = int((span.end_time - span.start_time) * 1000)

            event_type = (
                ObservabilityEventType.MCP_CALL_COMPLETED
                if span.status == "success"
                else ObservabilityEventType.MCP_CALL_FAILED
            )
            self._emit_mcp_event(span, event_type)
            self._record_metrics(span)

        return result

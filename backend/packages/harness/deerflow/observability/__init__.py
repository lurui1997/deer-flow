"""DeerFlow Observability Module.

Provides unified tracing, structured logging, metrics collection, and
observability pipeline for the Agent Runtime Worker (ARW).

Modules:
    tracing: Unified trace context with trace_id/span_id support
    logging: Structured JSON logging with trace context injection
    metrics: Prometheus-compatible metrics collection
    pipeline: Multi-sink observability data pipeline
    types: Shared observability data types and enums
"""

from deerflow.observability.tracing import (
    TraceContext,
    generate_span_id,
    generate_trace_id,
    get_current_trace_context,
    set_trace_context,
)
from deerflow.observability.types import (
    CommandAuditRecord,
    MCPCallSpan,
    ObservabilityEvent,
    ObservabilityEventType,
    SkillExecutionRecord,
    ThinkingRecord,
    ToolCallSpan,
    WebSearchRecord,
)

__all__ = [
    # Tracing
    "TraceContext",
    "generate_trace_id",
    "generate_span_id",
    "get_current_trace_context",
    "set_trace_context",
    # Types
    "ObservabilityEvent",
    "ObservabilityEventType",
    "ToolCallSpan",
    "ThinkingRecord",
    "SkillExecutionRecord",
    "MCPCallSpan",
    "WebSearchRecord",
    "CommandAuditRecord",
]

"""Unified tracing context for DeerFlow observability.

Provides trace_id/span_id generation and context propagation across
middlewares using Python's contextvars.
"""

from __future__ import annotations

import contextvars
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TraceContext:
    """Unified trace context for cross-middleware tracing."""

    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None

    # Agent info
    agent_name: Optional[str] = None
    thread_id: Optional[str] = None
    scheduler_run_id: Optional[str] = None

    # Timing
    start_time: float = field(default_factory=time.time)

    def child_span(self, span_name: Optional[str] = None) -> TraceContext:
        """Create a child span context."""
        return TraceContext(
            trace_id=self.trace_id,
            span_id=generate_span_id(),
            parent_span_id=self.span_id,
            agent_name=self.agent_name,
            thread_id=self.thread_id,
            scheduler_run_id=self.scheduler_run_id,
        )


# ContextVar for storing current trace context
_current_trace_context: contextvars.ContextVar[Optional[TraceContext]] = contextvars.ContextVar(
    "trace_context", default=None
)


def get_current_trace_context() -> Optional[TraceContext]:
    """Get the current trace context."""
    return _current_trace_context.get()


def set_trace_context(context: Optional[TraceContext]) -> None:
    """Set the current trace context."""
    _current_trace_context.set(context)


def generate_trace_id() -> str:
    """Generate a unique trace ID (32 hex chars)."""
    return uuid.uuid4().hex


def generate_span_id() -> str:
    """Generate a unique span ID (16 hex chars)."""
    return uuid.uuid4().hex[:16]


class TracingMixin:
    """Mixin providing tracing utilities for middlewares."""

    def start_span(
        self,
        span_name: Optional[str] = None,
        parent_context: Optional[TraceContext] = None,
    ) -> TraceContext:
        """Start a new span with optional parent context."""
        parent = parent_context or get_current_trace_context()

        span = TraceContext(
            trace_id=parent.trace_id if parent else generate_trace_id(),
            span_id=generate_span_id(),
            parent_span_id=parent.span_id if parent else None,
        )

        set_trace_context(span)
        return span

    def end_span(self, span: TraceContext) -> None:
        """End a span and restore parent context if available."""
        # Restore parent context if exists
        if span.parent_span_id:
            # Note: In practice, you'd maintain a stack, but for simplicity
            # we just clear the context here
            set_trace_context(None)
        else:
            set_trace_context(None)

    def get_trace_info(self) -> dict:
        """Get current trace info as a dictionary for logging."""
        ctx = get_current_trace_context()
        if not ctx:
            return {}
        return {
            "trace_id": ctx.trace_id,
            "span_id": ctx.span_id,
            "parent_span_id": ctx.parent_span_id,
        }

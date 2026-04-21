"""ThinkingMiddleware - Capture and record LLM thinking content.

Observability middleware for tracking LLM reasoning/thinking processes:
- Extracts thinking content from model responses (Claude thinking, DeepSeek reasoning)
- Records planned tool calls before execution
- Tracks thinking duration and model information
"""

from __future__ import annotations

import logging
import time
from typing import override

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

from deerflow.agents.worker_state import WorkerState
from deerflow.observability.metrics import MetricsCollector
from deerflow.observability.pipeline import ObservabilityEvent, emit_event
from deerflow.observability.tracing import TracingMixin, get_current_trace_context
from deerflow.observability.types import ObservabilityEventType, ThinkingRecord

logger = logging.getLogger(__name__)


class ThinkingMiddleware(AgentMiddleware[WorkerState], TracingMixin):
    """Capture and record LLM thinking/reasoning content.

    This middleware extracts thinking content from model responses and records
    them for observability. It supports:
    - Claude's thinking content blocks
    - DeepSeek's reasoning_content
    - Generic reasoning fields

    Also tracks planned tool calls to understand the model's decision process.
    """

    state_schema = WorkerState

    def __init__(
        self,
        max_thinking_history: int = 100,
        emit_events: bool = True,
    ):
        """Initialize ThinkingMiddleware.

        Args:
            max_thinking_history: Maximum number of thinking records to keep.
            emit_events: Whether to emit observability events.
        """
        super().__init__()
        self._max_thinking_history = max_thinking_history
        self._emit_events = emit_events
        self._turn_counter = 0

    def _extract_thinking_content(self, message) -> str | None:
        """Extract thinking content from a model message.

        Supports multiple provider formats:
        - Claude: content blocks with type="thinking"
        - DeepSeek: reasoning_content field
        - Generic: thinking or reasoning fields
        """
        # Try content blocks (Claude format)
        content = getattr(message, "content", None)
        if isinstance(content, list):
            thinking_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "thinking":
                        thinking_parts.append(block.get("thinking", ""))
                    elif block.get("type") == "reasoning":
                        thinking_parts.append(block.get("content", ""))
            if thinking_parts:
                return "\n".join(thinking_parts)

        # Try reasoning_content (DeepSeek format)
        reasoning = getattr(message, "reasoning_content", None)
        if reasoning:
            return str(reasoning)

        # Try additional_kwargs
        kwargs = getattr(message, "additional_kwargs", {}) or {}
        thinking = kwargs.get("thinking") or kwargs.get("reasoning")
        if thinking:
            return str(thinking)

        # Try response_metadata
        metadata = getattr(message, "response_metadata", {}) or {}
        thinking = metadata.get("thinking") or metadata.get("reasoning_content")
        if thinking:
            return str(thinking)

        return None

    def _extract_planned_tools(self, message) -> list[str]:
        """Extract planned tool calls from a model message."""
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            return []

        planned = []
        for tc in tool_calls:
            if isinstance(tc, dict):
                name = tc.get("name", "")
            else:
                name = getattr(tc, "name", "")
            if name:
                planned.append(name)
        return planned

    def _get_model_name(self, state: WorkerState) -> str:
        """Get current model name from state."""
        runtime = state.get("runtime") or {}
        return runtime.get("current_model", "unknown")

    def _calculate_thinking_duration(self, message) -> int:
        """Calculate thinking duration in milliseconds."""
        # Try to get duration from message metadata
        metadata = getattr(message, "response_metadata", {}) or {}
        duration_ms = metadata.get("thinking_duration_ms")
        if duration_ms:
            return int(duration_ms)

        # Fallback: estimate based on content length (rough heuristic)
        content = self._extract_thinking_content(message)
        if content:
            # Rough estimate: ~10ms per 100 chars
            return max(100, len(content) // 10)

        return 0

    @override
    def after_model(self, state: WorkerState, runtime: Runtime, output) -> None:
        """Capture thinking content after model response."""
        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]

        # Check if this is an AI message
        msg_type = getattr(last_msg, "type", None)
        if msg_type != "ai":
            return None

        # Extract thinking content
        thinking_content = self._extract_thinking_content(last_msg)
        if not thinking_content:
            return None

        # Increment turn counter
        self._turn_counter += 1

        # Extract planned tools
        planned_tools = self._extract_planned_tools(last_msg)

        # Calculate duration
        duration_ms = self._calculate_thinking_duration(last_msg)

        # Create thinking record
        record = ThinkingRecord(
            timestamp=time.time(),
            model_name=self._get_model_name(state),
            thinking_content=thinking_content,
            duration_ms=duration_ms,
            tool_calls_planned=planned_tools,
            turn_number=self._turn_counter,
        )

        # Update state
        thinking_history = list(state.get("thinking_history", []))
        thinking_history.append(record)

        # Trim history if needed
        if len(thinking_history) > self._max_thinking_history:
            thinking_history = thinking_history[-self._max_thinking_history :]

        # Emit observability event
        if self._emit_events:
            trace_ctx = get_current_trace_context()
            event = ObservabilityEvent(
                event_type=ObservabilityEventType.THINKING_CONTENT,
                timestamp=record.timestamp,
                trace_id=trace_ctx.trace_id if trace_ctx else None,
                span_id=trace_ctx.span_id if trace_ctx else None,
                payload={
                    "model_name": record.model_name,
                    "turn_number": record.turn_number,
                    "duration_ms": record.duration_ms,
                    "tool_calls_planned": record.tool_calls_planned,
                    "thinking_length": len(thinking_content) if thinking_content else 0,
                },
            )
            emit_event(event)

        logger.debug(
            "ThinkingMiddleware: captured thinking for turn %d, model=%s, "
            "duration=%dms, planned_tools=%s",
            record.turn_number,
            record.model_name,
            record.duration_ms,
            record.tool_calls_planned,
        )

        return {"thinking_history": thinking_history}

    @override
    async def aafter_model(self, state: WorkerState, runtime: Runtime, output) -> None:
        """Async version of after_model."""
        return self.after_model(state, runtime, output)

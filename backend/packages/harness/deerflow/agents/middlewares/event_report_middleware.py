"""EventReportMiddleware - RocketMQ 事件上报与 WebSocket 展示流.

中间件 #9 in ARW middleware chain:
- RocketMQ 主通道事件上报 (agent_runtime_events, agent_hitl_requests)
- WebSocket 辅助通道实时推送
- 展示流可恢复性支持 (ringbuffer, last_event_id 重连补流)
- 事件类型对齐 LangGraph 流式协议
- 可观测性指标集成

双通道上报:
- 主通道 (RocketMQ): Worker 直发事件到 agent_runtime_events
- 辅助通道 (WebSocket): 通过 gateway 容器向 ARC 实时推送
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
from deerflow.observability.tracing import TracingMixin, get_current_trace_context, set_trace_context
from deerflow.observability.types import ObservabilityEventType

logger = logging.getLogger(__name__)


class EventReportMiddleware(AgentMiddleware[WorkerState], TracingMixin):
    """Report events via RocketMQ and WebSocket streaming with observability.

    This middleware handles dual-channel event reporting:
    1. RocketMQ: Primary channel for task completion/failure, HITL requests
    2. WebSocket: Secondary channel for real-time progress/heartbeat
    3. Observability: Metrics and structured events for monitoring

    Stream resumability:
    - Gateway maintains event ringbuffer per run
    - ARC WebSocket reconnect with last_event_id triggers replay
    - Heartbeat events distinguish "running but idle" vs "disconnected"

    Event types align with LangGraph streaming protocol:
    - metadata: Execution metadata
    - values: State values updates
    - messages-tuple: Message stream
    - heartbeat: Periodic keepalive
    """

    state_schema = WorkerState

    # Event types
    EVENT_TASK_STARTED = "task_started"
    EVENT_TASK_COMPLETED = "task_completed"
    EVENT_TASK_FAILED = "task_failed"
    EVENT_HITL_REQUESTED = "agent_hitl_requests"
    EVENT_HITL_RESOLVED = "agent_hitl_resolved"
    EVENT_HEARTBEAT = "heartbeat"
    EVENT_CHECKPOINT = "checkpoint"

    def __init__(
        self,
        rocketmq_producer=None,
        websocket_manager=None,
        enable_rocktmq: bool = True,
        enable_websocket: bool = True,
        heartbeat_interval: float = 30.0,
        ringbuffer_size: int = 1000,
    ):
        """Initialize EventReportMiddleware.

        Args:
            rocketmq_producer: RocketMQ producer instance.
            websocket_manager: WebSocket connection manager.
            enable_rocktmq: Whether to enable RocketMQ reporting.
            enable_websocket: Whether to enable WebSocket streaming.
            heartbeat_interval: Interval between heartbeat events in seconds.
            ringbuffer_size: Size of event ringbuffer for replay.
        """
        super().__init__()
        self._rocketmq_producer = rocketmq_producer
        self._websocket_manager = websocket_manager
        self._enable_rocktmq = enable_rocktmq
        self._enable_websocket = enable_websocket
        self._heartbeat_interval = heartbeat_interval
        self._ringbuffer_size = ringbuffer_size
        self._last_heartbeat = 0.0
        self._event_sequence = 0

    def _get_thread_id(self) -> str | None:
        """Get current thread ID from config."""
        try:
            from langgraph.config import get_config
            config = get_config()
            return config.get("configurable", {}).get("thread_id")
        except Exception:
            return None

    def _get_scheduler_run_id(self, state: WorkerState) -> str | None:
        """Get scheduler_run_id from task_context."""
        task_context = state.get("task_context") or {}
        return task_context.get("scheduler_run_id")

    def _emit_rocktmq_event(
        self, event_type: str, payload: dict, state: WorkerState
    ) -> None:
        """Emit event to RocketMQ.

        Args:
            event_type: Type of event.
            payload: Event payload.
            state: Current WorkerState.
        """
        if not self._enable_rocktmq or not self._rocketmq_producer:
            return

        scheduler_run_id = self._get_scheduler_run_id(state)

        message = {
            "event_type": event_type,
            "scheduler_run_id": scheduler_run_id,
            "thread_id": self._get_thread_id(),
            "timestamp": time.time(),
            "payload": payload,
        }

        try:
            # Use scheduler_run_id as Tag for precise routing
            # Topic: agent_runtime_events or agent_hitl_requests
            topic = (
                "agent_hitl_requests"
                if event_type in (self.EVENT_HITL_REQUESTED, self.EVENT_HITL_RESOLVED)
                else "agent_runtime_events"
            )

            # TODO: Implement actual RocketMQ send
            # self._rocketmq_producer.send(
            #     topic=topic,
            #     tag=scheduler_run_id,
            #     body=message,
            # )

            logger.debug(
                "EventReportMiddleware: RocketMQ event %s to topic %s",
                event_type,
                topic,
            )
        except Exception as e:
            logger.exception("Failed to emit RocketMQ event: %s", e)

    def _emit_websocket_event(
        self, event_type: str, payload: dict, state: WorkerState
    ) -> None:
        """Emit event to WebSocket stream.

        Args:
            event_type: Type of event.
            payload: Event payload.
            state: Current WorkerState.
        """
        if not self._enable_websocket or not self._websocket_manager:
            return

        thread_id = self._get_thread_id()
        self._event_sequence += 1

        message = {
            "event": event_type,
            "data": payload,
            "thread_id": thread_id,
            "sequence": self._event_sequence,
            "timestamp": time.time(),
        }

        try:
            # TODO: Implement actual WebSocket send
            # self._websocket_manager.send_to_thread(thread_id, message)

            logger.debug(
                "EventReportMiddleware: WebSocket event %s to thread %s",
                event_type,
                thread_id,
            )
        except Exception as e:
            logger.exception("Failed to emit WebSocket event: %s", e)

    def _maybe_emit_heartbeat(self, state: WorkerState) -> None:
        """Emit heartbeat if interval has passed."""
        now = time.time()
        if now - self._last_heartbeat < self._heartbeat_interval:
            return

        self._last_heartbeat = now

        runtime = state.get("runtime") or {}
        payload = {
            "token_count": runtime.get("token_count"),
            "checkpoint_count": runtime.get("checkpoint_count"),
            "current_model": runtime.get("current_model"),
        }

        self._emit_websocket_event(self.EVENT_HEARTBEAT, payload, state)

    @override
    def before_agent(self, state: WorkerState, runtime: Runtime) -> dict | None:
        """Report task start event."""
        task_context = state.get("task_context") or {}
        agent_name = task_context.get("agent_name", "unknown")

        # Initialize trace context
        trace_ctx = self.start_span()
        if task_context.get("scheduler_run_id"):
            trace_ctx.scheduler_run_id = task_context["scheduler_run_id"]
        trace_ctx.agent_name = agent_name
        set_trace_context(trace_ctx)

        payload = {
            "agent_name": agent_name,
            "task_description": task_context.get("task_description"),
            "is_plan_mode": task_context.get("is_plan_mode"),
            "subagent_enabled": task_context.get("subagent_enabled"),
            "trace_id": trace_ctx.trace_id,
        }

        self._emit_rocktmq_event(self.EVENT_TASK_STARTED, payload, state)
        self._emit_websocket_event(self.EVENT_TASK_STARTED, payload, state)

        # Emit observability event
        event = ObservabilityEvent(
            event_type=ObservabilityEventType.AGENT_STARTED,
            timestamp=time.time(),
            trace_id=trace_ctx.trace_id,
            span_id=trace_ctx.span_id,
            payload=payload,
        )
        emit_event(event)

        # Record metrics
        MetricsCollector.record_agent_run(agent_name=agent_name, status="started")
        MetricsCollector.set_active_threads(1)

        logger.info("EventReportMiddleware: Task started event emitted, trace_id=%s", trace_ctx.trace_id)
        return None

    @override
    def after_model(self, state: WorkerState, runtime: Runtime, output) -> None:
        """Report model output event."""
        self._maybe_emit_heartbeat(state)

        # TODO: Report model output for streaming display
        # This would emit messages-tuple events for the frontend

    @override
    def on_tool_result(
        self, state: WorkerState, runtime: Runtime, tool_name: str, result
    ) -> None:
        """Report tool execution result."""
        self._maybe_emit_heartbeat(state)

        # TODO: Report tool execution for streaming display

    @override
    def on_agent_end(self, state: WorkerState, runtime: Runtime, output) -> None:
        """Report task completion event."""
        runtime_stats = state.get("runtime") or {}
        task_context = state.get("task_context") or {}
        agent_name = task_context.get("agent_name", "unknown")

        duration = (
            time.time() - runtime_stats.get("start_time")
            if runtime_stats.get("start_time")
            else None
        )

        payload = {
            "status": "completed",
            "token_count": runtime_stats.get("token_count"),
            "checkpoint_count": runtime_stats.get("checkpoint_count"),
            "duration": duration,
        }

        self._emit_rocktmq_event(self.EVENT_TASK_COMPLETED, payload, state)
        self._emit_websocket_event(self.EVENT_TASK_COMPLETED, payload, state)

        # Emit observability event
        trace_ctx = get_current_trace_context()
        event = ObservabilityEvent(
            event_type=ObservabilityEventType.AGENT_COMPLETED,
            timestamp=time.time(),
            trace_id=trace_ctx.trace_id if trace_ctx else None,
            span_id=trace_ctx.span_id if trace_ctx else None,
            payload={
                "agent_name": agent_name,
                "status": "completed",
                "token_count": runtime_stats.get("token_count"),
                "checkpoint_count": runtime_stats.get("checkpoint_count"),
                "duration_sec": duration,
            },
        )
        emit_event(event)

        # Record metrics
        MetricsCollector.record_agent_run(agent_name=agent_name, status="completed")
        MetricsCollector.set_active_threads(0)

        logger.info("EventReportMiddleware: Task completed event emitted")

    @override
    def on_agent_error(
        self, state: WorkerState, runtime: Runtime, error: Exception
    ) -> None:
        """Report task failure event."""
        task_context = state.get("task_context") or {}
        agent_name = task_context.get("agent_name", "unknown")

        payload = {
            "status": "failed",
            "error": str(error),
            "error_type": type(error).__name__,
        }

        self._emit_rocktmq_event(self.EVENT_TASK_FAILED, payload, state)
        self._emit_websocket_event(self.EVENT_TASK_FAILED, payload, state)

        # Emit observability event
        trace_ctx = get_current_trace_context()
        event = ObservabilityEvent(
            event_type=ObservabilityEventType.AGENT_FAILED,
            timestamp=time.time(),
            trace_id=trace_ctx.trace_id if trace_ctx else None,
            span_id=trace_ctx.span_id if trace_ctx else None,
            payload={
                "agent_name": agent_name,
                "status": "failed",
                "error": str(error),
                "error_type": type(error).__name__,
            },
        )
        emit_event(event)

        # Record metrics
        MetricsCollector.record_agent_run(agent_name=agent_name, status="failed")
        MetricsCollector.set_active_threads(0)

        logger.error(
            "EventReportMiddleware: Task failed event emitted: %s", error
        )

    def emit_hitl_request(self, hitl_state: dict, state: WorkerState) -> None:
        """Emit HITL request event (called by HITLMiddleware).

        Args:
            hitl_state: The HITL state.
            state: Current WorkerState.
        """
        payload = {
            "hitl_type": hitl_state.get("hitl_type"),
            "clarification_type": hitl_state.get("clarification_type"),
            "question": hitl_state.get("question"),
            "context": hitl_state.get("context"),
            "options": hitl_state.get("options"),
            "tool_call_id": hitl_state.get("tool_call_id"),
        }

        self._emit_rocktmq_event(self.EVENT_HITL_REQUESTED, payload, state)
        self._emit_websocket_event(self.EVENT_HITL_REQUESTED, payload, state)

    def emit_hitl_resolved(
        self, hitl_state: dict, response: str, state: WorkerState
    ) -> None:
        """Emit HITL resolved event.

        Args:
            hitl_state: The HITL state that was resolved.
            response: The response.
            state: Current WorkerState.
        """
        payload = {
            "hitl_type": hitl_state.get("hitl_type"),
            "response": response,
        }

        self._emit_rocktmq_event(self.EVENT_HITL_RESOLVED, payload, state)
        self._emit_websocket_event(self.EVENT_HITL_RESOLVED, payload, state)

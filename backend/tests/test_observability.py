"""Tests for DeerFlow observability module.

Covers:
- Tracing context management
- Metrics collection
- Pipeline event emission
- Observability middlewares
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from deerflow.observability import (
    generate_span_id,
    generate_trace_id,
    get_current_trace_context,
    set_trace_context,
)
from deerflow.observability.metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsCollector,
)
from deerflow.observability.pipeline import (
    CallbackSink,
    LoggingSink,
    ObservabilityEvent,
    ObservabilityPipeline,
    PipelineConfig,
    emit_event,
    get_global_pipeline,
    set_global_pipeline,
)
from deerflow.observability.tracing import TraceContext, TracingMixin
from deerflow.observability.types import ObservabilityEventType


# -----------------------------------------------------------------------------
# Tracing Tests
# -----------------------------------------------------------------------------

class TestTracing:
    """Tests for tracing module."""

    def test_generate_trace_id(self):
        """Test trace ID generation."""
        trace_id = generate_trace_id()
        assert len(trace_id) == 32
        assert all(c in "0123456789abcdef" for c in trace_id)

    def test_generate_span_id(self):
        """Test span ID generation."""
        span_id = generate_span_id()
        assert len(span_id) == 16
        assert all(c in "0123456789abcdef" for c in span_id)

    def test_trace_context(self):
        """Test trace context creation and child spans."""
        ctx = TraceContext(trace_id="abc123", span_id="def456")
        assert ctx.trace_id == "abc123"
        assert ctx.span_id == "def456"
        assert ctx.parent_span_id is None

        child = ctx.child_span()
        assert child.trace_id == "abc123"
        assert child.span_id != "def456"
        assert child.parent_span_id == "def456"

    def test_trace_context_vars(self):
        """Test trace context variable storage."""
        ctx = TraceContext(trace_id="test123", span_id="span456")
        set_trace_context(ctx)

        retrieved = get_current_trace_context()
        assert retrieved is not None
        assert retrieved.trace_id == "test123"
        assert retrieved.span_id == "span456"

        # Clear context
        set_trace_context(None)
        assert get_current_trace_context() is None

    def test_tracing_mixin(self):
        """Test TracingMixin methods."""
        mixin = TracingMixin()

        # Start span without parent
        span = mixin.start_span()
        assert span.trace_id is not None
        assert span.span_id is not None
        assert span.parent_span_id is None

        # Get trace info
        info = mixin.get_trace_info()
        assert "trace_id" in info
        assert "span_id" in info

        mixin.end_span(span)


# -----------------------------------------------------------------------------
# Metrics Tests
# -----------------------------------------------------------------------------

class TestMetrics:
    """Tests for metrics module."""

    def test_counter(self):
        """Test counter metric."""
        counter = Counter("test_counter", "Test counter", ["label"])
        counter.inc(labels={"label": "a"})
        counter.inc(labels={"label": "a"}, amount=2)
        assert counter.get(labels={"label": "a"}) == 3

    def test_counter_multiple_labels(self):
        """Test counter with multiple label values."""
        counter = Counter("test_counter", "Test counter", ["status"])
        counter.inc(labels={"status": "success"})
        counter.inc(labels={"status": "error"})
        assert counter.get(labels={"status": "success"}) == 1
        assert counter.get(labels={"status": "error"}) == 1

    def test_histogram(self):
        """Test histogram metric."""
        hist = Histogram("test_hist", "Test histogram", ["method"])
        hist.observe(0.05, labels={"method": "GET"})
        hist.observe(0.1, labels={"method": "GET"})
        hist.observe(0.5, labels={"method": "POST"})

        assert hist.get_count(labels={"method": "GET"}) == 2
        assert abs(hist.get_sum(labels={"method": "GET"}) - 0.15) < 0.001
        assert hist.get_count(labels={"method": "POST"}) == 1

    def test_histogram_buckets(self):
        """Test histogram bucket counts."""
        hist = Histogram("test_hist", "Test histogram", buckets=[0.01, 0.1, 1.0])
        hist.observe(0.005)
        hist.observe(0.05)
        hist.observe(0.5)

        buckets = hist.get_bucket_counts()
        assert buckets[0.01] == 1
        assert buckets[0.1] == 2  # 0.005 and 0.05 both <= 0.1
        assert buckets[1.0] == 3  # All three <= 1.0

    def test_gauge(self):
        """Test gauge metric."""
        gauge = Gauge("test_gauge", "Test gauge")
        gauge.set(10.0)
        assert gauge.get() == 10.0
        gauge.inc(amount=5.0)
        assert gauge.get() == 15.0
        gauge.dec(amount=3.0)
        assert gauge.get() == 12.0

    def test_metrics_collector(self):
        """Test MetricsCollector convenience methods."""
        MetricsCollector.record_tool_call("bash", 0.5, "success")
        MetricsCollector.record_llm_usage("gpt-4", 100, 50)
        MetricsCollector.record_agent_run("test-agent", "completed")
        MetricsCollector.record_web_search("tavily", 1.0, "success", 5)
        MetricsCollector.record_mcp_call("github", "search", "success")
        MetricsCollector.record_command_execution("docker", 2.0)
        MetricsCollector.record_dangerous_command("rm_rf")
        MetricsCollector.record_checkpoint()
        MetricsCollector.record_hitl_request("clarification")

        metrics = MetricsCollector.get_all_metrics()
        assert "agent_runs" in metrics
        assert "tool_calls" in metrics
        assert "llm_token_usage" in metrics
        assert "checkpoints" in metrics
        assert "dangerous_commands" in metrics


# -----------------------------------------------------------------------------
# Pipeline Tests
# -----------------------------------------------------------------------------

class TestPipeline:
    """Tests for observability pipeline."""

    def test_pipeline_basic(self):
        """Test basic pipeline operation."""
        received_batches = []

        async def callback(data):
            received_batches.append(data)

        sink = CallbackSink(callback)
        pipeline = ObservabilityPipeline([sink], config=PipelineConfig(batch_size=2))

        # Emit events (no async needed for emit)
        event1 = ObservabilityEvent(
            event_type=ObservabilityEventType.TOOL_CALL_STARTED,
            timestamp=time.time(),
            payload={"tool": "bash"},
        )
        event2 = ObservabilityEvent(
            event_type=ObservabilityEventType.TOOL_CALL_COMPLETED,
            timestamp=time.time(),
            payload={"tool": "bash"},
        )

        pipeline.emit(event1)
        pipeline.emit(event2)

        # Manually flush
        import asyncio
        asyncio.run(pipeline._flush())

        assert len(received_batches) >= 1
        first_batch = received_batches[0]
        assert "events" in first_batch
        assert len(first_batch["events"]) == 2

    def test_pipeline_sampling(self):
        """Test pipeline sampling."""
        received_batches = []

        async def callback(data):
            received_batches.append(data)

        sink = CallbackSink(callback)
        pipeline = ObservabilityPipeline(
            [sink], config=PipelineConfig(batch_size=1, sample_rate=0.0)
        )

        event = ObservabilityEvent(
            event_type=ObservabilityEventType.TOOL_CALL_STARTED,
            timestamp=time.time(),
            payload={},
        )
        pipeline.emit(event)

        # Manually flush
        import asyncio
        asyncio.run(pipeline._flush())

        # With sample_rate=0, no events should be emitted
        assert len(received_batches) == 0

    def test_global_pipeline(self):
        """Test global pipeline getter/setter."""
        assert get_global_pipeline() is None

        pipeline = ObservabilityPipeline([])
        set_global_pipeline(pipeline)
        assert get_global_pipeline() is pipeline

    def test_emit_event_without_pipeline(self):
        """Test emit_event when no pipeline is set."""
        set_global_pipeline(None)
        event = ObservabilityEvent(
            event_type=ObservabilityEventType.TOOL_CALL_STARTED,
            timestamp=time.time(),
            payload={},
        )
        # Should not raise
        emit_event(event)


# -----------------------------------------------------------------------------
# Middleware Tests
# -----------------------------------------------------------------------------

class TestObservabilityMiddlewares:
    """Tests for observability middlewares."""

    def test_tool_tracing_middleware_creation(self):
        """Test ToolTracingMiddleware can be instantiated."""
        from deerflow.agents.middlewares.tool_tracing_middleware import (
            ToolTracingMiddleware,
        )

        mw = ToolTracingMiddleware()
        assert mw._emit_events is True
        assert mw._record_metrics is True

    def test_thinking_middleware_creation(self):
        """Test ThinkingMiddleware can be instantiated."""
        from deerflow.agents.middlewares.thinking_middleware import (
            ThinkingMiddleware,
        )

        mw = ThinkingMiddleware()
        assert mw._max_thinking_history == 100
        assert mw._emit_events is True

    def test_mcp_tracing_middleware_creation(self):
        """Test MCPTracingMiddleware can be instantiated."""
        from deerflow.agents.middlewares.mcp_tracing_middleware import (
            MCPTracingMiddleware,
        )

        mw = MCPTracingMiddleware()
        assert mw._emit_events is True
        assert mw._record_metrics is True

    def test_web_search_middleware_creation(self):
        """Test WebSearchMiddleware can be instantiated."""
        from deerflow.agents.middlewares.web_search_middleware import (
            WebSearchMiddleware,
        )

        mw = WebSearchMiddleware()
        assert mw._emit_events is True
        assert mw._record_metrics is True

    def test_mcp_tool_detection(self):
        """Test MCP tool detection."""
        from deerflow.agents.middlewares.mcp_tracing_middleware import (
            MCPTracingMiddleware,
        )

        mw = MCPTracingMiddleware()
        assert mw._is_mcp_tool("mcp_github_search") is True
        assert mw._is_mcp_tool("mcp_slack_post") is True
        assert mw._is_mcp_tool("bash") is False
        assert mw._is_mcp_tool("web_search") is False

    def test_web_search_detection(self):
        """Test web search tool detection."""
        from deerflow.agents.middlewares.web_search_middleware import (
            WebSearchMiddleware,
        )

        mw = WebSearchMiddleware()
        is_search, search_type = mw._is_search_tool("web_search")
        assert is_search is True
        assert search_type == "web_search"

        is_search, _ = mw._is_search_tool("bash")
        assert is_search is False

    def test_provider_detection(self):
        """Test search provider detection."""
        from deerflow.agents.middlewares.web_search_middleware import (
            WebSearchMiddleware,
        )

        mw = WebSearchMiddleware()
        assert mw._detect_provider("tavily_search", {}) == "tavily"
        assert mw._detect_provider("ddg_search", {}) == "ddg"
        assert mw._detect_provider("web_search", {"provider": "exa"}) == "exa"


# -----------------------------------------------------------------------------
# WorkerState Integration Tests
# -----------------------------------------------------------------------------

class TestWorkerStateObservability:
    """Tests for WorkerState observability fields."""

    def test_worker_state_has_observability_fields(self):
        """Test WorkerState has all observability fields."""
        from deerflow.agents.worker_state import WorkerState

        # Create a minimal WorkerState with observability fields
        state = WorkerState(
            messages=[],
            thinking_history=[],
            tool_call_spans=[],
            skill_execution_records=[],
            mcp_call_spans=[],
            web_search_records=[],
            command_audit_records=[],
        )

        # Check that observability fields exist and are accessible
        assert "thinking_history" in state
        assert "tool_call_spans" in state
        assert "skill_execution_records" in state
        assert "mcp_call_spans" in state
        assert "web_search_records" in state
        assert "command_audit_records" in state


# -----------------------------------------------------------------------------
# Integration Test
# -----------------------------------------------------------------------------

class TestObservabilityIntegration:
    """Integration tests for the full observability system."""

    def test_full_pipeline_with_metrics(self):
        """Test full observability pipeline with metrics collection."""
        # Set up pipeline
        received_data = []

        async def capture(data):
            received_data.append(data)

        pipeline = ObservabilityPipeline(
            [CallbackSink(capture)],
            config=PipelineConfig(batch_size=5, sample_rate=1.0),
        )
        set_global_pipeline(pipeline)

        # Record some metrics
        MetricsCollector.record_tool_call("bash", 0.5, "success")
        MetricsCollector.record_tool_call("web_search", 1.2, "success")
        MetricsCollector.record_agent_run("test", "completed")

        # Emit events (batch size is 5, so these won't flush yet)
        for i in range(5):
            event = ObservabilityEvent(
                event_type=ObservabilityEventType.TOOL_CALL_STARTED,
                timestamp=time.time(),
                payload={"tool": f"tool_{i}"},
            )
            emit_event(event)

        # Manually flush
        import asyncio
        asyncio.run(pipeline._flush())

        # Verify metrics (metrics are cumulative across tests, so check >= expected)
        metrics = MetricsCollector.get_all_metrics()
        assert metrics["tool_calls"][("bash", "success")] >= 1
        assert metrics["tool_calls"][("web_search", "success")] >= 1
        assert metrics["agent_runs"][("test", "completed")] >= 1

        # Clean up
        set_global_pipeline(None)

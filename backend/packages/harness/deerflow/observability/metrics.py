"""Metrics collection for DeerFlow observability.

Provides Prometheus-compatible metrics for agent runs, tool calls,
LLM usage, and system health.

Note: This module uses a lightweight metrics registry that works
without requiring prometheus_client as a hard dependency. If
prometheus_client is available, metrics can be exported in
Prometheus format.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricValue:
    """A single metric value with labels."""

    value: float
    timestamp: float = field(default_factory=time.time)


class Counter:
    """Simple counter metric (monotonically increasing)."""

    def __init__(self, name: str, description: str, label_names: list[str] | None = None):
        self.name = name
        self.description = description
        self.label_names = label_names or []
        self._values: dict[tuple[str, ...], float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, labels: dict[str, str] | None = None, amount: float = 1.0) -> None:
        """Increment counter by amount."""
        label_key = self._make_label_key(labels or {})
        with self._lock:
            self._values[label_key] += amount

    def get(self, labels: dict[str, str] | None = None) -> float:
        """Get current counter value."""
        label_key = self._make_label_key(labels or {})
        with self._lock:
            return self._values[label_key]

    def _make_label_key(self, labels: dict[str, str]) -> tuple[str, ...]:
        """Create a hashable key from labels."""
        return tuple(labels.get(k, "") for k in self.label_names)

    def collect(self) -> dict[tuple[str, ...], float]:
        """Collect all counter values."""
        with self._lock:
            return dict(self._values)


class Histogram:
    """Simple histogram metric for latency distributions."""

    DEFAULT_BUCKETS = [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]

    def __init__(
        self,
        name: str,
        description: str,
        label_names: list[str] | None = None,
        buckets: list[float] | None = None,
    ):
        self.name = name
        self.description = description
        self.label_names = label_names or []
        self.buckets = sorted(buckets or self.DEFAULT_BUCKETS)
        self._values: dict[tuple[str, ...], list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def observe(self, value: float, labels: dict[str, str] | None = None) -> None:
        """Observe a value."""
        label_key = self._make_label_key(labels or {})
        with self._lock:
            self._values[label_key].append(value)

    def get_count(self, labels: dict[str, str] | None = None) -> int:
        """Get total number of observations."""
        label_key = self._make_label_key(labels or {})
        with self._lock:
            return len(self._values[label_key])

    def get_sum(self, labels: dict[str, str] | None = None) -> float:
        """Get sum of all observations."""
        label_key = self._make_label_key(labels or {})
        with self._lock:
            return sum(self._values[label_key])

    def get_bucket_counts(self, labels: dict[str, str] | None = None) -> dict[float, int]:
        """Get observation counts per bucket (cumulative)."""
        label_key = self._make_label_key(labels or {})
        with self._lock:
            values = self._values[label_key]
            counts: dict[float, int] = {b: 0 for b in self.buckets}
            for v in values:
                for b in self.buckets:
                    if v <= b:
                        counts[b] += 1
            return counts

    def _make_label_key(self, labels: dict[str, str]) -> tuple[str, ...]:
        """Create a hashable key from labels."""
        return tuple(labels.get(k, "") for k in self.label_names)


class Gauge:
    """Simple gauge metric (can go up and down)."""

    def __init__(self, name: str, description: str, label_names: list[str] | None = None):
        self.name = name
        self.description = description
        self.label_names = label_names or []
        self._values: dict[tuple[str, ...], float] = defaultdict(float)
        self._lock = threading.Lock()

    def set(self, value: float, labels: dict[str, str] | None = None) -> None:
        """Set gauge to a specific value."""
        label_key = self._make_label_key(labels or {})
        with self._lock:
            self._values[label_key] = value

    def inc(self, labels: dict[str, str] | None = None, amount: float = 1.0) -> None:
        """Increment gauge by amount."""
        label_key = self._make_label_key(labels or {})
        with self._lock:
            self._values[label_key] += amount

    def dec(self, labels: dict[str, str] | None = None, amount: float = 1.0) -> None:
        """Decrement gauge by amount."""
        label_key = self._make_label_key(labels or {})
        with self._lock:
            self._values[label_key] -= amount

    def get(self, labels: dict[str, str] | None = None) -> float:
        """Get current gauge value."""
        label_key = self._make_label_key(labels or {})
        with self._lock:
            return self._values[label_key]

    def _make_label_key(self, labels: dict[str, str]) -> tuple[str, ...]:
        """Create a hashable key from labels."""
        return tuple(labels.get(k, "") for k in self.label_names)


# -----------------------------------------------------------------------------
# DeerFlow-specific metrics
# -----------------------------------------------------------------------------

# Agent runs
AGENT_RUNS_TOTAL = Counter(
    "deerflow_agent_runs_total",
    "Total number of agent runs",
    label_names=["agent_name", "status"],
)

# Tool calls
TOOL_CALLS_TOTAL = Counter(
    "deerflow_tool_calls_total",
    "Total number of tool calls",
    label_names=["tool_name", "status"],
)

TOOL_CALL_DURATION = Histogram(
    "deerflow_tool_call_duration_seconds",
    "Tool call duration in seconds",
    label_names=["tool_name"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0],
)

# LLM usage
LLM_TOKEN_USAGE = Counter(
    "deerflow_llm_token_usage_total",
    "Total LLM token usage",
    label_names=["model_name", "token_type"],
)

LLM_LATENCY = Histogram(
    "deerflow_llm_latency_seconds",
    "LLM call latency",
    label_names=["model_name"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# System
ACTIVE_THREADS = Gauge(
    "deerflow_active_threads",
    "Number of active agent threads",
)

CHECKPOINT_COUNT = Counter(
    "deerflow_checkpoints_total",
    "Total number of checkpoints created",
)

# HITL
HITL_REQUESTS_TOTAL = Counter(
    "deerflow_hitl_requests_total",
    "Total number of HITL requests",
    label_names=["hitl_type"],
)

# MCP
MCP_CALLS_TOTAL = Counter(
    "deerflow_mcp_calls_total",
    "Total number of MCP tool calls",
    label_names=["server_name", "tool_name", "status"],
)

# Web search
WEB_SEARCH_LATENCY = Histogram(
    "deerflow_web_search_latency_seconds",
    "Web search latency",
    label_names=["provider"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

WEB_SEARCH_RESULTS = Counter(
    "deerflow_web_search_results_total",
    "Total number of web search results",
    label_names=["provider", "status"],
)

# Skill execution
SKILL_EXECUTION_DURATION = Histogram(
    "deerflow_skill_execution_duration_seconds",
    "Skill execution duration",
    label_names=["skill_name", "load_type"],
    buckets=[0.01, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0],
)

SKILL_LOAD_ERRORS = Counter(
    "deerflow_skill_load_errors_total",
    "Total number of skill load errors",
    label_names=["skill_name"],
)

# Command execution
COMMAND_EXECUTION_DURATION = Histogram(
    "deerflow_command_execution_duration_seconds",
    "Command execution duration",
    label_names=["sandbox_level"],
    buckets=[0.01, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0],
)

DANGEROUS_COMMANDS_DETECTED = Counter(
    "deerflow_dangerous_commands_detected_total",
    "Total number of dangerous commands detected",
    label_names=["flag_type"],
)


class MetricsCollector:
    """Convenience class for recording metrics."""

    @staticmethod
    def record_tool_call(tool_name: str, duration_sec: float, status: str) -> None:
        """Record a tool call metric."""
        TOOL_CALLS_TOTAL.inc(labels={"tool_name": tool_name, "status": status})
        TOOL_CALL_DURATION.observe(value=duration_sec, labels={"tool_name": tool_name})

    @staticmethod
    def record_llm_usage(model_name: str, input_tokens: int, output_tokens: int) -> None:
        """Record LLM token usage."""
        LLM_TOKEN_USAGE.inc(
            labels={"model_name": model_name, "token_type": "input"},
            amount=input_tokens,
        )
        LLM_TOKEN_USAGE.inc(
            labels={"model_name": model_name, "token_type": "output"},
            amount=output_tokens,
        )

    @staticmethod
    def record_llm_latency(model_name: str, latency_sec: float) -> None:
        """Record LLM call latency."""
        LLM_LATENCY.observe(value=latency_sec, labels={"model_name": model_name})

    @staticmethod
    def record_agent_run(agent_name: str, status: str) -> None:
        """Record an agent run."""
        AGENT_RUNS_TOTAL.inc(labels={"agent_name": agent_name, "status": status})

    @staticmethod
    def record_web_search(provider: str, latency_sec: float, status: str, results_count: int = 0) -> None:
        """Record a web search."""
        WEB_SEARCH_LATENCY.observe(value=latency_sec, labels={"provider": provider})
        WEB_SEARCH_RESULTS.inc(
            labels={"provider": provider, "status": status},
            amount=results_count,
        )

    @staticmethod
    def record_mcp_call(server_name: str, tool_name: str, status: str) -> None:
        """Record an MCP call."""
        MCP_CALLS_TOTAL.inc(
            labels={"server_name": server_name, "tool_name": tool_name, "status": status}
        )

    @staticmethod
    def record_skill_execution(skill_name: str, load_type: str, duration_sec: float) -> None:
        """Record a skill execution."""
        SKILL_EXECUTION_DURATION.observe(
            value=duration_sec,
            labels={"skill_name": skill_name, "load_type": load_type},
        )

    @staticmethod
    def record_skill_load_error(skill_name: str) -> None:
        """Record a skill load error."""
        SKILL_LOAD_ERRORS.inc(labels={"skill_name": skill_name})

    @staticmethod
    def record_command_execution(sandbox_level: str, duration_sec: float) -> None:
        """Record a command execution."""
        COMMAND_EXECUTION_DURATION.observe(
            value=duration_sec,
            labels={"sandbox_level": sandbox_level},
        )

    @staticmethod
    def record_dangerous_command(flag_type: str) -> None:
        """Record a dangerous command detection."""
        DANGEROUS_COMMANDS_DETECTED.inc(labels={"flag_type": flag_type})

    @staticmethod
    def record_checkpoint() -> None:
        """Record a checkpoint creation."""
        CHECKPOINT_COUNT.inc()

    @staticmethod
    def record_hitl_request(hitl_type: str) -> None:
        """Record an HITL request."""
        HITL_REQUESTS_TOTAL.inc(labels={"hitl_type": hitl_type})

    @staticmethod
    def set_active_threads(count: int) -> None:
        """Set active threads gauge."""
        ACTIVE_THREADS.set(value=float(count))

    @staticmethod
    def get_all_metrics() -> dict[str, Any]:
        """Get all current metrics as a dictionary."""
        return {
            "agent_runs": AGENT_RUNS_TOTAL.collect(),
            "tool_calls": TOOL_CALLS_TOTAL.collect(),
            "tool_call_duration": {
                k: {"count": len(v), "sum": sum(v)}
                for k, v in TOOL_CALL_DURATION._values.items()
            },
            "llm_token_usage": LLM_TOKEN_USAGE.collect(),
            "llm_latency": {
                k: {"count": len(v), "sum": sum(v)}
                for k, v in LLM_LATENCY._values.items()
            },
            "active_threads": ACTIVE_THREADS.get(),
            "checkpoints": CHECKPOINT_COUNT.collect(),
            "hitl_requests": HITL_REQUESTS_TOTAL.collect(),
            "mcp_calls": MCP_CALLS_TOTAL.collect(),
            "web_search_latency": {
                k: {"count": len(v), "sum": sum(v)}
                for k, v in WEB_SEARCH_LATENCY._values.items()
            },
            "skill_execution_duration": {
                k: {"count": len(v), "sum": sum(v)}
                for k, v in SKILL_EXECUTION_DURATION._values.items()
            },
            "skill_load_errors": SKILL_LOAD_ERRORS.collect(),
            "command_execution_duration": {
                k: {"count": len(v), "sum": sum(v)}
                for k, v in COMMAND_EXECUTION_DURATION._values.items()
            },
            "dangerous_commands": DANGEROUS_COMMANDS_DETECTED.collect(),
        }

"""Observability data types and event definitions.

Defines all data structures used by the observability system for tracking
agent execution, tool calls, skill execution, MCP calls, web searches,
and command execution auditing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


class ObservabilityEventType:
    """Observability event type constants."""

    # Agent lifecycle
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"

    # Model calls
    MODEL_CALL_STARTED = "model_call_started"
    MODEL_CALL_COMPLETED = "model_call_completed"
    THINKING_CONTENT = "thinking_content"

    # Tool calls
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_COMPLETED = "tool_call_completed"
    TOOL_CALL_FAILED = "tool_call_failed"

    # Skill execution
    SKILL_LOADED = "skill_loaded"
    SKILL_EXECUTION_STARTED = "skill_execution_started"
    SKILL_EXECUTION_COMPLETED = "skill_execution_completed"
    SKILL_EXECUTION_FAILED = "skill_execution_failed"

    # MCP calls
    MCP_CALL_STARTED = "mcp_call_started"
    MCP_CALL_COMPLETED = "mcp_call_completed"
    MCP_CALL_FAILED = "mcp_call_failed"
    MCP_SERVER_HEALTH_CHECK = "mcp_server_health_check"

    # Web search
    WEB_SEARCH_STARTED = "web_search_started"
    WEB_SEARCH_COMPLETED = "web_search_completed"
    WEB_SEARCH_FAILED = "web_search_failed"

    # Sandbox / command execution
    COMMAND_EXECUTION_STARTED = "command_execution_started"
    COMMAND_EXECUTION_COMPLETED = "command_execution_completed"
    COMMAND_EXECUTION_FAILED = "command_execution_failed"
    DANGEROUS_COMMAND_DETECTED = "dangerous_command_detected"

    # Checkpoints
    CHECKPOINT_CREATED = "checkpoint_created"
    CHECKPOINT_RESTORED = "checkpoint_restored"

    # HITL
    HITL_REQUESTED = "hitl_requested"
    HITL_RESOLVED = "hitl_resolved"

    # Loop detection
    LOOP_DETECTED = "loop_detected"
    LOOP_BROKEN = "loop_broken"

    # Heartbeat
    HEARTBEAT = "heartbeat"


@dataclass
class ObservabilityEvent:
    """Generic observability event."""

    event_type: str
    timestamp: float
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    payload: dict = field(default_factory=dict)


@dataclass
class ToolCallSpan:
    """Tool call tracing span."""

    span_id: str
    trace_id: str
    parent_span_id: Optional[str] = None

    # Call info
    tool_name: str = ""
    tool_call_id: str = ""
    arguments: dict = field(default_factory=dict)

    # Timing
    start_time: float = 0.0
    end_time: Optional[float] = None
    duration_ms: Optional[int] = None

    # Execution info
    status: str = "pending"  # pending | success | error | timeout
    result: Optional[Any] = None
    error_message: Optional[str] = None

    # Performance
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None


@dataclass
class ThinkingRecord:
    """LLM thinking process record."""

    timestamp: float
    model_name: str
    thinking_content: Optional[str] = None
    duration_ms: int = 0
    tool_calls_planned: list[str] = field(default_factory=list)
    turn_number: int = 0


@dataclass
class SkillExecutionRecord:
    """Skill execution record."""

    skill_name: str
    load_type: str = "resident"  # resident | deferred
    trigger_keyword: Optional[str] = None

    # Timing
    load_start_time: float = 0.0
    load_end_time: Optional[float] = None
    execution_start_time: Optional[float] = None
    execution_end_time: Optional[float] = None

    # Status
    status: str = "loading"  # loading | loaded | executing | completed | error
    error_message: Optional[str] = None

    # Outputs
    artifacts_produced: list[str] = field(default_factory=list)
    scripts_executed: list[str] = field(default_factory=list)


@dataclass
class MCPCallSpan:
    """MCP call tracing span."""

    span_id: str
    trace_id: str
    mcp_server_name: str = ""
    mcp_tool_name: str = ""

    # Timing
    start_time: float = 0.0
    end_time: Optional[float] = None
    duration_ms: Optional[int] = None

    # Call info
    request_params: dict = field(default_factory=dict)
    response: Optional[Any] = None

    # Status
    status: str = "pending"
    error_type: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class WebSearchRecord:
    """Web search record."""

    search_id: str
    provider: str = ""  # tavily | ddg | exa | firecrawl | jina
    query: str = ""

    # Timing
    request_time: float = 0.0
    response_time: Optional[float] = None
    latency_ms: Optional[int] = None

    # Results
    results_count: int = 0
    top_result_title: Optional[str] = None
    top_result_url: Optional[str] = None

    # Status
    status: str = "pending"
    error_message: Optional[str] = None
    cache_hit: bool = False


@dataclass
class CommandAuditRecord:
    """Command execution audit record."""

    command_id: str
    command: str = ""
    sandbox_level: str = "local"  # local | docker | k8s

    # Timing
    start_time: float = 0.0
    end_time: Optional[float] = None
    duration_ms: Optional[int] = None

    # Execution result
    exit_code: Optional[int] = None
    stdout_preview: Optional[str] = None
    stderr_preview: Optional[str] = None
    status: str = "pending"
    error_message: Optional[str] = None

    # Security
    is_dangerous: bool = False
    danger_flags: list[str] = field(default_factory=list)

    # Resources
    cpu_time_ms: Optional[int] = None
    memory_peak_mb: Optional[float] = None

"""RunConfig Schema - ARW 运行时配置规范.

借鉴 DeerFlow RunnableConfig.configurable 模式，ARW 所有运行时参数收敛到
RunConfig 标准 schema，明确三方注入边界，作为 ARC ↔ Worker 的输入契约.

注入方:
- ARC 注入: scheduler_run_id, agent_name, Pod 资源, 沙箱挂载
- Master 注入: task_input, approval_policy, is_plan_mode, subagent_enabled
- Worker 自决: model_name, 模型降级链, compact_strategy, tool_search_enabled, thinking_enabled
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class RunConfig:
    """ARW Runtime Configuration Schema.

    This dataclass defines the complete runtime configuration for Agent Runtime Worker,
    serving as the input contract between ARC and Worker.

    The configuration is divided into three injection sources:
    1. ARC Injected (immutable during runtime)
    2. Master Injected (task-level, may be updated via HITL)
    3. Worker Self-Determined (can be overridden by ARC config center)
    """

    # ========================================================================
    # ARC Injected (immutable during runtime)
    # ========================================================================

    scheduler_run_id: str | None = None
    """调度运行 ID，等于调度它的 Master Pod Name.
    
    Used as RocketMQ Tag for precise event routing.
    """

    agent_name: str = "default"
    """Agent 名称."""

    pod_resources: dict[str, Any] = field(default_factory=dict)
    """Pod 资源配置: CPU, memory, etc."""

    sandbox_mounts: list[dict] = field(default_factory=list)
    """沙箱挂载点配置."""

    workspace_base_path: str = "/mnt/user-data"
    """工作区基础路径."""

    # ========================================================================
    # Master Injected (task-level, mutable)
    # ========================================================================

    task_input: dict[str, Any] = field(default_factory=dict)
    """任务输入数据."""

    task_description: str = ""
    """任务目标描述."""

    ontology_info: dict[str, Any] = field(default_factory=dict)
    """本体信息."""

    approval_policy: str = "default"
    """审批策略: default, strict, none."""

    is_plan_mode: bool = False
    """是否启用 Plan 模式 (TodoMiddleware)."""

    subagent_enabled: bool = False
    """是否启用 Subagent 委托."""

    # ========================================================================
    # Worker Self-Determined (overrideable by ARC config center)
    # ========================================================================

    model_name: str = "gpt-4o"
    """当前使用的模型名称."""

    model_fallback_chain: list[str] = field(default_factory=list)
    """模型降级链: 主模型不可用时按序降级."""

    model_tier: str = "standard"
    """当前 LLM 档位: economy, standard, premium."""

    compact_strategy: Literal["truncate", "summarize", "hybrid"] = "truncate"
    """上下文 Compact 策略.
    
    - truncate: 简单截断 + 保留最近 N 条（默认）
    - summarize: LLM 摘要
    - hybrid: 远端摘要 + 近端截断
    """

    tool_search_enabled: bool = True
    """是否启用延迟 Skill 检索 (skill_search 工具)."""

    thinking_enabled: bool = False
    """是否启用 thinking 模式（用于推理类模型）."""

    max_tokens: int = 4000
    """最大 Token 数."""

    temperature: float = 0.7
    """采样温度."""

    timeout_seconds: float = 3600.0
    """任务级超时（秒）."""

    # ========================================================================
    # Middleware Feature Toggles
    # ========================================================================

    enable_task_context: bool = True
    """启用 TaskContextMiddleware."""

    enable_thread_data: bool = True
    """启用 ThreadDataMiddleware."""

    enable_skill_loader: bool = True
    """启用 SkillLoaderMiddleware."""

    enable_knowledge_retrieval: bool = True
    """启用 KnowledgeRetrievalMiddleware."""

    enable_summarization: bool = True
    """启用 SummarizationMiddleware."""

    enable_checkpoint: bool = True
    """启用 CheckpointMiddleware."""

    enable_hitl: bool = True
    """启用 HITLMiddleware."""

    enable_event_report: bool = True
    """启用 EventReportMiddleware."""

    enable_guardrail: bool = True
    """启用 GuardrailMiddleware."""

    # ========================================================================
    # HITL Configuration
    # ========================================================================

    hitl_timeout_seconds: float = 86400.0
    """HITL 等待超时（秒），默认 24 小时."""

    auto_escalate_on_guardrail: bool = True
    """Guardrail 严重违规时自动升级到 HITL."""

    # ========================================================================
    # Event & Observability
    # ========================================================================

    enable_rocktmq_events: bool = True
    """启用 RocketMQ 事件上报."""

    enable_websocket_stream: bool = True
    """启用 WebSocket 展示流."""

    heartbeat_interval: float = 30.0
    """心跳间隔（秒）."""

    log_level: str = "INFO"
    """日志级别."""

    def to_configurable(self) -> dict[str, Any]:
        """Convert RunConfig to LangGraph configurable dict.

        Returns:
            Dictionary suitable for RunnableConfig.configurable.
        """
        return {
            "scheduler_run_id": self.scheduler_run_id,
            "agent_name": self.agent_name,
            "task_input": self.task_input,
            "task_description": self.task_description,
            "ontology_info": self.ontology_info,
            "approval_policy": self.approval_policy,
            "is_plan_mode": self.is_plan_mode,
            "subagent_enabled": self.subagent_enabled,
            "model_name": self.model_name,
            "model_tier": self.model_tier,
            "compact_strategy": self.compact_strategy,
            "tool_search_enabled": self.tool_search_enabled,
            "thinking_enabled": self.thinking_enabled,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_arc_payload(cls, payload: dict[str, Any]) -> "RunConfig":
        """Create RunConfig from ARC injection payload.

        Args:
            payload: Payload from ARC during Pod creation.

        Returns:
            RunConfig instance.
        """
        return cls(
            scheduler_run_id=payload.get("scheduler_run_id"),
            agent_name=payload.get("agent_name", "default"),
            pod_resources=payload.get("pod_resources", {}),
            sandbox_mounts=payload.get("sandbox_mounts", []),
            workspace_base_path=payload.get(
                "workspace_base_path", "/mnt/user-data"
            ),
            task_input=payload.get("task_input", {}),
            task_description=payload.get("task_description", ""),
            ontology_info=payload.get("ontology_info", {}),
            approval_policy=payload.get("approval_policy", "default"),
            is_plan_mode=payload.get("is_plan_mode", False),
            subagent_enabled=payload.get("subagent_enabled", False),
            model_name=payload.get("model_name", "gpt-4o"),
            model_fallback_chain=payload.get("model_fallback_chain", []),
            model_tier=payload.get("model_tier", "standard"),
            compact_strategy=payload.get("compact_strategy", "truncate"),
            tool_search_enabled=payload.get("tool_search_enabled", True),
            thinking_enabled=payload.get("thinking_enabled", False),
            max_tokens=payload.get("max_tokens", 4000),
            temperature=payload.get("temperature", 0.7),
            timeout_seconds=payload.get("timeout_seconds", 3600.0),
            enable_task_context=payload.get("enable_task_context", True),
            enable_thread_data=payload.get("enable_thread_data", True),
            enable_skill_loader=payload.get("enable_skill_loader", True),
            enable_knowledge_retrieval=payload.get(
                "enable_knowledge_retrieval", True
            ),
            enable_summarization=payload.get("enable_summarization", True),
            enable_checkpoint=payload.get("enable_checkpoint", True),
            enable_hitl=payload.get("enable_hitl", True),
            enable_event_report=payload.get("enable_event_report", True),
            enable_guardrail=payload.get("enable_guardrail", True),
            hitl_timeout_seconds=payload.get("hitl_timeout_seconds", 86400.0),
            auto_escalate_on_guardrail=payload.get(
                "auto_escalate_on_guardrail", True
            ),
            enable_rocktmq_events=payload.get("enable_rocktmq_events", True),
            enable_websocket_stream=payload.get("enable_websocket_stream", True),
            heartbeat_interval=payload.get("heartbeat_interval", 30.0),
            log_level=payload.get("log_level", "INFO"),
        )

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors.

        Returns:
            List of validation error messages. Empty if valid.
        """
        errors = []

        if not self.scheduler_run_id:
            errors.append("scheduler_run_id is required")

        if self.compact_strategy not in ("truncate", "summarize", "hybrid"):
            errors.append(
                f"Invalid compact_strategy: {self.compact_strategy}"
            )

        if self.model_tier not in ("economy", "standard", "premium"):
            errors.append(f"Invalid model_tier: {self.model_tier}")

        if self.temperature < 0 or self.temperature > 2:
            errors.append(f"Invalid temperature: {self.temperature}")

        if self.max_tokens < 1:
            errors.append(f"Invalid max_tokens: {self.max_tokens}")

        return errors

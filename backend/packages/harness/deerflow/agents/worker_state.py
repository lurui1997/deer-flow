"""WorkerState Schema for Agent Runtime Worker (ARW).

This module defines the unified state schema for ARW, extending ThreadState
with ARW-specific fields for task context, sandbox, skills, HITL, and runtime stats.

The WorkerState is the common foundation for:
- Checkpoint persistence
- HITL recovery
- Context compaction
- Subagent result reflux
"""

from __future__ import annotations

from typing import Annotated, NotRequired, TypedDict

from langchain.agents import AgentState

from deerflow.agents.thread_state import (
    SandboxState,
    ThreadDataState,
    merge_artifacts,
    merge_viewed_images,
    ViewedImageData,
)


# ---------------------------------------------------------------------------
# Task Context (常驻区 - 永不被 Compact)
# ---------------------------------------------------------------------------


class TaskContext(TypedDict):
    """ARC 注入的任务需求上下文 - 常驻区，永不被 Compact."""

    scheduler_run_id: NotRequired[str | None]
    """调度运行 ID，等于调度它的 Master Pod Name."""

    agent_name: NotRequired[str | None]
    """Agent 名称."""

    task_input: NotRequired[dict | None]
    """任务输入数据."""

    task_description: NotRequired[str | None]
    """任务目标描述."""

    ontology_info: NotRequired[dict | None]
    """本体信息."""

    approval_policy: NotRequired[str | None]
    """审批策略."""

    is_plan_mode: NotRequired[bool | None]
    """是否启用 Plan 模式."""

    subagent_enabled: NotRequired[bool | None]
    """是否启用 Subagent."""


# ---------------------------------------------------------------------------
# Skill Registry State
# ---------------------------------------------------------------------------


class SkillInfo(TypedDict):
    """Skill 基本信息."""

    name: str
    """Skill 名称."""

    description: str
    """Skill 描述."""

    schema: NotRequired[dict | None]
    """工具 schema（仅常驻 Skill 有）."""


class SkillRegistryState(TypedDict):
    """Skill 注册表状态 - 支持二级加载."""

    resident_skills: NotRequired[list[SkillInfo]]
    """一级（常驻）Skill：Agent Spec 显式声明的 Skill."""

    deferred_skills: NotRequired[list[SkillInfo]]
    """二级（延迟）Skill：Skill 市场内潜在可用的 Skill，仅注册名称+描述."""

    loaded_skill_packages: NotRequired[list[str]]
    """已加载的 Skill 包路径列表."""


# ---------------------------------------------------------------------------
# Artifact Reference
# ---------------------------------------------------------------------------


class ArtifactRef(TypedDict):
    """工具产出物索引 - 写回 Ontology 之前的中转."""

    artifact_id: str
    """产出物 ID."""

    artifact_type: str
    """产出物类型."""

    name: str
    """产出物名称."""

    path: NotRequired[str | None]
    """本地路径（在 /mnt/user-data/outputs 下）."""

    metadata: NotRequired[dict | None]
    """产出物元数据."""


# ---------------------------------------------------------------------------
# Todo Item (Plan Mode)
# ---------------------------------------------------------------------------


class Todo(TypedDict):
    """Plan 模式的执行计划与进度."""

    id: str
    """Todo ID."""

    content: str
    """Todo 内容."""

    status: NotRequired[str | None]
    """状态: pending, in_progress, done."""

    parent_id: NotRequired[str | None]
    """父 Todo ID（支持嵌套）."""


# ---------------------------------------------------------------------------
# HITL State
# ---------------------------------------------------------------------------


class HITLState(TypedDict):
    """HITL 等待状态."""

    is_waiting: NotRequired[bool | None]
    """是否处于 HITL 等待状态."""

    hitl_type: NotRequired[str | None]
    """HITL 类型: clarification, harness_intercept, etc."""

    clarification_type: NotRequired[str | None]
    """澄清类型: missing_info, ambiguous_requirement, approach_choice, risk_confirmation, suggestion."""

    question: NotRequired[str | None]
    """问题内容."""

    context: NotRequired[str | None]
    """额外上下文."""

    options: NotRequired[list[str] | None]
    """选项列表."""

    tool_call_id: NotRequired[str | None]
    """关联的工具调用 ID."""

    resume_node: NotRequired[str | None]
    """恢复点节点."""

    resumed_at: NotRequired[float | None]
    """恢复时间戳."""

    response: NotRequired[str | None]
    """用户/审批回执."""


# ---------------------------------------------------------------------------
# Runtime Stats
# ---------------------------------------------------------------------------


class RuntimeStats(TypedDict):
    """运行时统计信息."""

    token_count: NotRequired[int | None]
    """Token 计数."""

    token_limit: NotRequired[int | None]
    """Token 上限."""

    current_model: NotRequired[str | None]
    """当前使用的模型名称."""

    model_tier: NotRequired[str | None]
    """当前 LLM 档位."""

    checkpoint_count: NotRequired[int | None]
    """检查点计数."""

    last_checkpoint_id: NotRequired[str | None]
    """最后检查点 ID."""

    start_time: NotRequired[float | None]
    """任务开始时间戳."""

    last_activity: NotRequired[float | None]
    """最后活动时间戳."""


# ---------------------------------------------------------------------------
# Worker State (Main)
# ---------------------------------------------------------------------------


class WorkerState(AgentState):
    """ARW 统一状态 Schema.

    继承自 LangGraph AgentState，对齐 DeerFlow ThreadState，
    是检查点持久化、HITL 恢复、上下文 Compact、Subagent 结果回流的共同基础.

    三层上下文分区:
    - 常驻区: task_context（永不被 Compact）
    - 知识区: retrieved_knowledge（参与 Compact，优先保留）
    - 工作区: messages（达到 Token 预算 80% 时触发 Compact）
    """

    # === 继承自 ThreadState 的字段 ===
    sandbox: NotRequired[SandboxState | None]
    """沙箱状态."""

    thread_data: NotRequired[ThreadDataState | None]
    """Thread 数据路径（workspace/uploads/outputs）."""

    title: NotRequired[str | None]
    """对话标题."""

    artifacts: Annotated[list[str], merge_artifacts]
    """产出物列表（合并策略：去重）."""

    todos: NotRequired[list[Todo] | None]
    """Plan 模式的执行计划."""

    uploaded_files: NotRequired[list[dict] | None]
    """已上传文件列表."""

    viewed_images: Annotated[dict[str, ViewedImageData], merge_viewed_images]
    """已查看图片（合并策略：新值覆盖旧值，空 dict 表示清空）."""

    # === ARW 特有字段 ===
    task_context: NotRequired[TaskContext | None]
    """ARC 注入的任务需求（常驻区）."""

    skills: NotRequired[SkillRegistryState | None]
    """Skill 注册表状态."""

    artifact_refs: NotRequired[list[ArtifactRef] | None]
    """工具产出物索引（写回 Ontology 之前的中转）."""

    hitl: NotRequired[HITLState | None]
    """HITL 等待状态."""

    runtime: NotRequired[RuntimeStats | None]
    """运行时统计."""

    retrieved_knowledge: NotRequired[list[dict] | None]
    """RAG/MCP 检索结果（知识区）."""

    # === LangGraph 标准字段（已在 AgentState 中定义） ===
    # messages: list[BaseMessage] - 完整对话与工具调用历史

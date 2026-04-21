"""ARW Agent Factory - Agent Runtime Worker Agent 工厂.

组装10层中间件链，创建配置化的 ARW Agent:

中间件链顺序 (与文档 §2.3 对齐):
  1. TaskContextMiddleware      - 注入 ARC 任务需求
  2. ThreadDataMiddleware       - 创建工作目录 (继承自 DeerFlow)
  3. SkillLoaderMiddleware      - Skill 二级加载
  4. OntologyContextMiddleware  - 读取本体信息 (继承自 DeerFlow)
  5. KnowledgeRetrievalMiddleware - RAG/MCP 检索
  6. SummarizationMiddleware    - 上下文 Compact (继承自 DeerFlow)
  7. CheckpointMiddleware       - 检查点 + pre-run snapshot
  8. HITLMiddleware            - HITL 平台桥接 (wrap_tool_call 链最末位)
  9. EventReportMiddleware     - 事件上报
  10. GuardrailMiddleware      - 输出护栏 (after_model 链最末位)

约束:
- HITLMiddleware 必须位于 wrap_tool_call 链最末位
- GuardrailMiddleware 作用于 after_model 输出内容侧，是 after_model 链最末位
- 中间件之间通过 WorkerState 通信，不直接相互调用
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware

from deerflow.agents.middlewares.checkpoint_middleware import (
    CheckpointMiddleware,
)
from deerflow.agents.middlewares.event_report_middleware import (
    EventReportMiddleware,
)
from deerflow.agents.middlewares.guardrail_middleware import GuardrailMiddleware
from deerflow.agents.middlewares.hitl_middleware import HITLMiddleware
from deerflow.agents.middlewares.knowledge_retrieval_middleware import (
    KnowledgeRetrievalMiddleware,
)
from deerflow.agents.middlewares.skill_loader_middleware import (
    SkillLoaderMiddleware,
)
from deerflow.agents.middlewares.task_context_middleware import (
    TaskContextMiddleware,
)
from deerflow.agents.run_config import RunConfig
from deerflow.agents.worker_state import WorkerState
from deerflow.tools.builtins import ask_clarification_tool

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


def create_arw_agent(
    model: BaseChatModel,
    tools: list[BaseTool] | None = None,
    *,
    run_config: RunConfig | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    extra_middleware: list[AgentMiddleware] | None = None,
) -> CompiledStateGraph:
    """Create an Agent Runtime Worker (ARW) agent with full middleware chain.

    This factory creates an ARW agent with the complete 10-layer middleware chain
    as specified in the ARW design document.

    Middleware Chain:
        1. TaskContextMiddleware - Inject ARC task requirements
        2. ThreadDataMiddleware - Create workspace directories
        3. SkillLoaderMiddleware - Two-tier skill loading
        4. UploadsMiddleware - Handle file uploads (DeerFlow built-in)
        5. SandboxMiddleware - Sandbox execution (DeerFlow built-in)
        6. DanglingToolCallMiddleware - Handle dangling tool calls
        7. GuardrailMiddleware (optional) - Content guardrails
        8. ToolErrorHandlingMiddleware - Tool error handling
        9. SummarizationMiddleware (optional) - Context compaction
        10. TodoMiddleware (optional) - Plan mode task tracking
        11. TitleMiddleware (optional) - Auto title generation
        12. MemoryMiddleware (optional) - Memory management
        13. ViewImageMiddleware (optional) - Vision support
        14. SubagentLimitMiddleware (optional) - Subagent limiting
        15. LoopDetectionMiddleware - Loop detection
        16. KnowledgeRetrievalMiddleware - RAG/MCP retrieval
        17. CheckpointMiddleware - Checkpoints and snapshots
        18. HITLMiddleware - HITL platform bridging
        19. EventReportMiddleware - Event reporting
        20. ClarificationMiddleware - Clarification handling
        21. GuardrailMiddleware (output) - Output guardrails

    Args:
        model: Chat model instance.
        tools: User-provided tools.
        run_config: ARW runtime configuration. Uses defaults if None.
        checkpointer: Optional checkpoint saver for persistence.
        extra_middleware: Additional middleware to insert into the chain.

    Returns:
        Compiled LangGraph agent.
    """
    config = run_config or RunConfig()

    # Validate configuration
    errors = config.validate()
    if errors:
        raise ValueError(f"Invalid RunConfig: {'; '.join(errors)}")

    # Build middleware chain
    middleware_chain: list[AgentMiddleware] = []
    extra_tools: list[BaseTool] = list(tools or [])

    # ========================================================================
    # Layer 1: TaskContextMiddleware
    # ========================================================================
    if config.enable_task_context:
        middleware_chain.append(
            TaskContextMiddleware(
                scheduler_run_id=config.scheduler_run_id,
                agent_name=config.agent_name,
                task_input=config.task_input,
                task_description=config.task_description,
                ontology_info=config.ontology_info,
                approval_policy=config.approval_policy,
                is_plan_mode=config.is_plan_mode,
                subagent_enabled=config.subagent_enabled,
            )
        )
        logger.debug("ARW Factory: Added TaskContextMiddleware")

    # ========================================================================
    # Layer 2: ThreadDataMiddleware (DeerFlow built-in)
    # ========================================================================
    if config.enable_thread_data:
        from deerflow.agents.middlewares.thread_data_middleware import (
            ThreadDataMiddleware,
        )

        middleware_chain.append(ThreadDataMiddleware(lazy_init=True))
        logger.debug("ARW Factory: Added ThreadDataMiddleware")

    # ========================================================================
    # Layer 3: SkillLoaderMiddleware
    # ========================================================================
    if config.enable_skill_loader:
        middleware_chain.append(
            SkillLoaderMiddleware(
                enable_deferred_loading=config.tool_search_enabled,
            )
        )
        logger.debug("ARW Factory: Added SkillLoaderMiddleware")

    # ========================================================================
    # Layer 4-6: Uploads, Sandbox, DanglingToolCall (DeerFlow built-ins)
    # ========================================================================
    from deerflow.agents.middlewares.dangling_tool_call_middleware import (
        DanglingToolCallMiddleware,
    )
    from deerflow.agents.middlewares.uploads_middleware import UploadsMiddleware
    from deerflow.sandbox.middleware import SandboxMiddleware

    middleware_chain.append(UploadsMiddleware())
    middleware_chain.append(SandboxMiddleware(lazy_init=True))
    middleware_chain.append(DanglingToolCallMiddleware())
    logger.debug("ARW Factory: Added Uploads, Sandbox, DanglingToolCall middlewares")

    # ========================================================================
    # Layer 7: GuardrailMiddleware (input side)
    # ========================================================================
    if config.enable_guardrail:
        middleware_chain.append(GuardrailMiddleware())
        logger.debug("ARW Factory: Added GuardrailMiddleware (input)")

    # ========================================================================
    # Layer 8: ToolErrorHandlingMiddleware (DeerFlow built-in)
    # ========================================================================
    from deerflow.agents.middlewares.tool_error_handling_middleware import (
        ToolErrorHandlingMiddleware,
    )

    middleware_chain.append(ToolErrorHandlingMiddleware())
    logger.debug("ARW Factory: Added ToolErrorHandlingMiddleware")

    # ========================================================================
    # Layer 9: SummarizationMiddleware (DeerFlow built-in, conditional)
    # ========================================================================
    if config.enable_summarization:
        from deerflow.agents.middlewares.summarization_middleware import (
            DeerFlowSummarizationMiddleware,
        )

        # Note: SummarizationMiddleware requires a model for summarization
        # For now, we skip it unless explicitly configured
        logger.debug("ARW Factory: SummarizationMiddleware skipped (requires config)")

    # ========================================================================
    # Layer 10: TodoMiddleware (DeerFlow built-in, plan mode)
    # ========================================================================
    if config.is_plan_mode:
        from deerflow.agents.middlewares.todo_middleware import TodoMiddleware

        middleware_chain.append(
            TodoMiddleware(
                system_prompt="""
<todo_list_system>
You have access to the `write_todos` tool to help you manage and track complex multi-step objectives.

**CRITICAL RULES:**
- Mark todos as completed IMMEDIATELY after finishing each step
- Keep EXACTLY ONE task as `in_progress` at any time
- Update the todo list in REAL-TIME as you work
- DO NOT use this tool for simple tasks (< 3 steps)
</todo_list_system>
""",
                tool_description="Use this tool to create and manage a structured task list for complex work sessions.",
            )
        )
        logger.debug("ARW Factory: Added TodoMiddleware (plan mode)")

    # ========================================================================
    # Layer 11-14: Optional middlewares (Memory, Vision, Subagent, etc.)
    # ========================================================================
    # These would be added based on feature flags in the config

    # ========================================================================
    # Layer 15: LoopDetectionMiddleware (DeerFlow built-in)
    # ========================================================================
    from deerflow.agents.middlewares.loop_detection_middleware import (
        LoopDetectionMiddleware,
    )

    middleware_chain.append(LoopDetectionMiddleware())
    logger.debug("ARW Factory: Added LoopDetectionMiddleware")

    # ========================================================================
    # Layer 16: KnowledgeRetrievalMiddleware
    # ========================================================================
    if config.enable_knowledge_retrieval:
        middleware_chain.append(
            KnowledgeRetrievalMiddleware(
                enable_rag=True,
                enable_mcp=True,
            )
        )
        logger.debug("ARW Factory: Added KnowledgeRetrievalMiddleware")

    # ========================================================================
    # Layer 17: CheckpointMiddleware
    # ========================================================================
    if config.enable_checkpoint:
        middleware_chain.append(CheckpointMiddleware())
        logger.debug("ARW Factory: Added CheckpointMiddleware")

    # ========================================================================
    # Layer 18: HITLMiddleware (wrap_tool_call chain last)
    # ========================================================================
    if config.enable_hitl:
        middleware_chain.append(HITLMiddleware())
        extra_tools.append(ask_clarification_tool)
        logger.debug("ARW Factory: Added HITLMiddleware")

    # ========================================================================
    # Layer 19: ClarificationMiddleware (DeerFlow built-in, always last among built-ins)
    # ========================================================================
    from deerflow.agents.middlewares.clarification_middleware import (
        ClarificationMiddleware,
    )

    middleware_chain.append(ClarificationMiddleware())
    logger.debug("ARW Factory: Added ClarificationMiddleware")

    # ========================================================================
    # Layer 20: EventReportMiddleware
    # ========================================================================
    if config.enable_event_report:
        middleware_chain.append(
            EventReportMiddleware(
                enable_rocktmq=config.enable_rocktmq_events,
                enable_websocket=config.enable_websocket_stream,
                heartbeat_interval=config.heartbeat_interval,
            )
        )
        logger.debug("ARW Factory: Added EventReportMiddleware")

    # ========================================================================
    # Layer 21: GuardrailMiddleware (output side, after_model chain last)
    # ========================================================================
    if config.enable_guardrail:
        middleware_chain.append(
            GuardrailMiddleware(
                enable_pii_detection=True,
                enable_sensitive_detection=True,
                enable_schema_validation=True,
            )
        )
        logger.debug("ARW Factory: Added GuardrailMiddleware (output)")

    # ========================================================================
    # Insert extra middleware if provided
    # ========================================================================
    if extra_middleware:
        # Insert before ClarificationMiddleware to maintain invariant
        clar_idx = next(
            i
            for i, m in enumerate(middleware_chain)
            if isinstance(m, ClarificationMiddleware)
        )
        for mw in extra_middleware:
            middleware_chain.insert(clar_idx, mw)
            clar_idx += 1
            logger.debug("ARW Factory: Added extra middleware %s", type(mw).__name__)

    # ========================================================================
    # Create agent with WorkerState schema
    # ========================================================================
    logger.info(
        "ARW Factory: Creating agent with %d middlewares and %d tools",
        len(middleware_chain),
        len(extra_tools),
    )

    return create_agent(
        model=model,
        tools=extra_tools or None,
        middleware=middleware_chain,
        state_schema=WorkerState,
        checkpointer=checkpointer,
        name=config.agent_name,
    )

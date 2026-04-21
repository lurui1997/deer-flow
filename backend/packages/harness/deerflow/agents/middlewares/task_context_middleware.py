"""TaskContextMiddleware - 注入 ARC 任务需求，初始化 WorkerState.task_context.

中间件 #1 in ARW middleware chain:
- 注入 ARC 任务需求
- 初始化 WorkerState.task_context
- 设置 scheduler_run_id
"""

from __future__ import annotations

import logging
from typing import override

from langchain.agents.middleware import AgentMiddleware
from langgraph.config import get_config
from langgraph.runtime import Runtime

from deerflow.agents.worker_state import TaskContext, WorkerState

logger = logging.getLogger(__name__)


class TaskContextMiddleware(AgentMiddleware[WorkerState]):
    """Inject ARC task context into WorkerState.

    This middleware initializes the task_context field of WorkerState with
    information injected by ARC, including scheduler_run_id, agent_name,
    task_input, and other task-level configuration.

    The task_context resides in the "resident zone" and is never compacted.
    """

    state_schema = WorkerState

    def __init__(
        self,
        scheduler_run_id: str | None = None,
        agent_name: str | None = None,
        task_input: dict | None = None,
        task_description: str | None = None,
        ontology_info: dict | None = None,
        approval_policy: str | None = None,
        is_plan_mode: bool = False,
        subagent_enabled: bool = False,
    ):
        """Initialize TaskContextMiddleware.

        Args:
            scheduler_run_id: The scheduler run ID (equals Master Pod Name).
            agent_name: The agent name.
            task_input: Task input data from ARC.
            task_description: Task goal description.
            ontology_info: Ontology information.
            approval_policy: Approval policy configuration.
            is_plan_mode: Whether plan mode is enabled.
            subagent_enabled: Whether subagent is enabled.
        """
        super().__init__()
        self._task_context = TaskContext(
            scheduler_run_id=scheduler_run_id,
            agent_name=agent_name,
            task_input=task_input or {},
            task_description=task_description,
            ontology_info=ontology_info or {},
            approval_policy=approval_policy,
            is_plan_mode=is_plan_mode,
            subagent_enabled=subagent_enabled,
        )

    @override
    def before_agent(self, state: WorkerState, runtime: Runtime) -> dict | None:
        """Inject task context before agent execution.

        Priority order for configuration:
        1. Constructor arguments (explicitly provided)
        2. Runtime context
        3. LangGraph config.configurable
        """
        # Try to get from runtime context or config
        config_data = {}
        try:
            config_data = get_config()
            config_data = config_data.get("configurable", {})
        except RuntimeError:
            pass

        # Merge with priority: constructor > config > defaults
        task_context = TaskContext()

        # scheduler_run_id
        task_context["scheduler_run_id"] = (
            self._task_context.get("scheduler_run_id")
            or runtime.context.get("scheduler_run_id") if runtime.context else None
            or config_data.get("scheduler_run_id")
        )

        # agent_name
        task_context["agent_name"] = (
            self._task_context.get("agent_name")
            or runtime.context.get("agent_name") if runtime.context else None
            or config_data.get("agent_name")
        )

        # task_input
        task_context["task_input"] = (
            self._task_context.get("task_input")
            or config_data.get("task_input")
            or {}
        )

        # task_description
        task_context["task_description"] = (
            self._task_context.get("task_description")
            or config_data.get("task_description")
        )

        # ontology_info
        task_context["ontology_info"] = (
            self._task_context.get("ontology_info")
            or config_data.get("ontology_info")
            or {}
        )

        # approval_policy
        task_context["approval_policy"] = (
            self._task_context.get("approval_policy")
            or config_data.get("approval_policy")
        )

        # is_plan_mode
        task_context["is_plan_mode"] = (
            self._task_context.get("is_plan_mode")
            if self._task_context.get("is_plan_mode") is not None
            else config_data.get("is_plan_mode", False)
        )

        # subagent_enabled
        task_context["subagent_enabled"] = (
            self._task_context.get("subagent_enabled")
            if self._task_context.get("subagent_enabled") is not None
            else config_data.get("subagent_enabled", False)
        )

        logger.debug(
            "TaskContextMiddleware initialized with scheduler_run_id=%s, agent_name=%s",
            task_context.get("scheduler_run_id"),
            task_context.get("agent_name"),
        )

        return {"task_context": task_context}

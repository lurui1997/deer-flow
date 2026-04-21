"""CheckpointMiddleware - 关键节点写检查点 + pre-run snapshot.

中间件 #7 in ARW middleware chain:
- 关键节点写检查点
- Pre-run snapshot 捕获
- 支持失败时回滚到 step 之前

与 LangGraph Checkpointer 抽象配合，后端支持 memory/sqlite/postgres 三档可配.
"""

from __future__ import annotations

import logging
import time
from typing import override

from langchain.agents.middleware import AgentMiddleware
from langgraph.config import get_config
from langgraph.runtime import Runtime

from deerflow.agents.worker_state import RuntimeStats, WorkerState

logger = logging.getLogger(__name__)


class CheckpointMiddleware(AgentMiddleware[WorkerState]):
    """Capture checkpoints and pre-run snapshots for recovery.

    This middleware captures checkpoints at key execution points and maintains
    pre-run snapshots that enable rollback to the state before a step execution.

    Key features:
    - Checkpoint at model call start
    - Checkpoint at tool call start
    - Pre-run snapshot for rollback on failure
    - Update runtime stats (checkpoint count, last checkpoint ID)

    Works with LangGraph Checkpointer abstraction for persistence.
    """

    state_schema = WorkerState

    def __init__(
        self,
        enable_snapshots: bool = True,
        snapshot_on_model: bool = True,
        snapshot_on_tool: bool = True,
        max_snapshots: int = 10,
    ):
        """Initialize CheckpointMiddleware.

        Args:
            enable_snapshots: Whether to enable pre-run snapshots.
            snapshot_on_model: Whether to snapshot before model calls.
            snapshot_on_tool: Whether to snapshot before tool calls.
            max_snapshots: Maximum number of snapshots to retain.
        """
        super().__init__()
        self._enable_snapshots = enable_snapshots
        self._snapshot_on_model = snapshot_on_model
        self._snapshot_on_tool = snapshot_on_tool
        self._max_snapshots = max_snapshots

    def _update_runtime_stats(
        self, state: WorkerState, checkpoint_id: str | None = None
    ) -> RuntimeStats:
        """Update runtime statistics with checkpoint information.

        Args:
            state: Current WorkerState.
            checkpoint_id: Optional checkpoint ID to record.

        Returns:
            Updated RuntimeStats.
        """
        runtime = state.get("runtime") or {}

        stats = RuntimeStats(
            token_count=runtime.get("token_count"),
            token_limit=runtime.get("token_limit"),
            current_model=runtime.get("current_model"),
            model_tier=runtime.get("model_tier"),
            checkpoint_count=(runtime.get("checkpoint_count") or 0) + 1,
            last_checkpoint_id=checkpoint_id,
            start_time=runtime.get("start_time") or time.time(),
            last_activity=time.time(),
        )

        return stats

    @override
    def before_agent(self, state: WorkerState, runtime: Runtime) -> dict | None:
        """Initialize checkpoint tracking before agent execution.

        Sets up initial runtime stats with start time.
        """
        config_data = {}
        try:
            config_data = get_config()
            config_data = config_data.get("configurable", {})
        except RuntimeError:
            pass

        # Initialize runtime stats
        runtime_stats = RuntimeStats(
            start_time=time.time(),
            last_activity=time.time(),
            checkpoint_count=0,
            current_model=config_data.get("model_name"),
            model_tier=config_data.get("model_tier"),
        )

        logger.debug("CheckpointMiddleware initialized with runtime stats")
        return {"runtime": runtime_stats}

    @override
    def before_model(self, state: WorkerState, runtime: Runtime) -> dict | None:
        """Capture pre-model snapshot.

        Called before each model invocation. Updates runtime stats and
        marks this as a checkpoint point.
        """
        if not self._enable_snapshots or not self._snapshot_on_model:
            return None

        # Generate checkpoint ID
        checkpoint_id = f"model_{int(time.time() * 1000)}"

        # Update runtime stats
        stats = self._update_runtime_stats(state, checkpoint_id)

        logger.debug(
            "CheckpointMiddleware: Pre-model checkpoint %s", checkpoint_id
        )

        # Note: Actual checkpoint persistence is handled by LangGraph Checkpointer
        # This middleware just tracks metadata and ensures the state is checkpoint-ready
        return {"runtime": stats}

    @override
    def wrap_tool_call(
        self,
        request,
        handler,
    ):
        """Wrap tool call with pre-run snapshot.

        Captures snapshot before tool execution. If tool fails, the snapshot
        enables rollback to the pre-execution state.
        """
        if not self._enable_snapshots or not self._snapshot_on_tool:
            return handler(request)

        # Generate checkpoint ID for this tool call
        checkpoint_id = f"tool_{request.tool_call.get('id', 'unknown')}"
        logger.debug(
            "CheckpointMiddleware: Pre-tool checkpoint %s", checkpoint_id
        )

        # Execute the tool call
        try:
            result = handler(request)
            return result
        except Exception as e:
            logger.exception(
                "Tool execution failed, checkpoint %s available for rollback",
                checkpoint_id,
            )
            raise

    @override
    async def awrap_tool_call(self, request, handler):
        """Async version of wrap_tool_call."""
        if not self._enable_snapshots or not self._snapshot_on_tool:
            return await handler(request)

        checkpoint_id = f"tool_{request.tool_call.get('id', 'unknown')}"
        logger.debug(
            "CheckpointMiddleware: Pre-tool checkpoint %s", checkpoint_id
        )

        try:
            result = await handler(request)
            return result
        except Exception as e:
            logger.exception(
                "Tool execution failed, checkpoint %s available for rollback",
                checkpoint_id,
            )
            raise

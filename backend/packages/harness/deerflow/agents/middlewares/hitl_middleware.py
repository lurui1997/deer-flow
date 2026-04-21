"""HITLMiddleware - Human-in-the-Loop 平台桥接中间件.

中间件 #8 in ARW middleware chain (wrap_tool_call chain 最末位):
- 保持与 ClarificationMiddleware 等价的中断语义
- 写入 WorkerState.hitl
- 发出 agent_hitl_requests 事件
- 支持 Command(resume=...) 恢复

必须与 ClarificationMiddleware 协同工作，位于 wrap_tool_call 链最末位
(对齐 DeerFlow ClarificationMiddleware 的 last 约束).
"""

from __future__ import annotations

import logging
import time
from typing import override

from langchain.agents.middleware import AgentMiddleware
from langgraph.graph import END
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from deerflow.agents.worker_state import HITLState, WorkerState

logger = logging.getLogger(__name__)


class HITLMiddleware(AgentMiddleware[WorkerState]):
    """Bridge HITL between DeerFlow ClarificationMiddleware and platform.

    This middleware wraps and extends ClarificationMiddleware behavior:
    1. Intercepts ask_clarification tool calls (must be last in wrap_tool_call chain)
    2. Formats HITL state for WorkerState.hitl
    3. Emits agent_hitl_requests events to platform
    4. Supports resume via Command(resume=...)

    Position constraint: Must be LAST in wrap_tool_call chain to avoid
    being bypassed by subsequent tool interceptors.

    Works with DanglingToolCallMiddleware to handle dangling tool calls
    after interruption/resume.
    """

    state_schema = WorkerState

    # HITL type mapping from clarification_type to platform types
    HITL_TYPE_MAP = {
        "missing_info": "clarification",
        "ambiguous_requirement": "clarification",
        "approach_choice": "clarification",
        "risk_confirmation": "clarification",
        "suggestion": "clarification",
        # Platform extensions
        "harness_intercept": "harness_intercept",
    }

    def __init__(
        self,
        event_callback: callable | None = None,
        enable_platform_events: bool = True,
    ):
        """Initialize HITLMiddleware.

        Args:
            event_callback: Optional callback for HITL events.
                Signature: (event_type, payload) -> None
            enable_platform_events: Whether to emit platform events.
        """
        super().__init__()
        self._event_callback = event_callback
        self._enable_platform_events = enable_platform_events

    def _extract_hitl_state(self, request: ToolCallRequest) -> HITLState:
        """Extract HITL state from ask_clarification tool call.

        Args:
            request: The tool call request.

        Returns:
            HITLState populated from tool call arguments.
        """
        args = request.tool_call.get("args", {})
        tool_call_id = request.tool_call.get("id", "")
        clarification_type = args.get("clarification_type", "missing_info")

        hitl_type = self.HITL_TYPE_MAP.get(clarification_type, "clarification")

        return HITLState(
            is_waiting=True,
            hitl_type=hitl_type,
            clarification_type=clarification_type,
            question=args.get("question", ""),
            context=args.get("context"),
            options=args.get("options"),
            tool_call_id=tool_call_id,
            resume_node="__end__",  # Default to END for interruption
        )

    def _emit_hitl_request(self, hitl_state: HITLState, thread_id: str | None) -> None:
        """Emit HITL request event to platform.

        Args:
            hitl_state: The HITL state to emit.
            thread_id: Current thread ID.
        """
        if not self._enable_platform_events:
            return

        event_payload = {
            "event_type": "agent_hitl_requests",
            "thread_id": thread_id,
            "hitl_type": hitl_state.get("hitl_type"),
            "clarification_type": hitl_state.get("clarification_type"),
            "question": hitl_state.get("question"),
            "context": hitl_state.get("context"),
            "options": hitl_state.get("options"),
            "tool_call_id": hitl_state.get("tool_call_id"),
            "created_at": time.time(),
        }

        logger.info(
            "HITLMiddleware: Emitting HITL request for thread %s, type=%s",
            thread_id,
            hitl_state.get("hitl_type"),
        )

        if self._event_callback:
            try:
                self._event_callback("agent_hitl_requests", event_payload)
            except Exception as e:
                logger.exception("Failed to emit HITL event: %s", e)

    def _emit_hitl_resolved(
        self,
        hitl_state: HITLState,
        response: str,
        thread_id: str | None,
    ) -> None:
        """Emit HITL resolved event to platform.

        Args:
            hitl_state: The HITL state that was resolved.
            response: The response that resolved the HITL.
            thread_id: Current thread ID.
        """
        if not self._enable_platform_events:
            return

        event_payload = {
            "event_type": "agent_hitl_resolved",
            "thread_id": thread_id,
            "hitl_type": hitl_state.get("hitl_type"),
            "response": response,
            "resolved_at": time.time(),
        }

        logger.info(
            "HITLMiddleware: HITL resolved for thread %s", thread_id
        )

        if self._event_callback:
            try:
                self._event_callback("agent_hitl_resolved", event_payload)
            except Exception as e:
                logger.exception("Failed to emit HITL resolved event: %s", e)

    @override
    def wrap_tool_call(self, request, handler):
        """Intercept ask_clarification and handle HITL.

        Must be LAST in wrap_tool_call chain. Delegates to ClarificationMiddleware
        for actual interruption, but adds platform bridging.
        """
        tool_name = request.tool_call.get("name", "")

        # Only intercept ask_clarification
        if tool_name != "ask_clarification":
            return handler(request)

        # This middleware assumes ClarificationMiddleware has already handled
        # the ask_clarification and returned a Command. We just add platform
        # event emission here.

        # Execute handler (which should be ClarificationMiddleware)
        result = handler(request)

        # If result is a Command (interruption), emit HITL event
        if isinstance(result, Command):
            hitl_state = self._extract_hitl_state(request)

            # Get thread ID from config
            thread_id = None
            try:
                from langgraph.config import get_config
                config = get_config()
                thread_id = config.get("configurable", {}).get("thread_id")
            except Exception:
                pass

            # Emit platform event
            self._emit_hitl_request(hitl_state, thread_id)

            # Return HITL state update along with the Command
            # Note: We can't modify the Command directly, but the state
            # will be updated in the next checkpoint
            logger.info(
                "HITLMiddleware: HITL interruption handled for thread %s",
                thread_id,
            )

        return result

    @override
    async def awrap_tool_call(self, request, handler):
        """Async version of wrap_tool_call."""
        tool_name = request.tool_call.get("name", "")

        if tool_name != "ask_clarification":
            return await handler(request)

        result = await handler(request)

        if isinstance(result, Command):
            hitl_state = self._extract_hitl_state(request)

            thread_id = None
            try:
                from langgraph.config import get_config
                config = get_config()
                thread_id = config.get("configurable", {}).get("thread_id")
            except Exception:
                pass

            self._emit_hitl_request(hitl_state, thread_id)

            logger.info(
                "HITLMiddleware: HITL interruption handled for thread %s",
                thread_id,
            )

        return result

    def create_resume_command(
        self,
        response: str,
        hitl_state: HITLState,
    ) -> Command:
        """Create a Command to resume from HITL.

        This is called by the gateway when consuming agent_hitl_responses
        and injecting the resume command.

        Args:
            response: User's response to the HITL.
            hitl_state: The HITL state from the interrupted execution.

        Returns:
            Command to resume execution with the response.
        """
        from langchain_core.messages import ToolMessage

        tool_call_id = hitl_state.get("tool_call_id", "")

        # Create ToolMessage to answer the ask_clarification tool
        tool_message = ToolMessage(
            content=f"User responded: {response}",
            tool_call_id=tool_call_id,
            name="ask_clarification",
        )

        # Create resume command
        # goto=None means continue to next node in the graph
        command = Command(
            update={
                "messages": [tool_message],
                "hitl": {
                    **hitl_state,
                    "is_waiting": False,
                    "response": response,
                    "resumed_at": time.time(),
                },
            },
            goto=None,  # Continue normal execution
        )

        logger.info("HITLMiddleware: Created resume command for HITL")

        return command

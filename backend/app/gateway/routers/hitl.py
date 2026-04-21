"""HITL (Human-in-the-Loop) external control API endpoints.

This module provides REST API endpoints for external systems to:
1. Query HITL status for threads
2. Submit responses to HITL interruptions
3. List pending HITL requests

This enables integration with external workflow systems, approval workflows,
and custom UIs for human interaction.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.gateway.deps import get_checkpointer
from deerflow.runtime import serialize_channel_values

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/hitl", tags=["hitl"])


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class HITLClarificationDetails(BaseModel):
    """Details of a clarification request."""

    tool_call_id: str = Field(description="ID of the ask_clarification tool call")
    question: str = Field(description="The clarification question")
    clarification_type: str = Field(description="Type: missing_info, ambiguous_requirement, approach_choice, risk_confirmation, suggestion")
    context: str | None = Field(default=None, description="Additional context")
    options: list[str] | None = Field(default=None, description="Suggested options")


class HITLStatusResponse(BaseModel):
    """Response model for HITL status check."""

    thread_id: str = Field(description="Thread ID")
    has_pending_hitl: bool = Field(description="Whether there's a pending HITL request")
    status: str = Field(description="Thread status: idle, busy, interrupted, error")
    clarification: HITLClarificationDetails | None = Field(default=None, description="Clarification details if pending")
    checkpoint_id: str | None = Field(default=None, description="Current checkpoint ID")
    timestamp: str = Field(description="Response timestamp")


class HITLResponseRequest(BaseModel):
    """Request model for submitting HITL response."""

    response: str = Field(description="User's response to the clarification")
    tool_call_id: str | None = Field(default=None, description="Optional: specific tool call ID to respond to")
    as_node: str = Field(default="__end__", description="Node identity for the update")


class HITLResponseResult(BaseModel):
    """Result of HITL response submission."""

    success: bool = Field(description="Whether the response was accepted")
    thread_id: str = Field(description="Thread ID")
    message: str = Field(description="Status message")
    checkpoint_id: str | None = Field(default=None, description="New checkpoint ID after response")
    timestamp: str = Field(description="Response timestamp")


class HITLPendingItem(BaseModel):
    """A pending HITL request."""

    thread_id: str = Field(description="Thread ID")
    checkpoint_id: str | None = Field(description="Checkpoint ID")
    status: str = Field(description="Thread status")
    clarification: HITLClarificationDetails = Field(description="Clarification details")
    created_at: str | None = Field(default=None, description="When the HITL was created")


class HITLPendingListResponse(BaseModel):
    """Response model for listing pending HITL requests."""

    pending: list[HITLPendingItem] = Field(description="List of pending HITL requests")
    total: int = Field(description="Total count")


class HITLBulkStatusRequest(BaseModel):
    """Request model for checking HITL status of multiple threads."""

    thread_ids: list[str] = Field(description="List of thread IDs to check")


class HITLBulkStatusResponse(BaseModel):
    """Response model for bulk HITL status check."""

    results: dict[str, HITLStatusResponse] = Field(description="Status for each thread")
    pending_count: int = Field(description="Number of threads with pending HITL")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_clarification_from_messages(messages: list) -> HITLClarificationDetails | None:
    """Extract clarification details from message list.

    Looks for ToolMessage with ask_clarification that doesn't have a response yet.
    """
    if not messages:
        return None

    # Look for the most recent ask_clarification tool message
    for msg in reversed(messages):
        msg_type = getattr(msg, "type", None) or msg.get("type", None)
        if msg_type == "tool":
            name = getattr(msg, "name", None) or msg.get("name", None)
            if name == "ask_clarification":
                content = getattr(msg, "content", None) or msg.get("content", "")
                tool_call_id = getattr(msg, "tool_call_id", None) or msg.get("tool_call_id", "")

                # Parse the formatted message to extract details
                # The content is formatted by ClarificationMiddleware
                lines = content.split("\n") if content else []

                # Extract question (first line after icon)
                question = ""
                clarification_type = "missing_info"  # default
                context = None
                options = []

                if lines:
                    first_line = lines[0].strip()
                    # Remove icon prefix
                    for icon in ["❓", "🤔", "🔀", "⚠️", "💡"]:
                        if first_line.startswith(icon):
                            first_line = first_line[len(icon):].strip()
                            break

                    # Check if this is context + question format
                    if len(lines) > 1 and lines[1].strip().startswith("("):
                        context = first_line
                        question = lines[1].strip()
                    else:
                        question = first_line

                    # Extract options
                    for line in lines:
                        stripped = line.strip()
                        if stripped.startswith(("1.", "2.", "3.", "4.", "5.")):
                            option = stripped[2:].strip()
                            if option:
                                options.append(option)

                return HITLClarificationDetails(
                    tool_call_id=tool_call_id,
                    question=question or "Clarification requested",
                    clarification_type=clarification_type,
                    context=context,
                    options=options if options else None,
                )

    return None


def _is_waiting_for_hitl(checkpoint_tuple) -> bool:
    """Check if the thread is waiting for HITL response."""
    if checkpoint_tuple is None:
        return False

    # Check for tasks (interrupted state)
    tasks = getattr(checkpoint_tuple, "tasks", None)
    if tasks:
        return True

    # Check channel values for ask_clarification tool message without response
    checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
    channel_values = checkpoint.get("channel_values", {})
    messages = channel_values.get("messages", [])

    # Look for pending ask_clarification
    for msg in reversed(messages):
        msg_type = getattr(msg, "type", None) or msg.get("type", None)
        if msg_type == "tool":
            name = getattr(msg, "name", None) or msg.get("name", None)
            if name == "ask_clarification":
                # Check if there's a response after this
                msg_index = messages.index(msg) if msg in messages else -1
                if msg_index >= 0:
                    # Check subsequent messages
                    for subsequent in messages[msg_index + 1:]:
                        sub_type = getattr(subsequent, "type", None) or subsequent.get("type", None)
                        # If we see a human message or another AI message, it's been responded to
                        if sub_type in ["human", "ai"]:
                            return False
                return True

    return False


def _derive_thread_status(checkpoint_tuple) -> str:
    """Derive thread status from checkpoint metadata."""
    if checkpoint_tuple is None:
        return "idle"

    # Check for error in pending writes
    pending_writes = getattr(checkpoint_tuple, "pending_writes", None) or []
    for pw in pending_writes:
        if len(pw) >= 2 and pw[1] == "__error__":
            return "error"

    # Check for pending next tasks (indicates interrupt)
    tasks = getattr(checkpoint_tuple, "tasks", None)
    if tasks:
        return "interrupted"

    return "idle"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/threads/{thread_id}/status", response_model=HITLStatusResponse)
async def get_hitl_status(thread_id: str, request: Request) -> HITLStatusResponse:
    """Get HITL status for a specific thread.

    Returns whether the thread has a pending HITL request and clarification details.
    """
    checkpointer = get_checkpointer(request)

    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    try:
        checkpoint_tuple = await checkpointer.aget_tuple(config)
    except Exception:
        logger.exception("Failed to get state for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to get thread state")

    if checkpoint_tuple is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
    channel_values = checkpoint.get("channel_values", {})
    messages = channel_values.get("messages", [])

    has_pending = _is_waiting_for_hitl(checkpoint_tuple)
    status = _derive_thread_status(checkpoint_tuple)

    clarification = None
    if has_pending:
        clarification = _extract_clarification_from_messages(messages)

    ckpt_config = getattr(checkpoint_tuple, "config", {})
    checkpoint_id = ckpt_config.get("configurable", {}).get("checkpoint_id") if ckpt_config else None

    return HITLStatusResponse(
        thread_id=thread_id,
        has_pending_hitl=has_pending,
        status=status,
        clarification=clarification,
        checkpoint_id=checkpoint_id,
        timestamp=str(time.time()),
    )


@router.post("/threads/{thread_id}/respond", response_model=HITLResponseResult)
async def submit_hitl_response(
    thread_id: str, body: HITLResponseRequest, request: Request
) -> HITLResponseResult:
    """Submit a response to a pending HITL request.

    This resumes the thread execution with the user's response.
    """
    checkpointer = get_checkpointer(request)

    # First check if there's a pending HITL
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    try:
        checkpoint_tuple = await checkpointer.aget_tuple(config)
    except Exception:
        logger.exception("Failed to get state for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to get thread state")

    if checkpoint_tuple is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    if not _is_waiting_for_hitl(checkpoint_tuple):
        return HITLResponseResult(
            success=False,
            thread_id=thread_id,
            message="No pending HITL request for this thread",
            timestamp=str(time.time()),
        )

    # Prepare the response message
    checkpoint = dict(getattr(checkpoint_tuple, "checkpoint", {}) or {})
    metadata = dict(getattr(checkpoint_tuple, "metadata", {}) or {})
    channel_values = dict(checkpoint.get("channel_values", {}))
    messages = list(channel_values.get("messages", []))

    # Create a ToolMessage response for the ask_clarification tool
    from langchain_core.messages import HumanMessage, ToolMessage

    # Find the tool_call_id for ask_clarification
    tool_call_id = body.tool_call_id
    if not tool_call_id:
        clarification = _extract_clarification_from_messages(messages)
        if clarification:
            tool_call_id = clarification.tool_call_id

    # Add the user's response as a HumanMessage
    response_msg = HumanMessage(content=body.response)
    messages.append(response_msg)

    # Add a ToolMessage to indicate the clarification was answered
    if tool_call_id:
        tool_response = ToolMessage(
            content=f"User responded: {body.response}",
            tool_call_id=tool_call_id,
            name="ask_clarification",
        )
        messages.append(tool_response)

    channel_values["messages"] = messages
    checkpoint["channel_values"] = channel_values
    metadata["updated_at"] = time.time()

    # Write the updated checkpoint
    write_config = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_ns": "",
        }
    }
    try:
        new_config = await checkpointer.aput(write_config, checkpoint, metadata, {})
    except Exception:
        logger.exception("Failed to submit HITL response for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to submit response")

    new_checkpoint_id = None
    if isinstance(new_config, dict):
        new_checkpoint_id = new_config.get("configurable", {}).get("checkpoint_id")

    return HITLResponseResult(
        success=True,
        thread_id=thread_id,
        message="HITL response submitted successfully",
        checkpoint_id=new_checkpoint_id,
        timestamp=str(time.time()),
    )


@router.post("/threads/bulk-status", response_model=HITLBulkStatusResponse)
async def get_bulk_hitl_status(body: HITLBulkStatusRequest, request: Request) -> HITLBulkStatusResponse:
    """Get HITL status for multiple threads at once."""
    results = {}
    pending_count = 0

    for thread_id in body.thread_ids:
        try:
            # Reuse the single status logic
            checkpointer = get_checkpointer(request)
            config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
            checkpoint_tuple = await checkpointer.aget_tuple(config)

            if checkpoint_tuple is None:
                results[thread_id] = HITLStatusResponse(
                    thread_id=thread_id,
                    has_pending_hitl=False,
                    status="not_found",
                    timestamp=str(time.time()),
                )
                continue

            checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
            channel_values = checkpoint.get("channel_values", {})
            messages = channel_values.get("messages", [])

            has_pending = _is_waiting_for_hitl(checkpoint_tuple)
            status = _derive_thread_status(checkpoint_tuple)

            clarification = None
            if has_pending:
                clarification = _extract_clarification_from_messages(messages)
                pending_count += 1

            ckpt_config = getattr(checkpoint_tuple, "config", {})
            checkpoint_id = ckpt_config.get("configurable", {}).get("checkpoint_id") if ckpt_config else None

            results[thread_id] = HITLStatusResponse(
                thread_id=thread_id,
                has_pending_hitl=has_pending,
                status=status,
                clarification=clarification,
                checkpoint_id=checkpoint_id,
                timestamp=str(time.time()),
            )
        except Exception as e:
            results[thread_id] = HITLStatusResponse(
                thread_id=thread_id,
                has_pending_hitl=False,
                status="error",
                timestamp=str(time.time()),
            )

    return HITLBulkStatusResponse(
        results=results,
        pending_count=pending_count,
    )


@router.get("/pending", response_model=HITLPendingListResponse)
async def list_pending_hitl(
    request: Request,
    limit: int = 100,
    offset: int = 0,
) -> HITLPendingListResponse:
    """List all threads with pending HITL requests.

    This endpoint scans threads to find those waiting for human input.
    """
    checkpointer = get_checkpointer(request)
    pending_items = []

    try:
        # List all checkpoints
        async for checkpoint_tuple in checkpointer.alist(None):
            cfg = getattr(checkpoint_tuple, "config", {})
            thread_id = cfg.get("configurable", {}).get("thread_id")

            if not thread_id:
                continue

            # Skip sub-graph checkpoints
            if cfg.get("configurable", {}).get("checkpoint_ns", ""):
                continue

            if _is_waiting_for_hitl(checkpoint_tuple):
                checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
                channel_values = checkpoint.get("channel_values", {})
                messages = channel_values.get("messages", [])

                clarification = _extract_clarification_from_messages(messages)
                if clarification:
                    status = _derive_thread_status(checkpoint_tuple)
                    metadata = getattr(checkpoint_tuple, "metadata", {}) or {}
                    checkpoint_id = cfg.get("configurable", {}).get("checkpoint_id")

                    pending_items.append(
                        HITLPendingItem(
                            thread_id=thread_id,
                            checkpoint_id=checkpoint_id,
                            status=status,
                            clarification=clarification,
                            created_at=str(metadata.get("created_at", "")),
                        )
                    )

            if len(pending_items) >= limit + offset:
                break

    except Exception:
        logger.exception("Failed to list pending HITL requests")
        raise HTTPException(status_code=500, detail="Failed to list pending HITL requests")

    total = len(pending_items)
    pending_items = pending_items[offset : offset + limit]

    return HITLPendingListResponse(
        pending=pending_items,
        total=total,
    )

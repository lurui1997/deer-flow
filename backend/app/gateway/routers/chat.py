"""High-level Chat API for LLM interaction with session continuity and HITL support.

Provides a simplified, OpenAI-style chat interface on top of the
LangGraph-compatible run system. Supports:

1. Single-turn and multi-turn conversations via ``thread_id``
2. Streaming (SSE) and blocking response modes
3. HITL (Human-in-the-Loop) interruption detection and resumption
4. Conversation history retrieval

All endpoints are fully documented in Swagger/OpenAPI at ``/docs``.

Example usage::

    # Start a conversation
    POST /api/chat/completions
    {"message": "Hello"}
    -> {"thread_id": "thread-1", "choices": [...], "hitl_pending": false}

    # Continue the conversation
    POST /api/chat/completions
    {"message": "Tell me more", "thread_id": "thread-1"}

    # Check HITL status
    GET /api/chat/threads/thread-1/hitl-status
    -> {"has_pending_hitl": true, "question": "Which language?"}

    # Respond to HITL
    POST /api/chat/threads/thread-1/hitl-respond
    {"response": "Python"}
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, ToolMessage
from pydantic import BaseModel, Field

from app.gateway.deps import get_checkpointer, get_stream_bridge
from app.gateway.routers.thread_runs import RunCreateRequest
from app.gateway.services import format_sse, start_run
from deerflow.runtime import serialize_channel_values
from deerflow.runtime.stream_bridge import END_SENTINEL, HEARTBEAT_SENTINEL

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    """A single message in the conversation."""

    role: Literal["user", "assistant", "system", "tool"] = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    tool_call_id: str | None = Field(default=None, description="Tool call ID (for tool messages)")


class ChatRequest(BaseModel):
    """Request body for a chat completion."""

    message: str = Field(..., description="User message to send")
    thread_id: str | None = Field(
        default=None, description="Thread ID for conversation continuity. Auto-generated if omitted."
    )
    model: str | None = Field(default=None, description="Model name. Uses system default if omitted.")
    system_prompt: str | None = Field(default=None, description="Optional system prompt override")
    thinking_enabled: bool = Field(default=True, description="Enable model thinking mode")
    stream: bool = Field(default=False, description="Whether to stream the response via SSE")
    temperature: float | None = Field(default=None, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int | None = Field(default=None, ge=1, description="Maximum tokens to generate")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ChatChoice(BaseModel):
    """A single chat completion choice."""

    index: int = Field(default=0, description="Choice index")
    message: ChatMessage = Field(..., description="The generated message")
    finish_reason: str | None = Field(default=None, description="Why generation stopped")


class ChatUsage(BaseModel):
    """Token usage information."""

    prompt_tokens: int = Field(default=0, description="Input tokens")
    completion_tokens: int = Field(default=0, description="Output tokens")
    total_tokens: int = Field(default=0, description="Total tokens")


class ChatResponse(BaseModel):
    """Response model for non-streaming chat completion."""

    thread_id: str = Field(..., description="Thread ID for this conversation")
    run_id: str | None = Field(default=None, description="Run ID")
    choices: list[ChatChoice] = Field(default_factory=list, description="Generated responses")
    usage: ChatUsage = Field(default_factory=ChatUsage, description="Token usage")
    created_at: str = Field(default="", description="Response timestamp")
    hitl_pending: bool = Field(default=False, description="Whether thread is waiting for HITL input")


class ChatStreamChunk(BaseModel):
    """A single chunk in the SSE stream."""

    thread_id: str = Field(..., description="Thread ID")
    run_id: str | None = Field(default=None, description="Run ID")
    delta: str = Field(default="", description="Text delta")
    finish_reason: str | None = Field(default=None, description="Stream finish reason")
    usage: ChatUsage | None = Field(default=None, description="Final usage (only on last chunk)")


class HITLStatusResponse(BaseModel):
    """HITL status for a conversation thread."""

    thread_id: str = Field(..., description="Thread ID")
    has_pending_hitl: bool = Field(..., description="Whether a pending HITL request exists")
    status: str = Field(..., description="Thread status: idle, busy, interrupted, error")
    question: str | None = Field(default=None, description="Clarification question if pending")
    context: str | None = Field(default=None, description="Additional context")
    options: list[str] | None = Field(default=None, description="Suggested options")
    tool_call_id: str | None = Field(default=None, description="Associated tool call ID")
    checkpoint_id: str | None = Field(default=None, description="Current checkpoint ID")
    timestamp: str = Field(..., description="Response timestamp")


class HITLRespondRequest(BaseModel):
    """Request to respond to a pending HITL."""

    response: str = Field(..., description="User's response to the clarification")
    tool_call_id: str | None = Field(default=None, description="Optional specific tool call ID")


class HITLRespondResponse(BaseModel):
    """Response after submitting HITL input."""

    success: bool = Field(..., description="Whether the response was accepted")
    thread_id: str = Field(..., description="Thread ID")
    message: str = Field(..., description="Status message")
    run_id: str | None = Field(default=None, description="New run ID if execution resumed")
    timestamp: str = Field(..., description="Response timestamp")


class ConversationHistoryResponse(BaseModel):
    """Conversation history for a thread."""

    thread_id: str = Field(..., description="Thread ID")
    messages: list[ChatMessage] = Field(default_factory=list, description="Conversation messages")
    title: str | None = Field(default=None, description="Conversation title")
    total_messages: int = Field(default=0, description="Total message count")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_run_request(body: ChatRequest, thread_id: str) -> RunCreateRequest:
    """Convert ChatRequest to internal RunCreateRequest."""
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    if body.model:
        config["configurable"]["model_name"] = body.model
    if body.thinking_enabled is not None:
        config["configurable"]["thinking_enabled"] = body.thinking_enabled
    if body.temperature is not None:
        config["configurable"]["temperature"] = body.temperature
    if body.max_tokens is not None:
        config["configurable"]["max_tokens"] = body.max_tokens

    input_data: dict[str, Any] = {"messages": [{"role": "user", "content": body.message}]}
    if body.system_prompt:
        input_data["messages"].insert(0, {"role": "system", "content": body.system_prompt})

    return RunCreateRequest(
        input=input_data,
        config=config,
        metadata=body.metadata,
        stream_mode=["values", "messages"] if body.stream else ["values"],
        multitask_strategy="reject",
        on_disconnect="cancel",
    )


def _extract_ai_text(channel_values: dict[str, Any]) -> str:
    """Extract the latest AI message text from channel values."""
    messages = channel_values.get("messages", [])
    for msg in reversed(messages):
        msg_type = getattr(msg, "type", None) or msg.get("type", None)
        if msg_type in ("ai", "assistant"):
            content = getattr(msg, "content", None) or msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                texts = [
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                ]
                return "\n".join(texts)
    return ""


def _extract_usage(channel_values: dict[str, Any]) -> ChatUsage:
    """Extract token usage from the latest AI message."""
    messages = channel_values.get("messages", [])
    for msg in reversed(messages):
        msg_type = getattr(msg, "type", None) or msg.get("type", None)
        if msg_type in ("ai", "assistant"):
            usage = getattr(msg, "usage_metadata", None)
            if usage:
                return ChatUsage(
                    prompt_tokens=usage.get("input_tokens", 0),
                    completion_tokens=usage.get("output_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                )
    return ChatUsage()


def _is_hitl_pending(checkpoint_tuple) -> bool:
    """Check if thread is waiting for HITL response."""
    if checkpoint_tuple is None:
        return False
    tasks = getattr(checkpoint_tuple, "tasks", None)
    if tasks:
        return True
    checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
    channel_values = checkpoint.get("channel_values", {})
    messages = channel_values.get("messages", [])
    for msg in reversed(messages):
        msg_type = getattr(msg, "type", None) or msg.get("type", None)
        if msg_type == "tool":
            name = getattr(msg, "name", None) or msg.get("name", None)
            if name == "ask_clarification":
                msg_index = messages.index(msg) if msg in messages else -1
                if msg_index >= 0:
                    for subsequent in messages[msg_index + 1 :]:
                        sub_type = getattr(subsequent, "type", None) or subsequent.get("type", None)
                        if sub_type in ("human", "ai"):
                            return False
                return True
    return False


def _extract_hitl_details(checkpoint_tuple) -> dict[str, Any] | None:
    """Extract HITL clarification details from checkpoint."""
    if checkpoint_tuple is None:
        return None
    checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
    channel_values = checkpoint.get("channel_values", {})
    messages = channel_values.get("messages", [])
    for msg in reversed(messages):
        msg_type = getattr(msg, "type", None) or msg.get("type", None)
        if msg_type == "tool":
            name = getattr(msg, "name", None) or msg.get("name", None)
            if name == "ask_clarification":
                content = getattr(msg, "content", "") or msg.get("content", "")
                tool_call_id = getattr(msg, "tool_call_id", "") or msg.get("tool_call_id", "")
                lines = content.split("\n") if content else []
                question = ""
                context_str = None
                options: list[str] = []
                if lines:
                    first_line = lines[0].strip()
                    for icon in ["❓", "🤔", "🔀", "⚠️", "💡"]:
                        if first_line.startswith(icon):
                            first_line = first_line[len(icon) :].strip()
                            break
                    if len(lines) > 1 and lines[1].strip().startswith("("):
                        context_str = first_line
                        question = lines[1].strip()
                    else:
                        question = first_line
                    for line in lines:
                        stripped = line.strip()
                        if stripped.startswith(("1.", "2.", "3.", "4.", "5.")):
                            option = stripped[2:].strip()
                            if option:
                                options.append(option)
                return {
                    "question": question or "Clarification requested",
                    "context": context_str,
                    "options": options if options else None,
                    "tool_call_id": tool_call_id,
                }
    return None


def _serialize_messages(channel_values: dict[str, Any]) -> list[ChatMessage]:
    """Serialize checkpoint messages to ChatMessage list."""
    result: list[ChatMessage] = []
    messages = channel_values.get("messages", [])
    for msg in messages:
        msg_type = getattr(msg, "type", None) or msg.get("type", None)
        content = getattr(msg, "content", "") or msg.get("content", "")
        if isinstance(content, list):
            texts = [
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            ]
            content = "\n".join(texts)
        role: Literal["user", "assistant", "system", "tool"] = "user"
        if msg_type in ("human", "user"):
            role = "user"
        elif msg_type in ("ai", "assistant"):
            role = "assistant"
        elif msg_type == "system":
            role = "system"
        elif msg_type == "tool":
            role = "tool"
        tool_call_id = None
        if msg_type == "tool":
            tool_call_id = getattr(msg, "tool_call_id", None) or msg.get("tool_call_id", None)
        result.append(ChatMessage(role=role, content=str(content), tool_call_id=tool_call_id))
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/completions",
    response_model=ChatResponse,
    summary="Chat Completion",
    description="Send a message and get a complete response. Use thread_id to continue a conversation.",
)
async def chat_completion(body: ChatRequest, request: Request) -> ChatResponse:
    """Non-streaming chat completion.

    Creates a run on the given thread (or a new one) and blocks until completion,
    returning the final AI response text.

    **HITL Handling**: If the agent interrupts for clarification, the response
    will have ``hitl_pending=true``. Poll ``GET /api/chat/threads/{thread_id}/hitl-status``
    or submit a response via ``POST /api/chat/threads/{thread_id}/hitl-respond``.
    """
    thread_id = body.thread_id or str(uuid.uuid4())
    run_req = _build_run_request(body, thread_id)
    record = await start_run(run_req, thread_id, request)

    if record.task is not None:
        try:
            await record.task
        except asyncio.CancelledError:
            pass

    checkpointer = get_checkpointer(request)
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    try:
        checkpoint_tuple = await checkpointer.aget_tuple(config)
    except Exception:
        logger.exception("Failed to fetch state for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to fetch thread state")

    if checkpoint_tuple is None:
        return ChatResponse(
            thread_id=thread_id,
            run_id=record.run_id,
            choices=[ChatChoice(message=ChatMessage(role="assistant", content=""))],
            created_at=str(time.time()),
        )

    checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
    channel_values = checkpoint.get("channel_values", {})
    text = _extract_ai_text(channel_values)
    usage = _extract_usage(channel_values)
    hitl_pending = _is_hitl_pending(checkpoint_tuple)

    return ChatResponse(
        thread_id=thread_id,
        run_id=record.run_id,
        choices=[
            ChatChoice(
                index=0,
                message=ChatMessage(role="assistant", content=text),
                finish_reason="stop" if not hitl_pending else "hitl",
            )
        ],
        usage=usage,
        created_at=str(time.time()),
        hitl_pending=hitl_pending,
    )


@router.post(
    "/completions/stream",
    summary="Streaming Chat Completion",
    description="Send a message and receive the response as an SSE stream.",
)
async def chat_completion_stream(body: ChatRequest, request: Request) -> StreamingResponse:
    """Streaming chat completion via Server-Sent Events.

    The SSE stream yields JSON-encoded ChatStreamChunk objects:

    - ``delta`` carries incremental text as it is generated.
    - ``finish_reason`` is set on the final chunk.
    - ``usage`` is included on the final chunk when available.

    **HITL Handling**: When the agent interrupts, the stream ends with
    ``finish_reason="hitl"``. Use the HITL status/respond endpoints to resume.
    """
    thread_id = body.thread_id or str(uuid.uuid4())
    run_req = _build_run_request(body, thread_id)
    run_req.stream_mode = ["values", "messages"]
    bridge = get_stream_bridge(request)
    record = await start_run(run_req, thread_id, request)

    async def _chat_stream():
        last_event_id = request.headers.get("Last-Event-ID")
        buffer = ""
        run_id = record.run_id
        try:
            async for entry in bridge.subscribe(record.run_id, last_event_id=last_event_id):
                if await request.is_disconnected():
                    break
                if entry is HEARTBEAT_SENTINEL:
                    yield ": heartbeat\n\n"
                    continue
                if entry is END_SENTINEL:
                    chunk = ChatStreamChunk(
                        thread_id=thread_id, run_id=run_id, delta=buffer, finish_reason="stop"
                    )
                    yield format_sse("message", chunk.model_dump())
                    yield format_sse("done", {"done": True})
                    return
                if entry.event == "messages":
                    msg_data = entry.data
                    if isinstance(msg_data, (list, tuple)) and len(msg_data) >= 2:
                        msg_chunk = msg_data[0]
                    else:
                        msg_chunk = msg_data
                    if isinstance(msg_chunk, dict):
                        msg_type = msg_chunk.get("type")
                        text = msg_chunk.get("content", "")
                    else:
                        msg_type = getattr(msg_chunk, "type", None)
                        text = getattr(msg_chunk, "content", "")
                    if msg_type in ("ai", "assistant", "AIMessage", "AIMessageChunk"):
                        if isinstance(text, str) and text:
                            delta = text[len(buffer) :] if text.startswith(buffer) else text
                            if delta:
                                buffer += text
                                chunk = ChatStreamChunk(
                                    thread_id=thread_id, run_id=run_id, delta=delta
                                )
                                yield format_sse("message", chunk.model_dump())
                elif entry.event == "error":
                    chunk = ChatStreamChunk(
                        thread_id=thread_id, run_id=run_id, delta="", finish_reason="error"
                    )
                    yield format_sse("message", chunk.model_dump())
                    yield format_sse("done", {"done": True})
                    return
            chunk = ChatStreamChunk(
                thread_id=thread_id, run_id=run_id, delta="", finish_reason="stop"
            )
            yield format_sse("message", chunk.model_dump())
            yield format_sse("done", {"done": True})
        except asyncio.CancelledError:
            chunk = ChatStreamChunk(
                thread_id=thread_id, run_id=run_id, delta="", finish_reason="cancelled"
            )
            yield format_sse("message", chunk.model_dump())
            yield format_sse("done", {"done": True})

    return StreamingResponse(
        _chat_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Location": f"/api/chat/threads/{thread_id}/runs/{record.run_id}",
        },
    )


@router.get(
    "/threads/{thread_id}/hitl-status",
    response_model=HITLStatusResponse,
    summary="Get HITL Status",
    description="Check whether a conversation thread is waiting for human input.",
)
async def get_hitl_status(thread_id: str, request: Request) -> HITLStatusResponse:
    """Get HITL status for a conversation thread."""
    checkpointer = get_checkpointer(request)
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    try:
        checkpoint_tuple = await checkpointer.aget_tuple(config)
    except Exception:
        logger.exception("Failed to get state for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to get thread state")

    if checkpoint_tuple is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    has_pending = _is_hitl_pending(checkpoint_tuple)
    details = _extract_hitl_details(checkpoint_tuple) if has_pending else None
    pending_writes = getattr(checkpoint_tuple, "pending_writes", None) or []
    status = "idle"
    for pw in pending_writes:
        if len(pw) >= 2 and pw[1] == "__error__":
            status = "error"
            break
    tasks = getattr(checkpoint_tuple, "tasks", None)
    if tasks:
        status = "interrupted"

    ckpt_config = getattr(checkpoint_tuple, "config", {})
    checkpoint_id = ckpt_config.get("configurable", {}).get("checkpoint_id") if ckpt_config else None

    return HITLStatusResponse(
        thread_id=thread_id,
        has_pending_hitl=has_pending,
        status=status,
        question=details.get("question") if details else None,
        context=details.get("context") if details else None,
        options=details.get("options") if details else None,
        tool_call_id=details.get("tool_call_id") if details else None,
        checkpoint_id=checkpoint_id,
        timestamp=str(time.time()),
    )


@router.post(
    "/threads/{thread_id}/hitl-respond",
    response_model=HITLRespondResponse,
    summary="Respond to HITL",
    description="Submit a human response to a pending clarification and resume execution.",
)
async def hitl_respond(
    thread_id: str, body: HITLRespondRequest, request: Request
) -> HITLRespondResponse:
    """Respond to a pending HITL request and resume the conversation."""
    checkpointer = get_checkpointer(request)
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    try:
        checkpoint_tuple = await checkpointer.aget_tuple(config)
    except Exception:
        logger.exception("Failed to get state for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to get thread state")

    if checkpoint_tuple is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    if not _is_hitl_pending(checkpoint_tuple):
        return HITLRespondResponse(
            success=False,
            thread_id=thread_id,
            message="No pending HITL request for this thread",
            timestamp=str(time.time()),
        )

    checkpoint = dict(getattr(checkpoint_tuple, "checkpoint", {}) or {})
    metadata = dict(getattr(checkpoint_tuple, "metadata", {}) or {})
    channel_values = dict(checkpoint.get("channel_values", {}))
    messages = list(channel_values.get("messages", []))

    tool_call_id = body.tool_call_id
    if not tool_call_id:
        details = _extract_hitl_details(checkpoint_tuple)
        if details:
            tool_call_id = details.get("tool_call_id", "")

    response_msg = HumanMessage(content=body.response)
    messages.append(response_msg)
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

    write_config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    try:
        new_config = await checkpointer.aput(write_config, checkpoint, metadata, {})
    except Exception:
        logger.exception("Failed to submit HITL response for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to submit response")

    # Trigger a new run to resume execution
    run_req = RunCreateRequest(
        input={"messages": []},
        config={"configurable": {"thread_id": thread_id}},
        stream_mode=["values"],
        multitask_strategy="reject",
        on_disconnect="cancel",
    )
    run_record = await start_run(run_req, thread_id, request)

    new_checkpoint_id = None
    if isinstance(new_config, dict):
        new_checkpoint_id = new_config.get("configurable", {}).get("checkpoint_id")

    return HITLRespondResponse(
        success=True,
        thread_id=thread_id,
        message="HITL response submitted and execution resumed",
        run_id=run_record.run_id,
        timestamp=str(time.time()),
    )


@router.get(
    "/threads/{thread_id}/history",
    response_model=ConversationHistoryResponse,
    summary="Get Conversation History",
    description="Retrieve the full message history for a conversation thread.",
)
async def get_conversation_history(thread_id: str, request: Request) -> ConversationHistoryResponse:
    """Get the conversation history for a thread.

    Returns all messages in chronological order, including user inputs,
    assistant responses, tool calls, and tool results.
    """
    checkpointer = get_checkpointer(request)
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    try:
        checkpoint_tuple = await checkpointer.aget_tuple(config)
    except Exception:
        logger.exception("Failed to get history for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to get conversation history")

    if checkpoint_tuple is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
    channel_values = checkpoint.get("channel_values", {})
    messages = _serialize_messages(channel_values)

    return ConversationHistoryResponse(
        thread_id=thread_id,
        messages=messages,
        title=channel_values.get("title"),
        total_messages=len(messages),
    )

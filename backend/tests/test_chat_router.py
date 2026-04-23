"""Tests for the Chat API router."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.routers import chat


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_checkpoint_tuple():
    """Create a mock checkpoint tuple with no HITL pending."""
    ckpt = MagicMock()
    ckpt.checkpoint = {"channel_values": {"messages": []}}
    ckpt.metadata = {}
    ckpt.config = {"configurable": {"thread_id": "test-thread", "checkpoint_id": "chk-1"}}
    ckpt.tasks = []
    ckpt.pending_writes = []
    ckpt.parent_config = None
    return ckpt


@pytest.fixture
def mock_hitl_checkpoint_tuple():
    """Create a mock checkpoint tuple with HITL pending."""
    tool_msg = MagicMock()
    tool_msg.type = "tool"
    tool_msg.name = "ask_clarification"
    tool_msg.content = "❓ 目标网站是什么？\n1. example.com\n2. other.com"
    tool_msg.tool_call_id = "call_123"

    ckpt = MagicMock()
    ckpt.checkpoint = {"channel_values": {"messages": [tool_msg]}}
    ckpt.metadata = {}
    ckpt.config = {"configurable": {"thread_id": "test-thread", "checkpoint_id": "chk-1"}}
    ckpt.tasks = [MagicMock()]  # Tasks present = interrupted
    ckpt.pending_writes = []
    ckpt.parent_config = None
    return ckpt


@pytest.fixture
def client(mock_checkpoint_tuple):
    """Create a TestClient with mocked dependencies."""
    app = FastAPI()
    app.include_router(chat.router)

    # Mock checkpointer (async methods need coroutine return values)
    import asyncio

    mock_cp = MagicMock()
    mock_cp.aget_tuple = MagicMock(
        return_value=asyncio.Future()
    )
    mock_cp.aget_tuple.return_value.set_result(mock_checkpoint_tuple)
    mock_cp.aput = MagicMock(return_value=asyncio.Future())
    mock_cp.aput.return_value.set_result({"configurable": {"checkpoint_id": "chk-2"}})

    # Mock stream bridge
    mock_bridge = MagicMock()
    mock_bridge.END_SENTINEL = object()
    mock_bridge.subscribe = MagicMock(return_value=async_gen([]))

    # Mock run manager
    mock_run_mgr = MagicMock()
    mock_record = MagicMock()
    mock_record.run_id = "run-1"
    mock_record.thread_id = "test-thread"
    mock_record.task = None
    mock_record.status.value = "success"
    mock_record.error = None
    mock_run_mgr.create_or_reject = MagicMock(return_value=mock_record)

    # Attach to app state
    app.state.checkpointer = mock_cp
    app.state.stream_bridge = mock_bridge
    app.state.run_manager = mock_run_mgr
    app.state.store = None

    with TestClient(app) as c:
        yield c


async def async_gen(items):
    """Helper to create an async generator from a list."""
    for item in items:
        yield item


# ---------------------------------------------------------------------------
# _is_hitl_pending tests
# ---------------------------------------------------------------------------


def test_is_hitl_pending_no_checkpoint():
    assert chat._is_hitl_pending(None) is False


def test_is_hitl_pending_no_messages(mock_checkpoint_tuple):
    assert chat._is_hitl_pending(mock_checkpoint_tuple) is False


def test_is_hitl_pending_with_tasks(mock_hitl_checkpoint_tuple):
    assert chat._is_hitl_pending(mock_hitl_checkpoint_tuple) is True


def test_is_hitl_pending_with_clarification_tool():
    tool_msg = MagicMock()
    tool_msg.type = "tool"
    tool_msg.name = "ask_clarification"
    tool_msg.content = "Question?"
    tool_msg.tool_call_id = "call_1"

    ckpt = MagicMock()
    ckpt.checkpoint = {"channel_values": {"messages": [tool_msg]}}
    ckpt.tasks = []

    assert chat._is_hitl_pending(ckpt) is True


def test_is_hitl_pending_after_human_response():
    tool_msg = MagicMock()
    tool_msg.type = "tool"
    tool_msg.name = "ask_clarification"
    tool_msg.content = "Question?"
    tool_msg.tool_call_id = "call_1"

    human_msg = MagicMock()
    human_msg.type = "human"

    ckpt = MagicMock()
    ckpt.checkpoint = {"channel_values": {"messages": [tool_msg, human_msg]}}
    ckpt.tasks = []

    assert chat._is_hitl_pending(ckpt) is False


# ---------------------------------------------------------------------------
# _extract_hitl_details tests
# ---------------------------------------------------------------------------


def test_extract_hitl_details_none():
    assert chat._extract_hitl_details(None) is None


def test_extract_hitl_details_with_options(mock_hitl_checkpoint_tuple):
    details = chat._extract_hitl_details(mock_hitl_checkpoint_tuple)
    assert details is not None
    assert "question" in details
    assert "options" in details
    assert details["tool_call_id"] == "call_123"


# ---------------------------------------------------------------------------
# _extract_ai_text tests
# ---------------------------------------------------------------------------


def test_extract_ai_text_empty():
    assert chat._extract_ai_text({}) == ""
    assert chat._extract_ai_text({"messages": []}) == ""


def test_extract_ai_text_from_ai_message():
    ai_msg = MagicMock()
    ai_msg.type = "ai"
    ai_msg.content = "Hello world"

    assert chat._extract_ai_text({"messages": [ai_msg]}) == "Hello world"


def test_extract_ai_text_from_dict_message():
    msg = {"type": "assistant", "content": "Dict response"}
    assert chat._extract_ai_text({"messages": [msg]}) == "Dict response"


# ---------------------------------------------------------------------------
# _serialize_messages tests
# ---------------------------------------------------------------------------


def test_serialize_messages_empty():
    assert chat._serialize_messages({}) == []
    assert chat._serialize_messages({"messages": []}) == []


def test_serialize_messages_roles():
    messages = [
        {"type": "human", "content": "Hi"},
        {"type": "ai", "content": "Hello"},
        {"type": "system", "content": "Sys"},
        {"type": "tool", "content": "Result", "tool_call_id": "tc1"},
    ]
    result = chat._serialize_messages({"messages": messages})
    assert len(result) == 4
    assert result[0].role == "user"
    assert result[1].role == "assistant"
    assert result[2].role == "system"
    assert result[3].role == "tool"
    assert result[3].tool_call_id == "tc1"


# ---------------------------------------------------------------------------
# _build_run_request tests
# ---------------------------------------------------------------------------


def test_build_run_request_basic():
    req = chat.ChatRequest(message="Hello")
    run_req = chat._build_run_request(req, "thread-1")
    assert run_req.input is not None
    assert run_req.config["configurable"]["thread_id"] == "thread-1"


def test_build_run_request_with_model():
    req = chat.ChatRequest(message="Hello", model="gpt-4o")
    run_req = chat._build_run_request(req, "thread-1")
    assert run_req.config["configurable"]["model_name"] == "gpt-4o"


def test_build_run_request_with_system_prompt():
    req = chat.ChatRequest(message="Hello", system_prompt="Be helpful")
    run_req = chat._build_run_request(req, "thread-1")
    messages = run_req.input["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "Be helpful"
    assert messages[1]["role"] == "user"


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------


def test_hitl_status_endpoint(client):
    response = client.get("/api/chat/threads/test-thread/hitl-status")
    assert response.status_code == 200
    data = response.json()
    assert data["thread_id"] == "test-thread"
    assert data["has_pending_hitl"] is False
    assert data["status"] == "idle"


def test_hitl_status_thread_not_found(client):
    # Override the mock to return None
    import asyncio

    mock_cp = client.app.state.checkpointer
    future = asyncio.Future()
    future.set_result(None)
    mock_cp.aget_tuple = MagicMock(return_value=future)

    response = client.get("/api/chat/threads/unknown-thread/hitl-status")
    assert response.status_code == 404


def test_conversation_history_endpoint(client):
    response = client.get("/api/chat/threads/test-thread/history")
    assert response.status_code == 200
    data = response.json()
    assert data["thread_id"] == "test-thread"
    assert "messages" in data


def test_hitl_respond_no_pending_hitl(client):
    response = client.post(
        "/api/chat/threads/test-thread/hitl-respond",
        json={"response": "Some answer"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "No pending HITL" in data["message"]


# ---------------------------------------------------------------------------
# ChatRequest validation tests
# ---------------------------------------------------------------------------


def test_chat_request_defaults():
    req = chat.ChatRequest(message="Hello")
    assert req.thread_id is None
    assert req.model is None
    assert req.thinking_enabled is True
    assert req.stream is False
    assert req.temperature is None
    assert req.max_tokens is None


def test_chat_request_temperature_bounds():
    with pytest.raises(ValueError):
        chat.ChatRequest(message="Hello", temperature=-0.1)

    with pytest.raises(ValueError):
        chat.ChatRequest(message="Hello", temperature=2.1)

    req = chat.ChatRequest(message="Hello", temperature=1.5)
    assert req.temperature == 1.5


def test_chat_request_max_tokens_bounds():
    with pytest.raises(ValueError):
        chat.ChatRequest(message="Hello", max_tokens=0)

    req = chat.ChatRequest(message="Hello", max_tokens=100)
    assert req.max_tokens == 100

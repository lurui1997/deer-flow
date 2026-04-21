"""WebSearchMiddleware - Observes web search tool calls.

Observability middleware for web search operations:
- Tracks search latency by provider
- Records result counts and quality
- Detects cache hits
- Supports multiple search providers
"""

from __future__ import annotations

import logging
import time
from typing import Any, override

from langchain.agents.middleware import AgentMiddleware
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from deerflow.agents.worker_state import WorkerState
from deerflow.observability.metrics import MetricsCollector
from deerflow.observability.pipeline import ObservabilityEvent, emit_event
from deerflow.observability.tracing import TracingMixin, generate_span_id, get_current_trace_context
from deerflow.observability.types import ObservabilityEventType, WebSearchRecord

logger = logging.getLogger(__name__)

# Search tool names by provider
_SEARCH_TOOLS = {
    "web_search": ["web_search", "search", "tavily_search", "ddg_search"],
    "web_fetch": ["web_fetch", "fetch", "tavily_fetch", "jina_fetch"],
    "image_search": ["image_search", "search_images"],
}

# Provider detection patterns
_PROVIDER_PATTERNS = {
    "tavily": ["tavily"],
    "ddg": ["ddg", "duckduckgo"],
    "exa": ["exa"],
    "firecrawl": ["firecrawl"],
    "jina": ["jina"],
}


class WebSearchMiddleware(AgentMiddleware[WorkerState], TracingMixin):
    """Observes web search tool calls.

    This middleware detects web search operations and records:
    - Search latency by provider
    - Result counts
    - Error rates
    - Cache hits
    """

    state_schema = WorkerState

    def __init__(
        self,
        search_tools: dict[str, list[str]] | None = None,
        emit_events: bool = True,
        record_metrics: bool = True,
    ):
        """Initialize WebSearchMiddleware.

        Args:
            search_tools: Mapping of search types to tool names.
            emit_events: Whether to emit observability events.
            record_metrics: Whether to record metrics.
        """
        super().__init__()
        self._search_tools = search_tools or _SEARCH_TOOLS
        self._emit_events = emit_events
        self._record_metrics = record_metrics

    def _is_search_tool(self, tool_name: str) -> tuple[bool, str]:
        """Check if tool is a search tool and return search type.

        Returns:
            Tuple of (is_search, search_type)
        """
        for search_type, tool_names in self._search_tools.items():
            if tool_name in tool_names:
                return True, search_type
        return False, ""

    def _detect_provider(self, tool_name: str, args: dict) -> str:
        """Detect search provider from tool name and arguments."""
        # Check tool name patterns
        for provider, patterns in _PROVIDER_PATTERNS.items():
            for pattern in patterns:
                if pattern in tool_name.lower():
                    return provider

        # Check args for provider hints
        provider_hint = args.get("provider") or args.get("engine")
        if provider_hint:
            return str(provider_hint).lower()

        return "unknown"

    def _extract_query(self, args: dict) -> str:
        """Extract search query from arguments."""
        query = args.get("query") or args.get("q") or args.get("url", "")
        return str(query)[:500]  # Limit query length

    def _count_results(self, result: Any) -> int:
        """Count search results from tool output."""
        if result is None:
            return 0

        if isinstance(result, list):
            return len(result)

        if isinstance(result, str):
            # Try to detect result count from text
            # Common patterns: "Found X results", "X results found"
            import re

            patterns = [
                r"(\d+)\s+results?\s+found",
                r"found\s+(\d+)\s+results?",
                r"(\d+)\s+matches?",
            ]
            for pattern in patterns:
                match = re.search(pattern, result.lower())
                if match:
                    return int(match.group(1))
            return 1 if result.strip() else 0

        if isinstance(result, dict):
            # Check common result fields
            for key in ["results", "items", "data", "matches"]:
                if key in result and isinstance(result[key], list):
                    return len(result[key])
            return 1

        return 0

    def _extract_top_result(self, result: Any) -> tuple[str | None, str | None]:
        """Extract top result title and URL."""
        if isinstance(result, list) and result:
            first = result[0]
            if isinstance(first, dict):
                title = first.get("title") or first.get("name", "")
                url = first.get("url") or first.get("link", "")
                return str(title)[:200] if title else None, str(url)[:500] if url else None

        if isinstance(result, dict):
            results = result.get("results") or result.get("items") or []
            if results and isinstance(results, list):
                first = results[0]
                if isinstance(first, dict):
                    title = first.get("title") or first.get("name", "")
                    url = first.get("url") or first.get("link", "")
                    return str(title)[:200] if title else None, str(url)[:500] if url else None

        return None, None

    def _create_record(self, request: ToolCallRequest) -> WebSearchRecord:
        """Create a web search record."""
        tool_name = str(request.tool_call.get("name", "unknown"))
        args = request.tool_call.get("args", {}) or {}

        return WebSearchRecord(
            search_id=generate_span_id(),
            provider=self._detect_provider(tool_name, args),
            query=self._extract_query(args),
            request_time=time.time(),
        )

    def _emit_search_event(self, record: WebSearchRecord, event_type: str) -> None:
        """Emit web search observability event."""
        if not self._emit_events:
            return

        trace_ctx = get_current_trace_context()
        event = ObservabilityEvent(
            event_type=event_type,
            timestamp=record.response_time or time.time(),
            trace_id=trace_ctx.trace_id if trace_ctx else None,
            span_id=trace_ctx.span_id if trace_ctx else None,
            payload={
                "provider": record.provider,
                "query": record.query,
                "latency_ms": record.latency_ms,
                "results_count": record.results_count,
                "status": record.status,
                "cache_hit": record.cache_hit,
            },
        )
        emit_event(event)

    def _record_metrics(self, record: WebSearchRecord) -> None:
        """Record web search metrics."""
        if not self._record_metrics:
            return

        latency_sec = (record.latency_ms or 0) / 1000.0
        MetricsCollector.record_web_search(
            provider=record.provider,
            latency_sec=latency_sec,
            status=record.status,
            results_count=record.results_count,
        )

    @override
    def wrap_tool_call(self, request: ToolCallRequest, handler):
        """Wrap search tool call with observation."""
        tool_name = str(request.tool_call.get("name", ""))
        is_search, _ = self._is_search_tool(tool_name)

        if not is_search:
            return handler(request)

        record = self._create_record(request)

        try:
            result = handler(request)
            record.status = "success"
            record.results_count = self._count_results(result)
            title, url = self._extract_top_result(result)
            record.top_result_title = title
            record.top_result_url = url
        except Exception as exc:
            record.status = "error"
            record.error_message = str(exc)
            logger.exception(
                "Web search failed: provider=%s query=%r",
                record.provider,
                record.query,
            )
            raise
        finally:
            record.response_time = time.time()
            record.latency_ms = int((record.response_time - record.request_time) * 1000)

            event_type = (
                ObservabilityEventType.WEB_SEARCH_COMPLETED
                if record.status == "success"
                else ObservabilityEventType.WEB_SEARCH_FAILED
            )
            self._emit_search_event(record, event_type)
            self._record_metrics(record)

        return result

    @override
    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        """Async version of wrap_tool_call."""
        tool_name = str(request.tool_call.get("name", ""))
        is_search, _ = self._is_search_tool(tool_name)

        if not is_search:
            return await handler(request)

        record = self._create_record(request)

        try:
            result = await handler(request)
            record.status = "success"
            record.results_count = self._count_results(result)
            title, url = self._extract_top_result(result)
            record.top_result_title = title
            record.top_result_url = url
        except Exception as exc:
            record.status = "error"
            record.error_message = str(exc)
            logger.exception(
                "Web search failed (async): provider=%s query=%r",
                record.provider,
                record.query,
            )
            raise
        finally:
            record.response_time = time.time()
            record.latency_ms = int((record.response_time - record.request_time) * 1000)

            event_type = (
                ObservabilityEventType.WEB_SEARCH_COMPLETED
                if record.status == "success"
                else ObservabilityEventType.WEB_SEARCH_FAILED
            )
            self._emit_search_event(record, event_type)
            self._record_metrics(record)

        return result

"""ARW Middleware implementations.

This package contains the middleware chain for Agent Runtime Worker,
including both core middlewares and observability middlewares.

Core Middlewares:
1. TaskContextMiddleware - Inject ARC task requirements
2. ThreadDataMiddleware - Create workspace directories
3. SkillLoaderMiddleware - Two-tier skill loading
4. OntologyContextMiddleware - Read ontology information
5. KnowledgeRetrievalMiddleware - RAG/MCP retrieval
6. SummarizationMiddleware - Context compaction
7. CheckpointMiddleware - Checkpoints and pre-run snapshots
8. HITLMiddleware - HITL platform bridging
9. EventReportMiddleware - Event reporting
10. GuardrailMiddleware - Output content guardrails

Observability Middlewares:
11. ThinkingMiddleware - Capture LLM thinking content
12. ToolTracingMiddleware - Full lifecycle tool call tracing
13. MCPTracingMiddleware - MCP tool call tracing
14. WebSearchMiddleware - Web search observation
"""

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
from deerflow.agents.middlewares.mcp_tracing_middleware import MCPTracingMiddleware
from deerflow.agents.middlewares.skill_loader_middleware import (
    SkillLoaderMiddleware,
    get_deferred_skill_registry,
    promote_deferred_skill,
)
from deerflow.agents.middlewares.task_context_middleware import (
    TaskContextMiddleware,
)
from deerflow.agents.middlewares.thinking_middleware import ThinkingMiddleware
from deerflow.agents.middlewares.tool_tracing_middleware import ToolTracingMiddleware
from deerflow.agents.middlewares.web_search_middleware import WebSearchMiddleware

__all__ = [
    # ARW Core Middleware
    "TaskContextMiddleware",
    "SkillLoaderMiddleware",
    "KnowledgeRetrievalMiddleware",
    "CheckpointMiddleware",
    "HITLMiddleware",
    "EventReportMiddleware",
    "GuardrailMiddleware",
    # Observability Middleware
    "ThinkingMiddleware",
    "ToolTracingMiddleware",
    "MCPTracingMiddleware",
    "WebSearchMiddleware",
    # Skill registry helpers
    "get_deferred_skill_registry",
    "promote_deferred_skill",
]

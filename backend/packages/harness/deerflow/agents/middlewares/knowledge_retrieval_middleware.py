"""KnowledgeRetrievalMiddleware - RAG/MCP 检索结果注入"知识区".

中间件 #5 in ARW middleware chain:
- RAG / MCP 检索结果注入"知识区"
- 知识区参与 Compact，优先保留
- 不可用时降级跳过

与 OntologyContextMiddleware + SummarizationMiddleware 协作，实现三层上下文模型:
- 常驻区: 任务目标描述 + 本体信息——永不被 Compact
- 知识区: RAG 检索结果 + Skill 包描述——参与 Compact，优先保留
- 工作区: 当前推理轮次的消息——达到 Token 预算 80% 时触发 Compact
"""

from __future__ import annotations

import logging
from typing import override

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

from deerflow.agents.worker_state import WorkerState

logger = logging.getLogger(__name__)


class KnowledgeRetrievalMiddleware(AgentMiddleware[WorkerState]):
    """Inject retrieved knowledge into WorkerState.

    This middleware performs RAG/MCP retrieval and injects results into the
    "knowledge zone" of WorkerState. The knowledge zone participates in
    context compaction but is prioritized for retention.

    Retrieval sources:
    - RAG (Retrieval-Augmented Generation): Vector DB search
    - MCP (Model Context Protocol): Dynamic tool/knowledge retrieval

    Degradation: If retrieval fails, logs warning and continues without
    blocking agent execution.
    """

    state_schema = WorkerState

    def __init__(
        self,
        enable_rag: bool = True,
        enable_mcp: bool = True,
        knowledge_sources: list[dict] | None = None,
        retrieval_timeout: float = 10.0,
    ):
        """Initialize KnowledgeRetrievalMiddleware.

        Args:
            enable_rag: Whether to enable RAG retrieval.
            enable_mcp: Whether to enable MCP retrieval.
            knowledge_sources: List of knowledge source configurations.
                Each dict should have: type (rag/mcp), config, priority.
            retrieval_timeout: Timeout for retrieval operations in seconds.
        """
        super().__init__()
        self._enable_rag = enable_rag
        self._enable_mcp = enable_mcp
        self._knowledge_sources = knowledge_sources or []
        self._retrieval_timeout = retrieval_timeout

    def _retrieve_rag_knowledge(
        self, query: str, task_context: dict | None
    ) -> list[dict]:
        """Retrieve knowledge from RAG sources.

        Args:
            query: The retrieval query (typically task description).
            task_context: Current task context for filtering.

        Returns:
            List of retrieved knowledge items.
        """
        if not self._enable_rag:
            return []

        results = []
        try:
            # TODO: Implement actual RAG retrieval
            # This should:
            # 1. Connect to vector database
            # 2. Perform similarity search with query
            # 3. Return top-k results with content and metadata
            logger.debug("RAG retrieval for query: %s", query)
        except Exception as e:
            logger.warning("RAG retrieval failed: %s", e)

        return results

    def _retrieve_mcp_knowledge(
        self, query: str, task_context: dict | None
    ) -> list[dict]:
        """Retrieve knowledge from MCP sources.

        Args:
            query: The retrieval query.
            task_context: Current task context for filtering.

        Returns:
            List of retrieved knowledge items.
        """
        if not self._enable_mcp:
            return []

        results = []
        try:
            # TODO: Implement actual MCP retrieval
            # This should:
            # 1. Connect to MCP servers
            # 2. Query for relevant context/tools
            # 3. Return results with content and metadata
            logger.debug("MCP retrieval for query: %s", query)
        except Exception as e:
            logger.warning("MCP retrieval failed: %s", e)

        return results

    def _format_knowledge(self, knowledge_items: list[dict]) -> list[dict]:
        """Format retrieved knowledge for injection into state.

        Args:
            knowledge_items: Raw knowledge items from retrieval.

        Returns:
            Formatted knowledge items ready for state.
        """
        formatted = []
        for item in knowledge_items:
            formatted_item = {
                "content": item.get("content", ""),
                "source": item.get("source", "unknown"),
                "source_type": item.get("source_type", "unknown"),
                "relevance_score": item.get("relevance_score", 0.0),
                "retrieved_at": item.get("retrieved_at"),
                "metadata": item.get("metadata", {}),
            }
            formatted.append(formatted_item)
        return formatted

    @override
    def before_agent(self, state: WorkerState, runtime: Runtime) -> dict | None:
        """Retrieve and inject knowledge before agent execution.

        Performs RAG and MCP retrieval based on task context, injects results
        into the knowledge zone of WorkerState.
        """
        task_context = state.get("task_context") or {}
        task_description = task_context.get("task_description", "")

        # Skip if no task description available
        if not task_description:
            logger.debug("No task description, skipping knowledge retrieval")
            return None

        # Retrieve from all enabled sources
        all_knowledge = []

        # RAG retrieval
        if self._enable_rag:
            rag_results = self._retrieve_rag_knowledge(
                task_description, task_context
            )
            all_knowledge.extend(rag_results)

        # MCP retrieval
        if self._enable_mcp:
            mcp_results = self._retrieve_mcp_knowledge(
                task_description, task_context
            )
            all_knowledge.extend(mcp_results)

        # Format and inject knowledge
        if all_knowledge:
            formatted_knowledge = self._format_knowledge(all_knowledge)
            logger.info(
                "KnowledgeRetrievalMiddleware: Retrieved %d knowledge items",
                len(formatted_knowledge),
            )
            return {"retrieved_knowledge": formatted_knowledge}

        logger.debug("No knowledge retrieved")
        return None

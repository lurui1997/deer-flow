"""SkillLoaderMiddleware - 声明式 Skill 体系与二级加载.

中间件 #3 in ARW middleware chain:
- 从 Skill 市场拉取资源
- 翻译初始化为 DeerFlow Skill 执行体系
- 支持二级加载策略（常驻 + 延迟）

Skill 二级加载策略:
- 一级（常驻）: Agent Spec 显式声明的 Skill，SKILL.md 注入 System Prompt，工具 schema 直接挂入 LLM tool list
- 二级（延迟）: Skill 市场内潜在可用的 Skill/MCP，仅注册名称+描述；LLM 通过内置 skill_search 工具按需拉取完整 schema
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import override

from langchain.agents.middleware import AgentMiddleware
from langgraph.config import get_config
from langgraph.runtime import Runtime

from deerflow.agents.worker_state import SkillInfo, SkillRegistryState, WorkerState

logger = logging.getLogger(__name__)

# ContextVar for concurrent isolation of deferred skill registry
_deferred_skill_registry: ContextVar[dict[str, SkillInfo]] = ContextVar(
    "deferred_skill_registry", default={}
)


class SkillLoaderMiddleware(AgentMiddleware[WorkerState]):
    """Load and manage skills with two-tier loading strategy.

    This middleware prepares skill resources from the skill marketplace and
    initializes them into the DeerFlow skill execution system.

    Two-tier loading:
    1. Resident (Tier-1): Explicitly declared skills in Agent Spec.
       Full schema loaded immediately, added to LLM tool list.
    2. Deferred (Tier-2): Potentially available skills in marketplace.
       Only name + description registered. LLM uses skill_search() to
       retrieve full schema on demand. Retrieved skills auto-promote to resident.

    Concurrent isolation via ContextVar prevents cross-request pollution.
    """

    state_schema = WorkerState

    def __init__(
        self,
        resident_skills: list[dict] | None = None,
        deferred_skills: list[dict] | None = None,
        skill_packages: list[str] | None = None,
        enable_deferred_loading: bool = True,
    ):
        """Initialize SkillLoaderMiddleware.

        Args:
            resident_skills: List of resident skill definitions (Tier-1).
                Each dict should have: name, description, schema (optional).
            deferred_skills: List of deferred skill definitions (Tier-2).
                Each dict should have: name, description.
            skill_packages: List of skill package paths to load.
            enable_deferred_loading: Whether to enable deferred (Tier-2) loading.
        """
        super().__init__()
        self._resident_skills = resident_skills or []
        self._deferred_skills = deferred_skills or []
        self._skill_packages = skill_packages or []
        self._enable_deferred_loading = enable_deferred_loading

    def _load_resident_skills(self) -> list[SkillInfo]:
        """Load resident (Tier-1) skills with full schema."""
        skills = []
        for skill_def in self._resident_skills:
            skill_info = SkillInfo(
                name=skill_def.get("name", ""),
                description=skill_def.get("description", ""),
                schema=skill_def.get("schema"),
            )
            skills.append(skill_info)
            logger.debug("Loaded resident skill: %s", skill_info["name"])
        return skills

    def _load_deferred_skills(self) -> list[SkillInfo]:
        """Load deferred (Tier-2) skills with name + description only."""
        if not self._enable_deferred_loading:
            return []

        skills = []
        for skill_def in self._deferred_skills:
            skill_info = SkillInfo(
                name=skill_def.get("name", ""),
                description=skill_def.get("description", ""),
                # No schema for deferred skills - loaded on demand
            )
            skills.append(skill_info)
            logger.debug("Registered deferred skill: %s", skill_info["name"])
        return skills

    def _load_skill_packages(self) -> list[str]:
        """Load skill packages from specified paths."""
        loaded = []
        for package_path in self._skill_packages:
            # TODO: Implement actual skill package loading logic
            # This should load SKILL.md, parse metadata, and register scripts/
            loaded.append(package_path)
            logger.debug("Loaded skill package: %s", package_path)
        return loaded

    @override
    def before_agent(self, state: WorkerState, runtime: Runtime) -> dict | None:
        """Initialize skill registry before agent execution.

        Loads resident and deferred skills, initializes the skill registry state.
        """
        # Get skill configuration from runtime context or config
        config_data = {}
        try:
            config_data = get_config()
            config_data = config_data.get("configurable", {})
        except RuntimeError:
            pass

        # Merge skill configuration with priority: constructor > config
        resident_skills_config = self._resident_skills or config_data.get(
            "resident_skills", []
        )
        deferred_skills_config = self._deferred_skills or config_data.get(
            "deferred_skills", []
        )
        skill_packages_config = self._skill_packages or config_data.get(
            "skill_packages", []
        )
        enable_deferred = (
            self._enable_deferred_loading
            if self._enable_deferred_loading is not None
            else config_data.get("enable_deferred_loading", True)
        )

        # Load skills
        resident_skills = []
        if resident_skills_config:
            for skill_def in resident_skills_config:
                skill_info = SkillInfo(
                    name=skill_def.get("name", ""),
                    description=skill_def.get("description", ""),
                    schema=skill_def.get("schema"),
                )
                resident_skills.append(skill_info)

        deferred_skills = []
        if enable_deferred and deferred_skills_config:
            for skill_def in deferred_skills_config:
                skill_info = SkillInfo(
                    name=skill_def.get("name", ""),
                    description=skill_def.get("description", ""),
                )
                deferred_skills.append(skill_info)

        # Load skill packages
        loaded_packages = self._load_skill_packages() if skill_packages_config else []

        # Initialize deferred skill registry in ContextVar for concurrent isolation
        deferred_registry = {
            skill["name"]: skill for skill in deferred_skills if skill.get("name")
        }
        _deferred_skill_registry.set(deferred_registry)

        skill_registry = SkillRegistryState(
            resident_skills=resident_skills,
            deferred_skills=deferred_skills,
            loaded_skill_packages=loaded_packages,
        )

        logger.info(
            "SkillLoaderMiddleware initialized: %d resident, %d deferred skills",
            len(resident_skills),
            len(deferred_skills),
        )

        return {"skills": skill_registry}


def get_deferred_skill_registry() -> dict[str, SkillInfo]:
    """Get the current deferred skill registry for this context.

    Used by skill_search tool to lookup deferred skills.
    """
    return _deferred_skill_registry.get()


def promote_deferred_skill(skill_name: str) -> SkillInfo | None:
    """Promote a deferred skill to resident status.

    Called when skill_search retrieves a deferred skill.
    Returns the promoted skill info or None if not found.
    """
    registry = _deferred_skill_registry.get()
    skill = registry.get(skill_name)
    if skill:
        # Remove from deferred registry
        del registry[skill_name]
        _deferred_skill_registry.set(registry)
        logger.info("Promoted deferred skill to resident: %s", skill_name)
    return skill

"""Registry of platform adapters."""

from __future__ import annotations
from typing import Optional

from agent_commander.adapters.base import BasePlatformAdapter
from agent_commander.adapters.codex import CodexAdapter
from agent_commander.adapters.agy import AgyAdapter
from agent_commander.adapters.claude import ClaudeAdapter
from agent_commander.adapters.grok import GrokAdapter
from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession

_ADAPTERS: dict[AgentPlatform, type[BasePlatformAdapter]] = {
    AgentPlatform.CODEX: CodexAdapter,
    AgentPlatform.AGY: AgyAdapter,
    AgentPlatform.CLAUDE: ClaudeAdapter,
    AgentPlatform.GROK: GrokAdapter,
}

_INSTANCES: dict[AgentPlatform, BasePlatformAdapter] = {}


def get_adapter(platform: AgentPlatform) -> BasePlatformAdapter:
    """Returns a singleton instance of the adapter for the requested platform."""
    if platform not in _INSTANCES:
        adapter_cls = _ADAPTERS[platform]
        _INSTANCES[platform] = adapter_cls()
    return _INSTANCES[platform]


def list_adapters() -> list[BasePlatformAdapter]:
    """Returns all available adapter instances."""
    return [get_adapter(p) for p in AgentPlatform]

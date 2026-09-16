"""Unit tests for platform adapters."""

from pathlib import Path
import pytest

from agent_commander.adapters.registry import get_adapter
from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession, UnifiedMessage


def test_platform_enums():
    for p in AgentPlatform:
        assert p.display_name
        assert p.default_dir
        assert p.badge


def test_codex_adapter_scan():
    adapter = get_adapter(AgentPlatform.CODEX)
    sessions = adapter.scan_sessions(limit=5)
    assert isinstance(sessions, list)
    if sessions:
        s = sessions[0]
        assert s.id
        assert s.platform == AgentPlatform.CODEX
        assert s.title
        assert s.size_bytes > 0


def test_agy_adapter_scan():
    adapter = get_adapter(AgentPlatform.AGY)
    sessions = adapter.scan_sessions(limit=5)
    assert isinstance(sessions, list)
    if sessions:
        s = sessions[0]
        assert s.id
        assert s.platform == AgentPlatform.AGY
        assert s.title
        messages = adapter.load_messages(s)
        assert len(messages) > 0


def test_claude_adapter_scan():
    adapter = get_adapter(AgentPlatform.CLAUDE)
    sessions = adapter.scan_sessions(limit=5)
    assert isinstance(sessions, list)
    if sessions:
        s = sessions[0]
        assert s.platform == AgentPlatform.CLAUDE
        assert s.title


def test_grok_adapter_scan():
    adapter = get_adapter(AgentPlatform.GROK)
    sessions = adapter.scan_sessions(limit=5)
    assert isinstance(sessions, list)
    if sessions:
        s = sessions[0]
        assert s.platform == AgentPlatform.GROK
        assert s.title

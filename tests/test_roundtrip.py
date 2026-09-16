"""Round-trip verification test for cross-platform copying."""

import tempfile
from pathlib import Path
import pytest

from agent_commander.adapters.codex import CodexAdapter
from agent_commander.adapters.agy import AgyAdapter
from agent_commander.adapters.claude import ClaudeAdapter
from agent_commander.adapters.grok import GrokAdapter
from agent_commander.converters.translator import SessionTranslator
from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession, UnifiedMessage, ToolCall


def test_roundtrip_claude_to_codex():
    orig_session = UnifiedSession(
        id="roundtrip-test-claude",
        platform=AgentPlatform.CLAUDE,
        title="Fix android emulator startup bug",
        raw_path=Path("dummy.jsonl"),
        messages=[
            UnifiedMessage(role="user", content="Fix android emulator startup bug"),
            UnifiedMessage(
                role="assistant",
                content="I will check the graphics backend and hypervisor configuration.",
                thinking="Hyper-V or gfxstream might be misconfigured.",
                tool_calls=[ToolCall(name="view_file", args={"path": "config.ini"})],
            ),
        ],
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        # Write out as Codex
        dest_path = SessionTranslator.copy_session(orig_session, AgentPlatform.CODEX, dest_dir=tmp_path)
        assert dest_path.exists()

        # Read back using CodexAdapter
        codex_adapter = CodexAdapter(base_dir=tmp_path.parent)
        parsed = codex_adapter._parse_session_header(dest_path)
        assert parsed is not None
        assert "Fix android emulator" in parsed.title

        messages = codex_adapter.load_messages(parsed)
        assert len(messages) >= 2
        user_msgs = [m for m in messages if m.role == "user"]
        assert any("Fix android emulator" in m.content for m in user_msgs)


def test_roundtrip_codex_to_grok():
    orig_session = UnifiedSession(
        id="roundtrip-test-codex",
        platform=AgentPlatform.CODEX,
        title="Check system health and memory leaks",
        raw_path=Path("dummy.jsonl"),
        messages=[
            UnifiedMessage(role="user", content="Check system health and memory leaks"),
            UnifiedMessage(
                role="assistant",
                content="System health is normal. Memory footprint is stable.",
            ),
        ],
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        dest_path = SessionTranslator.copy_session(orig_session, AgentPlatform.GROK, dest_dir=tmp_path)
        assert dest_path.exists()

        grok_adapter = GrokAdapter(base_dir=tmp_path.parent)
        parsed = grok_adapter._parse_session_dir(dest_path)
        assert parsed is not None

        messages = grok_adapter.load_messages(parsed)
        assert len(messages) >= 2
        assert any("Check system health" in m.content for m in messages)


def test_roundtrip_grok_to_agy():
    orig_session = UnifiedSession(
        id="roundtrip-test-grok",
        platform=AgentPlatform.GROK,
        title="Optimize database queries for sales data",
        raw_path=Path("dummy.jsonl"),
        messages=[
            UnifiedMessage(role="user", content="Optimize database queries for sales data"),
            UnifiedMessage(
                role="assistant",
                content="I have added indexes on order_date and customer_id.",
            ),
        ],
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        dest_path = SessionTranslator.copy_session(orig_session, AgentPlatform.AGY, dest_dir=tmp_path)
        assert dest_path.exists()

        agy_adapter = AgyAdapter(base_dir=tmp_path)
        sessions = agy_adapter.scan_sessions()
        assert len(sessions) == 1
        s = sessions[0]
        assert "Optimize database queries" in s.title

        messages = agy_adapter.load_messages(s)
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert "Optimize database queries" in messages[0].content
        assert messages[1].role == "assistant"
        assert "added indexes" in messages[1].content

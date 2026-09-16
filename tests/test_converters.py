"""Unit tests for conversation translation and cross-copying."""

from pathlib import Path
import tempfile
import pytest

from agent_commander.converters.translator import SessionTranslator
from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession, UnifiedMessage, ToolCall


@pytest.fixture
def sample_session():
    return UnifiedSession(
        id="test-session-1234-abcd",
        platform=AgentPlatform.CLAUDE,
        title="Test Build Python CLI App",
        raw_path=Path("sample.jsonl"),
        messages=[
            UnifiedMessage(role="user", content="Please build a dual-pane commander app."),
            UnifiedMessage(
                role="assistant",
                content="I will design and implement the app with Textual.",
                thinking="Let's structure the orthodox panes and adapters.",
                tool_calls=[ToolCall(name="run_command", args={"CommandLine": "git init"})],
            ),
        ],
    )


def test_copy_to_codex(sample_session):
    with tempfile.TemporaryDirectory() as tmpdir:
        dest_path = SessionTranslator.copy_session(
            session=sample_session,
            dest_platform=AgentPlatform.CODEX,
            dest_dir=Path(tmpdir),
        )
        assert dest_path.exists()
        assert dest_path.suffix == ".jsonl"
        content = dest_path.read_text(encoding="utf-8")
        assert "session_meta" in content
        assert "Please build a dual-pane commander app." in content
        assert "I will design and implement the app with Textual." in content


def test_copy_to_grok(sample_session):
    with tempfile.TemporaryDirectory() as tmpdir:
        dest_path = SessionTranslator.copy_session(
            session=sample_session,
            dest_platform=AgentPlatform.GROK,
            dest_dir=Path(tmpdir),
        )
        assert dest_path.exists()
        assert dest_path.name == "chat_history.jsonl"
        content = dest_path.read_text(encoding="utf-8")
        assert "Please build a dual-pane commander app." in content


def test_copy_to_agy(sample_session):
    with tempfile.TemporaryDirectory() as tmpdir:
        dest_path = SessionTranslator.copy_session(
            session=sample_session,
            dest_platform=AgentPlatform.AGY,
            dest_dir=Path(tmpdir),
        )
        assert dest_path.exists()
        assert dest_path.name == "transcript.jsonl"
        content = dest_path.read_text(encoding="utf-8")
        assert "USER_REQUEST" in content
        assert "PLANNER_RESPONSE" in content


def test_export_markdown(sample_session):
    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = Path(tmpdir) / "session.md"
        SessionTranslator.export_to_markdown(sample_session, out_file)
        assert out_file.exists()
        md_text = out_file.read_text(encoding="utf-8")
        assert "# Test Build Python CLI App" in md_text
        assert "Turn 1: USER" in md_text
        assert "Turn 2: ASSISTANT" in md_text

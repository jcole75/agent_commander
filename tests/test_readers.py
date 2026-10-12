"""Readers for Claude Code and Codex against current on-disk formats (see tests/fixtures/home)."""

from pathlib import Path

import pytest

from agent_commander.adapters.claude import ClaudeAdapter
from agent_commander.adapters.codex import CodexAdapter
from agent_commander.models.platform import AgentPlatform


def _by_id(sessions, sid):
    return next(s for s in sessions if s.id == sid)


def test_claude_scan_titles_and_metadata():
    sessions = ClaudeAdapter().scan_sessions()
    # Subagent transcripts under <session>/subagents/ are not sessions of their own.
    assert len(sessions) == 2
    s = _by_id(sessions, "6f1c2a9e-3b7d-4c1e-9a52-0d8e7b4f1a23")
    assert s.title == "Verbose flag for demo CLI"  # /rename title wins over first prompt
    assert s.model == "claude-opus-5-5"
    assert s.cwd == "/Users/jack/src/demo"
    assert s.message_count == 3  # one real prompt, two assistant API messages
    assert s.created_at.tzinfo is not None and s.updated_at.tzinfo is not None

    other = _by_id(sessions, "9a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d")
    assert other.title == "Why does the /health endpoint return 500?"


def test_claude_messages_merge_blocks_and_pair_tool_results():
    adapter = ClaudeAdapter()
    s = _by_id(adapter.scan_sessions(), "6f1c2a9e-3b7d-4c1e-9a52-0d8e7b4f1a23")
    msgs = adapter.load_messages(s)

    assert [m.role for m in msgs] == ["user", "assistant", "assistant"]
    assert msgs[0].content.startswith("Add a --verbose flag")
    # Thinking and tool_use lines from the same API message are merged into one turn.
    assert msgs[1].thinking == "Need to find the CLI entry point first."
    (call,) = msgs[1].tool_calls
    assert call.name == "Read" and call.id == "toolu_01"
    assert call.args == {"file_path": "/Users/jack/src/demo/cli.py"}
    assert call.output.startswith("import click")
    assert "logs every file path" in msgs[2].content
    # Meta caveats, sidechain prompts and slash-command echoes are hidden.
    joined = " ".join(m.content for m in msgs)
    assert "Caveat" not in joined and "subagent" not in joined and "/clear" not in joined


def test_claude_respects_config_dir(monkeypatch, agent_home, tmp_path):
    moved = tmp_path / "elsewhere"
    (agent_home / ".claude").rename(moved)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(moved))
    assert AgentPlatform.CLAUDE.default_dir == moved / "projects"
    assert len(ClaudeAdapter().scan_sessions()) == 2


def test_codex_scan_titles_and_metadata():
    sessions = CodexAdapter().scan_sessions()
    assert [s.id for s in sessions] == [
        "0199a3f2-7c41-7d20-b6a8-4e2f1c9d8b70",
        "0199a100-1111-7222-8333-444455556666",
    ]
    s = sessions[0]
    assert s.title == "Run the tests and fix whatever fails"
    assert s.model == "gpt-5.5-codex"
    assert s.cwd == "/Users/jack/src/demo"
    assert s.message_count == 2  # injected AGENTS.md / environment context is not counted
    assert sessions[1].title == "Summarise the README"


def test_codex_messages_include_assistant_text_and_tools():
    adapter = CodexAdapter()
    s = adapter.scan_sessions()[0]
    msgs = adapter.load_messages(s)

    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[0].content == "Run the tests and fix whatever fails"
    turn = msgs[1]
    assert turn.content == "Fixed the failing test in cli.py; all 10 tests pass now."
    assert turn.thinking == "**Running tests**"
    shell, patch = turn.tool_calls
    assert shell.name == "shell" and shell.args["command"][-1] == "pytest -q"
    assert "1 failed" in shell.output
    assert patch.name == "apply_patch" and patch.args.startswith("*** Begin Patch")
    assert patch.output == "Success. Updated cli.py"


def test_codex_reads_compressed_rollouts(agent_home):
    zstandard = pytest.importorskip("zstandard")
    day = agent_home / ".codex" / "sessions" / "2026" / "09" / "30"
    plain = next(day.glob("rollout-*.jsonl"))
    compressed = plain.with_name(plain.name + ".zst")
    compressed.write_bytes(zstandard.ZstdCompressor().compress(plain.read_bytes()))
    plain.unlink()

    adapter = CodexAdapter()
    s = next(x for x in adapter.scan_sessions() if x.id == "0199a100-1111-7222-8333-444455556666")
    assert s.title == "Summarise the README"
    assert [m.role for m in adapter.load_messages(s)] == ["user", "assistant"]


def test_codex_respects_codex_home(monkeypatch, agent_home, tmp_path):
    moved = tmp_path / "codex-home"
    (agent_home / ".codex").rename(moved)
    monkeypatch.setenv("CODEX_HOME", str(moved))
    assert len(CodexAdapter().scan_sessions()) == 2

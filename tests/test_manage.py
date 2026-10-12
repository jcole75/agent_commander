"""Archive, restore, delete, rename and full-text search."""

import json
import os
from pathlib import Path
import shutil

from click.testing import CliRunner
import pytest

from agent_commander.adapters.claude import ClaudeAdapter
from agent_commander.adapters.codex import CodexAdapter
from agent_commander.adapters.grok import GrokAdapter
from agent_commander.cli import main
from agent_commander.models.platform import AgentPlatform
from agent_commander.ui.app import AgentCommanderApp
from agent_commander.ui.dialogs import ConfirmDialog, RenameDialog

CLAUDE_ID = "6f1c2a9e-3b7d-4c1e-9a52-0d8e7b4f1a23"
CODEX_ID = "0199a3f2-7c41-7d20-b6a8-4e2f1c9d8b70"


def _get(sessions, sid):
    return next(s for s in sessions if s.id == sid)


def test_claude_archive_and_restore_moves_transcript_and_subagents(agent_home):
    adapter = ClaudeAdapter()
    session = _get(adapter.scan_sessions(), CLAUDE_ID)
    project = agent_home / ".claude" / "projects" / "-Users-jack-src-demo"

    archived_path = adapter.archive_session(session)
    archive = agent_home / "AgentCommander" / "archive" / "claude" / "-Users-jack-src-demo"
    assert archived_path == archive / f"{CLAUDE_ID}.jsonl" and archived_path.exists()
    assert (archive / CLAUDE_ID / "subagents" / "agent-1.jsonl").exists()
    assert not project.exists()  # emptied project folder is tidied away
    assert [s.id for s in adapter.scan_sessions()] == ["9a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d"]

    (archived,) = adapter.scan_archived_sessions()
    assert archived.archived and archived.title == "Verbose flag for demo CLI"

    restored = adapter.restore_session(archived)
    assert restored == project / f"{CLAUDE_ID}.jsonl" and restored.exists()
    assert (project / CLAUDE_ID / "subagents" / "agent-1.jsonl").exists()
    assert adapter.scan_archived_sessions() == []
    assert len(adapter.scan_sessions()) == 2


def test_codex_archive_uses_codex_layout(agent_home):
    adapter = CodexAdapter()
    session = _get(adapter.scan_sessions(), CODEX_ID)
    original = session.raw_path

    archived_path = adapter.archive_session(session)
    assert archived_path == agent_home / ".codex" / "archived_sessions" / original.name
    assert CODEX_ID not in [s.id for s in adapter.scan_sessions()]
    (archived,) = adapter.scan_archived_sessions()
    assert archived.id == CODEX_ID and archived.archived

    assert adapter.restore_session(archived) == original
    assert CODEX_ID in [s.id for s in adapter.scan_sessions()]


def test_delete_from_archive_is_permanent(agent_home):
    for adapter, sid in ((ClaudeAdapter(), CLAUDE_ID), (CodexAdapter(), CODEX_ID)):
        adapter.archive_session(_get(adapter.scan_sessions(), sid))
        (archived,) = adapter.scan_archived_sessions()
        assert adapter.delete_session(archived)
        assert adapter.scan_archived_sessions() == []
        assert sid not in [s.id for s in adapter.scan_sessions()]
    assert not (agent_home / "AgentCommander" / "archive" / "claude" / "-Users-jack-src-demo" / CLAUDE_ID).exists()


def test_grok_archive_moves_session_folder(agent_home):
    adapter = GrokAdapter()
    session = adapter.scan_sessions()[0]
    adapter.archive_session(session)
    assert len(adapter.scan_sessions()) == 1
    (archived,) = adapter.scan_archived_sessions()
    adapter.restore_session(archived)
    assert len(adapter.scan_sessions()) == 2


def test_rename_is_visible_to_the_agent(agent_home):
    claude = ClaudeAdapter()
    s = _get(claude.scan_sessions(), CLAUDE_ID)
    claude.rename_session(s, "Ship the verbose flag")
    last = json.loads(s.raw_path.read_text().splitlines()[-1])
    assert last == {"type": "custom-title", "customTitle": "Ship the verbose flag", "sessionId": CLAUDE_ID}
    assert _get(ClaudeAdapter().scan_sessions(), CLAUDE_ID).title == "Ship the verbose flag"

    codex = CodexAdapter()
    codex.rename_session(_get(codex.scan_sessions(), CODEX_ID), "Fix the tests")
    assert _get(CodexAdapter().scan_sessions(), CODEX_ID).title == "Fix the tests"

    with pytest.raises(NotImplementedError):
        GrokAdapter().rename_session(GrokAdapter().scan_sessions()[0], "x")


def test_contains_text_searches_whole_conversation(agent_home):
    codex = CodexAdapter()
    s = _get(codex.scan_sessions(), CODEX_ID)
    assert codex.contains_text(s, "ALL 10 TESTS")  # case-insensitive, in the final reply
    assert not codex.contains_text(s, "kubernetes")
    claude = ClaudeAdapter()
    assert claude.contains_text(_get(claude.scan_sessions(), CLAUDE_ID), "@click.command")  # tool output


def test_cli_archive_restore_rename_search(agent_home):
    runner = CliRunner()
    r = runner.invoke(main, ["archive", "6f1c"])
    assert r.exit_code == 0, r.output
    assert CLAUDE_ID in runner.invoke(main, ["list", "claude", "--archived"]).output
    r = runner.invoke(main, ["restore", "6f1c"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(main, ["rename", "0199a3f2", "Green build"])
    assert r.exit_code == 0, r.output
    out = runner.invoke(main, ["search", "codex", "pytest"]).output
    assert CODEX_ID in out and "Green build" in out
    assert "No sessions found." in runner.invoke(main, ["search", "codex", "kubernetes"]).output
    assert runner.invoke(main, ["rename", "grok-sess-001", "x"]).exit_code != 0


@pytest.mark.anyio
async def test_f8_archives_f9_shows_archive_f8_restores():
    app = AgentCommanderApp(left_platform=AgentPlatform.CLAUDE, right_platform=AgentPlatform.CODEX)
    async with app.run_test() as pilot:
        pane = app.commander.left_pane
        assert len(pane.sessions) == 2
        await pilot.press("f8")
        assert len(pane.sessions) == 1
        await pilot.press("f9")
        assert pane.show_archived and len(pane.sessions) == 1 and pane.sessions[0].archived
        await pilot.press("f8")
        assert pane.sessions == []
        await pilot.press("f9")
        assert not pane.show_archived and len(pane.sessions) == 2


@pytest.mark.anyio
async def test_shift_f8_deletes_only_after_confirming():
    app = AgentCommanderApp(left_platform=AgentPlatform.CODEX, right_platform=AgentPlatform.CLAUDE)
    async with app.run_test() as pilot:
        pane = app.commander.left_pane
        await pilot.press("shift+f8")
        assert isinstance(app.screen, ConfirmDialog)
        await pilot.press("enter")  # Cancel has focus, so Enter does not delete
        assert len(pane.sessions) == 2
        await pilot.press("delete")
        await pilot.press("y")
        await pilot.pause()
        assert len(pane.sessions) == 1


@pytest.mark.anyio
async def test_f6_renames_and_f4_enter_searches_contents():
    app = AgentCommanderApp(left_platform=AgentPlatform.CODEX, right_platform=AgentPlatform.CLAUDE)
    async with app.run_test() as pilot:
        pane = app.commander.left_pane
        await pilot.press("f6")
        assert isinstance(app.screen, RenameDialog)
        app.screen.query_one("#rename-input").value = "Renamed in the commander"
        await pilot.press("enter")
        await pilot.pause()
        assert any(s.title == "Renamed in the commander" for s in pane.sessions)

        await pilot.press("f4")
        for ch in "all 10":
            await pilot.press("space" if ch == " " else ch)
        assert pane.filter_query == "all 10"  # Space types into the box instead of tagging
        assert pane.filtered_sessions == []  # no title mentions it
        await pilot.press("enter")
        await pilot.pause()
        assert [s.id for s in pane.filtered_sessions] == [CODEX_ID]


@pytest.mark.skipif(not shutil.which(os.environ.get("AC_CODEX_BIN", "codex")),
                    reason="needs the codex CLI (set AC_CODEX_BIN to its path)")
def test_real_codex_cli_archive_and_restore(agent_home, monkeypatch):
    codex_bin = Path(shutil.which(os.environ.get("AC_CODEX_BIN", "codex")))
    monkeypatch.setenv("PATH", f"{codex_bin.parent}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.delenv("AC_NO_AGENT_CLI")
    adapter = CodexAdapter()
    session = _get(adapter.scan_sessions(), CODEX_ID)
    assert adapter._run_codex("--version")
    archived_path = adapter.archive_session(session)
    assert archived_path.parent.name == "archived_sessions" and archived_path.exists()
    (archived,) = adapter.scan_archived_sessions()
    assert adapter.restore_session(archived).exists()
    assert adapter.scan_archived_sessions() == []

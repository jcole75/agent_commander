"""Native cross-platform copies and Markdown transcripts."""

import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
import uuid

from click.testing import CliRunner
import pytest

from agent_commander.adapters.claude import ClaudeAdapter
from agent_commander.adapters.codex import CodexAdapter
from agent_commander.cli import main
from agent_commander.converters.portable import to_portable_turns
from agent_commander.converters.translator import SessionTranslator
from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import ToolCall, UnifiedMessage, UnifiedSession
from agent_commander.ui.app import AgentCommanderApp
from agent_commander.ui.dialogs import CopyConfirmDialog

CLAUDE_ID = "6f1c2a9e-3b7d-4c1e-9a52-0d8e7b4f1a23"
CODEX_ID = "0199a3f2-7c41-7d20-b6a8-4e2f1c9d8b70"


def _session(adapter, sid):
    s = next(x for x in adapter.scan_sessions() if x.id == sid)
    adapter.load_messages(s)
    return s


def test_portable_turns_alternate_and_start_with_user():
    s = UnifiedSession(id="x", platform=AgentPlatform.GROK, title="t", raw_path=Path("x"), messages=[
        UnifiedMessage(role="assistant", content="hello first"),
        UnifiedMessage(role="user", content="one"),
        UnifiedMessage(role="user", content="two"),
        UnifiedMessage(role="assistant", content="", tool_calls=[ToolCall(name="Bash", args={"command": "ls"}, output="a\nb")]),
        UnifiedMessage(role="assistant", content="done"),
        UnifiedMessage(role="user", content="trailing question"),
    ])
    turns = to_portable_turns(s, note="[note]")
    roles = [t.role for t in turns]
    assert roles[0] == "user" and roles[-1] == "assistant"
    assert all(a != b for a, b in zip(roles, roles[1:]))
    assert turns[0].text.endswith("[note]")
    assert any("one\n\ntwo" in t.text for t in turns)
    tool_turn = next(t for t in turns if "[Tool: Bash] ls" in t.text)
    assert tool_turn.text.index("[Tool: Bash]") < tool_turn.text.index("done")


def test_codex_to_claude_writes_resumable_transcript(agent_home):
    src = _session(CodexAdapter(), CODEX_ID)
    path = SessionTranslator.copy_session(src, AgentPlatform.CLAUDE)

    # Claude Code finds sessions by the encoded project folder of the cwd.
    assert path.parent == agent_home / ".claude" / "projects" / "-Users-jack-src-demo"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    entries = [r for r in records if r["type"] in ("user", "assistant")]
    assert [e["type"] for e in entries] == ["user", "assistant"]
    assert entries[0]["parentUuid"] is None and entries[1]["parentUuid"] == entries[0]["uuid"]
    assert {e["sessionId"] for e in entries} == {path.stem}
    assert all(e["cwd"] == "/Users/jack/src/demo" for e in entries)
    assert entries[1]["message"]["content"][0]["type"] == "text"

    copy = _session(ClaudeAdapter(), path.stem)
    assert copy.title == "Run the tests and fix whatever fails (from OpenAI Codex)"
    assert copy.messages[0].content.startswith("Run the tests and fix whatever fails")
    assert f"OpenAI Codex session {CODEX_ID}" in copy.messages[0].content
    assert "[Tool: shell] bash -lc pytest -q" in copy.messages[1].content
    assert "1 failed, 9 passed" in copy.messages[1].content


def test_claude_to_codex_writes_resumable_rollout(agent_home):
    src = _session(ClaudeAdapter(), CLAUDE_ID)
    path = SessionTranslator.copy_session(src, AgentPlatform.CODEX)

    thread_id = path.name[len("rollout-YYYY-MM-DDTHH-MM-SS-"):-len(".jsonl")]
    assert uuid.UUID(thread_id).version == 7
    records = [json.loads(line) for line in path.read_text().splitlines()]
    meta = records[0]
    assert meta["type"] == "session_meta" and meta["payload"]["id"] == thread_id
    assert meta["payload"]["cwd"] == "/Users/jack/src/demo"
    items = [r["payload"] for r in records if r["type"] == "response_item"]
    assert [(i["role"], i["content"][0]["type"]) for i in items] == [("user", "input_text"), ("assistant", "output_text")]
    events = [r["payload"]["type"] for r in records if r["type"] == "event_msg"]
    assert events == ["user_message", "agent_message"]

    index = [json.loads(l) for l in (agent_home / ".codex" / "session_index.jsonl").read_text().splitlines()]
    assert index[-1]["id"] == thread_id
    copy = next(s for s in CodexAdapter().scan_sessions() if s.id == thread_id)
    assert copy.title == "Verbose flag for demo CLI (from Claude Code)"
    msgs = CodexAdapter().load_messages(copy)
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert "[Tool: Read] /Users/jack/src/demo/cli.py" in msgs[1].content


def _codex_app_server_read(codex: str, codex_home: Path, thread_id: str) -> dict:
    """Ask a real `codex app-server` to resume, then read, a thread (no login needed)."""
    proc = subprocess.Popen([codex, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, env=dict(os.environ, CODEX_HOME=str(codex_home)))
    lines: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: [lines.put(l) for l in proc.stdout], daemon=True).start()
    try:
        def call(rid, method, params):
            proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}) + "\n")
            proc.stdin.flush()
            deadline = time.time() + 60
            while time.time() < deadline:
                try:
                    msg = json.loads(lines.get(timeout=1))
                except queue.Empty:
                    continue
                if msg.get("id") == rid:
                    return msg
            raise TimeoutError(method)

        call(1, "initialize", {"clientInfo": {"name": "agent-commander-tests", "version": "0"}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "initialized"}) + "\n")
        call(2, "thread/resume", {"threadId": thread_id})
        return call(3, "thread/read", {"threadId": thread_id, "includeTurns": True})
    finally:
        proc.kill()


@pytest.mark.skipif(not shutil.which(os.environ.get("AC_CODEX_BIN", "codex")),
                    reason="needs the codex CLI (set AC_CODEX_BIN to its path)")
def test_real_codex_resumes_copied_session(agent_home):
    src = _session(ClaudeAdapter(), CLAUDE_ID)
    path = SessionTranslator.copy_session(src, AgentPlatform.CODEX)
    thread_id = path.stem[-36:]
    result = _codex_app_server_read(shutil.which(os.environ.get("AC_CODEX_BIN", "codex")),
                                    agent_home / ".codex", thread_id)
    thread = result["result"]["thread"]
    assert thread["name"] == "Verbose flag for demo CLI (from Claude Code)"
    items = thread["turns"][0]["items"]
    assert items[0]["type"] == "userMessage"
    assert items[0]["content"][0]["text"].startswith("Add a --verbose flag")
    assert items[1]["type"] == "agentMessage"


def test_cli_list_copy_and_export(agent_home):
    runner = CliRunner()
    listed = runner.invoke(main, ["list", "codex"])
    assert listed.exit_code == 0 and CODEX_ID in listed.output

    copied = runner.invoke(main, ["copy", "0199a3f2", "--to", "claude"])
    assert copied.exit_code == 0, copied.output
    assert "Resume it with: cd /Users/jack/src/demo && claude --resume" in copied.output
    assert len(ClaudeAdapter().scan_sessions()) == 3

    out = agent_home / "t.md"
    exported = runner.invoke(main, ["copy", "6f1c", "--markdown", "-o", str(out)])
    assert exported.exit_code == 0, exported.output
    assert "# Verbose flag for demo CLI" in out.read_text()

    ambiguous = runner.invoke(main, ["copy", "0199", "--to", "claude"])
    assert ambiguous.exit_code != 0 and "matches several sessions" in ambiguous.output
    assert runner.invoke(main, ["copy", CODEX_ID]).exit_code != 0  # needs --to or --markdown


@pytest.mark.anyio
async def test_f5_native_copy_lands_in_other_pane():
    app = AgentCommanderApp(left_platform=AgentPlatform.CODEX, right_platform=AgentPlatform.CLAUDE)
    async with app.run_test() as pilot:
        before = len(app.commander.right_pane.sessions)
        await pilot.press("f5")
        assert isinstance(app.screen, CopyConfirmDialog)
        await pilot.press("enter")
        await pilot.pause()
        assert len(app.commander.right_pane.sessions) == before + 1
        assert any("(from OpenAI Codex)" in s.title for s in app.commander.right_pane.sessions)


@pytest.mark.anyio
async def test_f5_markdown_copy_writes_transcript(agent_home):
    app = AgentCommanderApp(left_platform=AgentPlatform.CLAUDE, right_platform=AgentPlatform.CODEX)
    async with app.run_test() as pilot:
        await pilot.press("f5")
        await pilot.press("m")
        await pilot.pause()
    exports = list((agent_home / "AgentCommander" / "exports").glob("claude_*.md"))
    assert len(exports) == 1
    assert len(CodexAdapter().scan_sessions()) == 2  # nothing written into Codex

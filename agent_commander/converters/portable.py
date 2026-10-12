"""Flatten any session into plain user/assistant turns that every agent CLI can resume.

Native tool calls and reasoning are tied to the platform (and model) that produced them:
Claude Code rejects thinking blocks without a valid signature, Codex keeps reasoning
encrypted, and neither knows the other's tools. So a cross-platform copy keeps the
conversation as text: each assistant turn carries a short, readable record of the
tools it ran and what they returned.
"""

from __future__ import annotations
from dataclasses import dataclass
import json
from typing import Optional

from agent_commander.models.session import ToolCall, UnifiedSession

TOOL_OUTPUT_LIMIT = 2000
TOOL_ARGS_LIMIT = 600


@dataclass
class PortableTurn:
    role: str  # "user" or "assistant"
    text: str


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"\n… [{len(text) - limit} more characters not copied]"


def _describe_args(args) -> str:
    if isinstance(args, dict):
        # Show the most telling argument inline when there is an obvious one.
        for key in ("command", "cmd", "file_path", "path", "pattern", "query", "url"):
            value = args.get(key)
            if value:
                if isinstance(value, list):
                    value = " ".join(str(v) for v in value)
                return _clip(str(value), TOOL_ARGS_LIMIT)
        return _clip(json.dumps(args, ensure_ascii=False), TOOL_ARGS_LIMIT)
    return _clip(str(args or ""), TOOL_ARGS_LIMIT)


def render_tool_call(tc: ToolCall) -> str:
    lines = [f"[Tool: {tc.name}] {_describe_args(tc.args)}".rstrip()]
    if tc.output:
        lines.append("```")
        lines.append(_clip(tc.output, TOOL_OUTPUT_LIMIT))
        lines.append("```")
    return "\n".join(lines)


def to_portable_turns(session: UnifiedSession, note: Optional[str] = None) -> list[PortableTurn]:
    """Collapse a session's messages into strictly alternating user/assistant text turns.

    The result always starts with a user turn and ends with an assistant turn, which is
    what both Claude Code and Codex expect before a new prompt is appended on resume.
    """
    turns: list[PortableTurn] = []

    def _append(role: str, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if turns and turns[-1].role == role:
            turns[-1].text += "\n\n" + text
        else:
            turns.append(PortableTurn(role, text))

    for msg in session.messages:
        if msg.role == "user":
            _append("user", msg.content)
            continue
        if msg.role == "system":
            # Compaction summaries and similar context read best as part of the conversation.
            _append("user", f"[Context] {msg.content}")
            continue
        # Tools run before the reply that reports on them.
        parts = [render_tool_call(tc) for tc in msg.tool_calls]
        if msg.content:
            parts.append(msg.content)
        _append("assistant", "\n\n".join(p for p in parts if p.strip()))

    if not turns or turns[0].role != "user":
        turns.insert(0, PortableTurn("user", "(Conversation imported by Agent Commander.)"))
    if note:
        # After the prompt, so the agent's session list still titles it by what was asked.
        turns[0].text = f"{turns[0].text}\n\n{note}"
    if turns[-1].role != "assistant":
        turns.append(PortableTurn("assistant", "(The imported conversation ends here.)"))
    return turns


def import_note(session: UnifiedSession) -> str:
    started = session.created_at or session.updated_at
    when = f"started {started.strftime('%Y-%m-%d %H:%M')}" if started else "date unknown"
    return (
        f"[Imported by Agent Commander from {session.platform.display_name} session {session.id} "
        f"({when}). Earlier tool calls are shown as text and were not re-run.]"
    )

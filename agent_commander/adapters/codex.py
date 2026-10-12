"""Codex platform adapter."""

from __future__ import annotations
from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Optional
import uuid

from agent_commander.adapters._util import file_mtime, first_line_title, iter_jsonl, parse_ts, stringify, utc_iso
from agent_commander.adapters.base import BasePlatformAdapter
from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession, UnifiedMessage, ToolCall


# Context Codex injects as "user" messages (AGENTS.md, environment, etc.), not typed by the person.
_CONTEXT_PREFIXES = (
    "<environment_context>",
    "<user_instructions>",
    "<permissions instructions>",
    "<collaboration_mode>",
    "<turn_aborted>",
    "<user_shell_command>",
    "# AGENTS.md instructions",
)


def _is_context(text: str) -> bool:
    stripped = text.lstrip()
    if stripped.startswith(_CONTEXT_PREFIXES):
        return True
    # Any message that is entirely one XML-style block is injected context.
    return bool(re.fullmatch(r"<([a-z_ ]+)>.*</\1>", stripped.strip(), re.DOTALL))


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for item in content or []:
        if isinstance(item, dict) and item.get("type") in ("text", "input_text", "output_text"):
            parts.append(item.get("text", ""))
        elif isinstance(item, str):
            parts.append(item)
    return "\n".join(p for p in parts if p)


def _parse_args(arguments):
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
            return parsed if isinstance(parsed, dict) else arguments
        except json.JSONDecodeError:
            return arguments
    return arguments if arguments is not None else {}


def _output_text(output) -> str:
    # function_call_output.output is a string, {"content": ..., "success": ...}, or a list of content items.
    if isinstance(output, dict) and "content" in output:
        return stringify(output.get("content"))
    return stringify(output)


class CodexAdapter(BasePlatformAdapter):
    """Adapter for OpenAI Codex rollouts in ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl[.zst]."""

    platform = AgentPlatform.CODEX

    def __init__(self, base_dir: Optional[Path] = None):
        super().__init__(base_dir)
        self._cache: dict[Path, tuple[tuple[float, int], UnifiedSession]] = {}

    def scan_sessions(self, limit: int = 200) -> list[UnifiedSession]:
        sessions: list[UnifiedSession] = []
        if not self.base_dir.exists():
            return sessions

        # sessions/YYYY/MM/DD/rollout-<timestamp>-<uuid>.jsonl; names sort chronologically.
        found_files: list[Path] = []

        def _dirs(parent: Path) -> list[Path]:
            return sorted((d for d in parent.iterdir() if d.is_dir() and d.name.isdigit()), reverse=True)

        for y in _dirs(self.base_dir):
            for m in _dirs(y):
                for d in _dirs(m):
                    files = [f for f in d.iterdir() if f.name.startswith("rollout-") and
                             (f.name.endswith(".jsonl") or f.name.endswith(".jsonl.zst"))]
                    found_files.extend(sorted(files, key=lambda f: f.name, reverse=True))
                    if len(found_files) >= limit:
                        break
                if len(found_files) >= limit:
                    break
            if len(found_files) >= limit:
                break

        for path in found_files[:limit]:
            try:
                session = self._parse_session_header(path)
                if session:
                    sessions.append(session)
            except Exception:
                continue

        return sessions

    def _parse_session_header(self, path: Path) -> Optional[UnifiedSession]:
        stat = path.stat()
        key = (stat.st_mtime, stat.st_size)
        cached = self._cache.get(path)
        if cached and cached[0] == key:
            return cached[1]

        match = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", path.name)
        session_id = match.group(1) if match else path.name.split(".")[0]

        saw_meta = False
        title = ""
        fallback_title = ""
        cwd = None
        created_at = None
        model = None
        message_count = 0

        for data in iter_jsonl(path):
            dtype = data.get("type")
            payload = data.get("payload") or {}

            if dtype == "session_meta":
                # Later session_meta lines can be copied in from fork history; the first one wins.
                if not saw_meta:
                    saw_meta = True
                    session_id = payload.get("id") or session_id
                    cwd = payload.get("cwd")
                    created_at = parse_ts(payload.get("timestamp"))
            elif dtype == "turn_context":
                model = payload.get("model") or model
            elif dtype == "event_msg" and payload.get("type") == "user_message" and not title:
                text = payload.get("message") or ""
                if text.strip() and not _is_context(text):
                    title = text
            elif dtype == "response_item" and payload.get("type") == "message":
                role = payload.get("role")
                if role not in ("user", "assistant"):
                    continue
                text = _content_text(payload.get("content"))
                if not text.strip() or (role == "user" and _is_context(text)):
                    continue
                message_count += 1
                if role == "user" and not fallback_title:
                    fallback_title = text

        if not saw_meta and not message_count:
            return None

        mtime = file_mtime(path)
        session = UnifiedSession(
            id=session_id,
            platform=self.platform,
            title=first_line_title(title or fallback_title) or f"Codex Session ({session_id[:8]})",
            raw_path=path,
            created_at=created_at or mtime,
            updated_at=mtime,
            cwd=cwd,
            model=model or "Codex",
            message_count=message_count,
            size_bytes=stat.st_size,
        )
        self._cache[path] = (key, session)
        return session

    def load_messages(self, session: UnifiedSession) -> list[UnifiedMessage]:
        messages: list[UnifiedMessage] = []
        if not session.raw_path.exists():
            session.messages = messages
            return messages

        pending: dict[str, ToolCall] = {}
        # Reasoning and tool calls between two assistant/user messages are folded into one assistant turn.
        turn: Optional[UnifiedMessage] = None

        def _turn(ts) -> UnifiedMessage:
            nonlocal turn
            if turn is None:
                turn = UnifiedMessage(role="assistant", content="", timestamp=ts)
                messages.append(turn)
            return turn

        def _add_call(ts, tc: ToolCall) -> None:
            _turn(ts).tool_calls.append(tc)
            if tc.id:
                pending[tc.id] = tc

        for data in iter_jsonl(session.raw_path):
            dtype = data.get("type")
            payload = data.get("payload") or {}
            ts = parse_ts(data.get("timestamp"))

            if dtype == "compacted":
                turn = None
                messages.append(UnifiedMessage(
                    role="system",
                    content="[Conversation compacted]\n" + (payload.get("message") or ""),
                    timestamp=ts,
                ))
                continue
            if dtype != "response_item":
                continue

            ptype = payload.get("type")
            if ptype == "message":
                role = payload.get("role", "assistant")
                text = _content_text(payload.get("content")).strip()
                if role not in ("user", "assistant") or not text:
                    continue
                if role == "user":
                    turn = None
                    if not _is_context(text):
                        messages.append(UnifiedMessage(role="user", content=text, timestamp=ts, raw_payload=payload))
                    continue
                # An assistant message closes the turn; any reasoning or tool calls before it belong to it.
                current = _turn(ts)
                current.content = text
                current.raw_payload = payload
                turn = None

            elif ptype == "reasoning":
                summary = stringify(payload.get("summary")) or stringify(payload.get("content"))
                if summary.strip():
                    current = _turn(ts)
                    current.thinking = "\n\n".join(p for p in (current.thinking or "", summary.strip()) if p)

            elif ptype in ("function_call", "custom_tool_call"):
                raw_args = payload.get("arguments") if ptype == "function_call" else payload.get("input")
                _add_call(ts, ToolCall(
                    name=payload.get("name", "tool"),
                    args=_parse_args(raw_args),
                    id=payload.get("call_id"),
                ))

            elif ptype == "local_shell_call":
                action = payload.get("action") or {}
                _add_call(ts, ToolCall(name="shell", args={"command": action.get("command")}, id=payload.get("call_id")))

            elif ptype == "web_search_call":
                action = payload.get("action") or {}
                _add_call(ts, ToolCall(name="web_search", args={"query": action.get("query")}, id=payload.get("id")))

            elif ptype in ("function_call_output", "custom_tool_call_output"):
                tc = pending.get(payload.get("call_id") or "")
                output = _output_text(payload.get("output"))
                if tc is not None:
                    tc.output = output
                else:
                    _add_call(ts, ToolCall(name="tool_result", output=output, id=payload.get("call_id")))

        session.messages = messages
        return messages

    def write_session(self, session: UnifiedSession, dest_dir: Optional[Path] = None) -> Path:
        target_dir = dest_dir or (self.base_dir / datetime.now().strftime("%Y/%m/%d"))
        target_dir.mkdir(parents=True, exist_ok=True)

        new_id = str(uuid.uuid4())
        ts_now = datetime.now()
        timestamp_prefix = ts_now.strftime("%Y-%m-%dT%H-%M-%S")
        filename = f"rollout-{timestamp_prefix}-{new_id}.jsonl"
        out_path = target_dir / filename

        records: list[dict] = []
        ordinal = 0

        # Session metadata line
        records.append({
            "timestamp": utc_iso(ts_now),
            "ordinal": ordinal,
            "type": "session_meta",
            "payload": {
                "session_id": new_id,
                "id": new_id,
                "timestamp": utc_iso(ts_now),
                "cwd": session.cwd or os.getcwd(),
                "cli_version": "imported",
                "source": "agent_commander",
            }
        })
        ordinal += 1

        for msg in session.messages:
            msg_ts = utc_iso(msg.timestamp or ts_now)

            if msg.thinking:
                records.append({
                    "timestamp": msg_ts,
                    "ordinal": ordinal,
                    "type": "response_item",
                    "payload": {
                        "type": "reasoning",
                        "id": str(uuid.uuid4()),
                        "summary": msg.thinking[:100],
                        "content": msg.thinking,
                    }
                })
                ordinal += 1

            if msg.content:
                records.append({
                    "timestamp": msg_ts,
                    "ordinal": ordinal,
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "id": str(uuid.uuid4()),
                        "role": msg.role if msg.role in ("user", "system", "assistant") else "assistant",
                        "content": [{"type": "text", "text": msg.content}],
                    }
                })
                ordinal += 1

            for tc in msg.tool_calls:
                call_id = str(uuid.uuid4())
                records.append({
                    "timestamp": msg_ts,
                    "ordinal": ordinal,
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call",
                        "call_id": call_id,
                        "name": tc.name,
                        "input": tc.args,
                    }
                })
                ordinal += 1

                if tc.output:
                    records.append({
                        "timestamp": msg_ts,
                        "ordinal": ordinal,
                        "type": "response_item",
                        "payload": {
                            "type": "custom_tool_call_output",
                            "call_id": call_id,
                            "output": tc.output,
                        }
                    })
                    ordinal += 1

        with open(out_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

        return out_path

    def get_resume_command(self, session: UnifiedSession) -> list[str] | None:
        cli = self.platform.resolve_cli_path() or "codex"
        return [cli, "resume", session.id]

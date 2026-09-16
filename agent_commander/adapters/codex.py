"""Codex platform adapter."""

from __future__ import annotations
from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Optional
import uuid

from agent_commander.adapters.base import BasePlatformAdapter
from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession, UnifiedMessage, ToolCall


class CodexAdapter(BasePlatformAdapter):
    """Adapter for OpenAI Codex sessions stored in ~/.codex/sessions."""

    platform = AgentPlatform.CODEX

    def scan_sessions(self, limit: int = 200) -> list[UnifiedSession]:
        sessions: list[UnifiedSession] = []
        if not self.base_dir.exists():
            return sessions

        # Fast hierarchical traversal: sessions/YYYY/MM/DD/rollout-*.jsonl
        # Years, months, and days sort naturally chronologically
        found_files: list[Path] = []
        years = sorted([y for y in self.base_dir.iterdir() if y.is_dir() and y.name.isdigit()], reverse=True)
        for y in years:
            months = sorted([m for m in y.iterdir() if m.is_dir() and m.name.isdigit()], reverse=True)
            for m in months:
                days = sorted([d for d in m.iterdir() if d.is_dir() and d.name.isdigit()], reverse=True)
                for d in days:
                    day_files = sorted(d.glob("*.jsonl"), reverse=True)
                    for f in day_files:
                        found_files.append(f)
                        if len(found_files) >= limit:
                            break
                    if len(found_files) >= limit:
                        break
                if len(found_files) >= limit:
                    break
            if len(found_files) >= limit:
                break

        for path in found_files:
            try:
                session = self._parse_session_header(path)
                if session:
                    sessions.append(session)
            except Exception:
                continue

        return sessions

    def _parse_session_header(self, path: Path) -> Optional[UnifiedSession]:
        stat = path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime)

        session_id = path.stem
        match = re.search(r"([0-9a-fA-F-]{36})", path.stem)
        if match:
            session_id = match.group(1)

        title = ""
        cwd = None
        created_at = mtime
        message_count = 0
        model = None

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line_idx in range(60):
                if line_idx > 20 and title:
                    break
                line = f.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    dtype = data.get("type")
                    payload = data.get("payload") or {}

                    if dtype == "session_meta":
                        session_id = payload.get("session_id") or session_id
                        cwd = payload.get("cwd")
                        if "timestamp" in payload:
                            try:
                                created_at = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
                            except Exception:
                                pass

                    elif dtype == "response_item":
                        ptype = payload.get("type")
                        if ptype == "message":
                            message_count += 1
                            role = payload.get("role", "")
                            content = payload.get("content", [])
                            if role == "user" and not title:
                                txt = ""
                                if isinstance(content, str):
                                    txt = content.strip()
                                elif isinstance(content, list):
                                    for item in content:
                                        if isinstance(item, dict) and item.get("type") in ("text", "input_text"):
                                            t = item.get("text", "").strip()
                                            if t:
                                                txt = t
                                                break
                                        elif isinstance(item, str) and item.strip():
                                            txt = item.strip()
                                            break
                                
                                # Skip system-injected tags masquerading as user messages
                                is_xml_tag = txt.startswith("<") and (">" in txt.splitlines()[0] or txt.endswith(">"))
                                if txt and not is_xml_tag:
                                    title = txt.splitlines()[0].strip()
                        elif ptype == "turn_context" and not model:
                            model = payload.get("model")
                except Exception:
                    continue

        if not title:
            title = f"Codex Session ({session_id[:8]})"
        elif len(title) > 60:
            title = title[:57] + "..."

        return UnifiedSession(
            id=session_id,
            platform=self.platform,
            title=title,
            raw_path=path,
            created_at=created_at,
            updated_at=mtime,
            cwd=cwd,
            model=model or "Codex",
            message_count=max(message_count, 1),
            size_bytes=stat.st_size,
        )

    def load_messages(self, session: UnifiedSession) -> list[UnifiedMessage]:
        messages: list[UnifiedMessage] = []
        if not session.raw_path.exists():
            return messages

        pending_tool_calls: dict[str, ToolCall] = {}

        with open(session.raw_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    dtype = data.get("type")
                    payload = data.get("payload") or {}
                    ts_str = data.get("timestamp")
                    ts = None
                    if ts_str:
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        except Exception:
                            pass

                    if dtype == "response_item":
                        ptype = payload.get("type")
                        if ptype == "message":
                            role = payload.get("role", "assistant")
                            content_obj = payload.get("content", "")
                            text = ""
                            if isinstance(content_obj, str):
                                text = content_obj
                            elif isinstance(content_obj, list):
                                parts = []
                                for part in content_obj:
                                    if isinstance(part, dict):
                                        if part.get("type") in ("text", "input_text"):
                                            parts.append(part.get("text", ""))
                                    elif isinstance(part, str):
                                        parts.append(part)
                                text = "\n".join(parts)

                            if text.strip():
                                messages.append(UnifiedMessage(
                                    role=role,
                                    content=text,
                                    timestamp=ts,
                                ))

                        elif ptype == "reasoning":
                            def _extract_text(obj) -> str:
                                if isinstance(obj, str):
                                    return obj
                                elif isinstance(obj, list):
                                    items = []
                                    for item in obj:
                                        if isinstance(item, str):
                                            items.append(item)
                                        elif isinstance(item, dict):
                                            txt = item.get("text") or item.get("content") or ""
                                            if txt:
                                                items.append(txt)
                                    return "\n".join(items)
                                return str(obj) if obj else ""

                            summary = _extract_text(payload.get("summary"))
                            content = _extract_text(payload.get("content"))
                            thinking_text = summary or content
                            if thinking_text.strip():
                                messages.append(UnifiedMessage(
                                    role="assistant",
                                    content="",
                                    thinking=thinking_text.strip(),
                                    timestamp=ts,
                                ))

                        elif ptype == "custom_tool_call":
                            call_id = payload.get("call_id") or payload.get("id", "")
                            name = payload.get("name", "tool")
                            tool_input = payload.get("input", {})
                            tc = ToolCall(name=name, args=tool_input)
                            pending_tool_calls[call_id] = tc
                            messages.append(UnifiedMessage(
                                role="tool",
                                content=f"Tool Call: {name}",
                                tool_calls=[tc],
                                timestamp=ts,
                            ))

                        elif ptype == "custom_tool_call_output":
                            call_id = payload.get("call_id", "")
                            output = payload.get("output", "")
                            if call_id in pending_tool_calls:
                                pending_tool_calls[call_id].output = str(output)
                except Exception:
                    continue

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
            "timestamp": ts_now.isoformat() + "Z",
            "ordinal": ordinal,
            "type": "session_meta",
            "payload": {
                "session_id": new_id,
                "id": new_id,
                "timestamp": ts_now.isoformat() + "Z",
                "cwd": session.cwd or os.getcwd(),
                "cli_version": "imported",
                "source": "agent_commander",
            }
        })
        ordinal += 1

        for msg in session.messages:
            msg_ts = (msg.timestamp or ts_now).isoformat() + "Z"

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

"""Google Antigravity (agy) platform adapter."""

from __future__ import annotations
from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Optional
import uuid

from agent_commander.adapters._util import parse_ts, utc_iso
from agent_commander.adapters.base import BasePlatformAdapter
from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession, UnifiedMessage, ToolCall


class AgyAdapter(BasePlatformAdapter):
    """Adapter for Antigravity (agy) sessions in ~/.gemini/antigravity/brain."""

    platform = AgentPlatform.AGY

    def scan_sessions(self, limit: int = 200) -> list[UnifiedSession]:
        sessions: list[UnifiedSession] = []
        if not self.base_dir.exists():
            return sessions

        subdirs = sorted(
            [d for d in self.base_dir.iterdir() if d.is_dir() and d.name != "tempmediaStorage"],
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )

        for d in subdirs[:limit]:
            try:
                session = self._parse_session_dir(d)
                if session:
                    sessions.append(session)
            except Exception:
                continue

        return sessions

    def _parse_session_dir(self, session_dir: Path) -> Optional[UnifiedSession]:
        session_id = session_dir.name
        transcript_path = session_dir / ".system_generated" / "logs" / "transcript.jsonl"
        if not transcript_path.exists():
            # Fallback to direct jsonl if any
            candidates = list(session_dir.glob("*.jsonl"))
            if candidates:
                transcript_path = candidates[0]
            else:
                return None

        stat = transcript_path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime).astimezone()
        title = ""
        created_at = mtime
        message_count = 0

        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for idx, line in enumerate(f):
                if idx > 30 and title:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    stype = data.get("type")
                    content = data.get("content") or ""
                    created_str = data.get("created_at")

                    if created_str and idx == 0:
                        try:
                            created_at = parse_ts(created_str) or created_at
                        except Exception:
                            pass

                    if stype == "USER_INPUT":
                        message_count += 1
                        if not title and content:
                            # Extract cleanly if wrapped in <USER_REQUEST>
                            match = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", content, re.DOTALL)
                            raw_prompt = match.group(1).strip() if match else content.strip()
                            first_line = raw_prompt.splitlines()[0] if raw_prompt else ""
                            if first_line:
                                title = first_line
                    elif stype == "PLANNER_RESPONSE":
                        message_count += 1
                except Exception:
                    continue

        if not title:
            title = f"Antigravity Session ({session_id[:8]})"
        elif len(title) > 60:
            title = title[:57] + "..."

        return UnifiedSession(
            id=session_id,
            platform=self.platform,
            title=title,
            raw_path=transcript_path,
            created_at=created_at,
            updated_at=mtime,
            model="Gemini",
            message_count=max(message_count, 1),
            size_bytes=stat.st_size,
        )

    def load_messages(self, session: UnifiedSession) -> list[UnifiedMessage]:
        messages: list[UnifiedMessage] = []
        transcript_path = session.raw_path
        if not transcript_path.exists():
            return messages

        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    stype = data.get("type", "")
                    content = data.get("content", "")
                    thinking = data.get("thinking")
                    tool_calls_data = data.get("tool_calls", [])
                    ts_str = data.get("created_at")
                    ts = None
                    if ts_str:
                        try:
                            ts = parse_ts(ts_str)
                        except Exception:
                            pass

                    parsed_tool_calls: list[ToolCall] = []
                    for tc in tool_calls_data:
                        name = tc.get("name", "tool")
                        args = tc.get("args", {})
                        parsed_tool_calls.append(ToolCall(name=name, args=args))

                    if stype == "USER_INPUT":
                        # Clean up prompt tags if present
                        user_text = content
                        match = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", content, re.DOTALL)
                        if match:
                            user_text = match.group(1).strip()

                        messages.append(UnifiedMessage(
                            role="user",
                            content=user_text,
                            timestamp=ts,
                        ))
                    elif stype == "PLANNER_RESPONSE":
                        messages.append(UnifiedMessage(
                            role="assistant",
                            content=content or "",
                            thinking=thinking,
                            tool_calls=parsed_tool_calls,
                            timestamp=ts,
                        ))
                    elif stype == "GENERIC":
                        messages.append(UnifiedMessage(
                            role="tool",
                            content=content,
                            timestamp=ts,
                        ))
                except Exception:
                    continue

        session.messages = messages
        return messages

    def write_session(self, session: UnifiedSession, dest_dir: Optional[Path] = None) -> Path:
        new_id = str(uuid.uuid4())
        base = dest_dir or self.base_dir
        target_dir = base / new_id / ".system_generated" / "logs"
        target_dir.mkdir(parents=True, exist_ok=True)
        out_path = target_dir / "transcript.jsonl"

        step_index = 0
        records: list[dict] = []
        now_iso = utc_iso()

        for msg in session.messages:
            msg_iso = utc_iso(msg.timestamp)
            if msg.role == "user":
                records.append({
                    "step_index": step_index,
                    "source": "USER_EXPLICIT",
                    "type": "USER_INPUT",
                    "status": "DONE",
                    "created_at": msg_iso,
                    "content": f"<USER_REQUEST>\n{msg.content}\n</USER_REQUEST>",
                })
                step_index += 1
            elif msg.role == "assistant":
                tc_list = []
                for tc in msg.tool_calls:
                    tc_list.append({
                        "name": tc.name,
                        "args": tc.args if isinstance(tc.args, dict) else {"cmd": str(tc.args)},
                    })
                records.append({
                    "step_index": step_index,
                    "source": "MODEL",
                    "type": "PLANNER_RESPONSE",
                    "status": "DONE",
                    "created_at": msg_iso,
                    "content": msg.content,
                    "thinking": msg.thinking or "",
                    "tool_calls": tc_list,
                })
                step_index += 1
            elif msg.role == "tool":
                records.append({
                    "step_index": step_index,
                    "source": "MODEL",
                    "type": "GENERIC",
                    "status": "DONE",
                    "created_at": msg_iso,
                    "content": msg.content,
                })
                step_index += 1

        with open(out_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

        return out_path

    def owned_paths(self, session: UnifiedSession) -> list[Path]:
        # The whole <base>/<session-id>/ folder belongs to the session.
        rel = session.raw_path.resolve().relative_to(self.base_dir.resolve())
        return [self.base_dir / rel.parts[0]]

    def get_resume_command(self, session: UnifiedSession) -> list[str] | None:
        cli = self.platform.resolve_cli_path()
        if cli:
            return [cli]
        return ["agy"]

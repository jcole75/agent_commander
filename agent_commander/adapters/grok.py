"""Grok Build platform adapter."""

from __future__ import annotations
from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Optional
import urllib.parse
import uuid

from agent_commander.adapters.base import BasePlatformAdapter
from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession, UnifiedMessage, ToolCall


class GrokAdapter(BasePlatformAdapter):
    """Adapter for Grok Build sessions in ~/.grok/sessions."""

    platform = AgentPlatform.GROK

    def scan_sessions(self, limit: int = 200) -> list[UnifiedSession]:
        sessions: list[UnifiedSession] = []
        if not self.base_dir.exists():
            return sessions

        # Find all chat_history.jsonl files
        history_files = sorted(
            self.base_dir.glob("**/chat_history.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for path in history_files[:limit]:
            try:
                session = self._parse_session_dir(path)
                if session:
                    sessions.append(session)
            except Exception:
                continue

        return sessions

    def _parse_session_dir(self, chat_file: Path) -> Optional[UnifiedSession]:
        stat = chat_file.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime).astimezone()
        session_id = chat_file.parent.name
        project_encoded = chat_file.parent.parent.name
        project_path = urllib.parse.unquote(project_encoded)

        title = ""
        created_at = mtime
        message_count = 0

        with open(chat_file, "r", encoding="utf-8", errors="replace") as f:
            for idx, line in enumerate(f):
                if idx > 40 and title:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    mtype = data.get("type", "")
                    content = data.get("content", "")

                    if mtype in ("user", "assistant"):
                        message_count += 1

                    if mtype == "user" and not title:
                        raw = ""
                        if isinstance(content, str):
                            raw = content
                        elif isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    raw = block.get("text", "")
                                    break
                                elif isinstance(block, str):
                                    raw = block
                                    break

                        m = re.search(r"<user_query>(.*?)(?:</user_query>|$)", raw, re.DOTALL)
                        if m:
                            q = m.group(1).strip()
                            if q:
                                title = q.splitlines()[0].strip()
                        elif raw.strip():
                            if not raw.startswith("<user_info>") and not raw.startswith("<system-reminder>"):
                                is_xml = raw.startswith("<") and (">" in raw.splitlines()[0] or raw.endswith(">"))
                                if not is_xml:
                                    title = raw.strip().splitlines()[0].strip()
                except Exception:
                    continue

        if not title:
            title = f"Grok ({session_id[:8]})"
        elif len(title) > 60:
            title = title[:57] + "..."

        return UnifiedSession(
            id=session_id,
            platform=self.platform,
            title=title,
            raw_path=chat_file,
            created_at=created_at,
            updated_at=mtime,
            cwd=project_path,
            model="Grok",
            message_count=max(message_count, 1),
            size_bytes=stat.st_size,
        )

    def load_messages(self, session: UnifiedSession) -> list[UnifiedMessage]:
        messages: list[UnifiedMessage] = []
        if not session.raw_path.exists():
            return messages

        with open(session.raw_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    mtype = data.get("type", "")
                    raw_content = data.get("content", "")
                    text = ""
                    thinking = None
                    tool_calls = []

                    if isinstance(raw_content, str):
                        text = raw_content
                    elif isinstance(raw_content, list):
                        parts = []
                        for b in raw_content:
                            if isinstance(b, dict):
                                btype = b.get("type")
                                if btype == "text":
                                    parts.append(b.get("text", ""))
                                elif btype in ("thinking", "reasoning"):
                                    thinking = b.get("text") or b.get("thinking")
                                elif btype == "tool_use":
                                    tool_calls.append(ToolCall(
                                        name=b.get("name", "tool"),
                                        args=b.get("input", {}),
                                    ))
                        text = "\n".join(parts)

                    if mtype == "user":
                        m = re.search(r"<user_query>(.*?)(?:</user_query>|$)", text, re.DOTALL)
                        if m:
                            text = m.group(1).strip()
                        elif text.startswith("<system-reminder>"):
                            # Skip standalone system reminders in conversation viewer
                            continue

                    if text.strip() or thinking or tool_calls:
                        messages.append(UnifiedMessage(
                            role=mtype or "assistant",
                            content=text.strip(),
                            thinking=thinking,
                            tool_calls=tool_calls,
                        ))
                except Exception:
                    continue

        session.messages = messages
        return messages

    def write_session(self, session: UnifiedSession, dest_dir: Optional[Path] = None) -> Path:
        new_id = str(uuid.uuid4())
        project_name = urllib.parse.quote(session.cwd or os.getcwd(), safe="")
        base = dest_dir or self.base_dir
        target_dir = base / project_name / new_id
        target_dir.mkdir(parents=True, exist_ok=True)
        out_path = target_dir / "chat_history.jsonl"

        records: list[dict] = []
        for msg in session.messages:
            content_blocks = []
            if msg.thinking:
                content_blocks.append({"type": "thinking", "text": msg.thinking})
            if msg.content:
                content_blocks.append({"type": "text", "text": msg.content})
            for tc in msg.tool_calls:
                content_blocks.append({
                    "type": "tool_use",
                    "id": str(uuid.uuid4()),
                    "name": tc.name,
                    "input": tc.args,
                })

            records.append({
                "type": msg.role,
                "content": content_blocks if content_blocks else msg.content,
            })

        with open(out_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

        return out_path

    def owned_paths(self, session: UnifiedSession) -> list[Path]:
        # <base>/<encoded project>/<session-id>/chat_history.jsonl: move the session folder.
        return [session.raw_path.parent]

    def get_resume_command(self, session: UnifiedSession) -> list[str] | None:
        cli = self.platform.resolve_cli_path() or "grok"
        return [cli, "--resume", session.id]

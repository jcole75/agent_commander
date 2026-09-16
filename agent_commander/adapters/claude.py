"""Claude Code platform adapter."""

from __future__ import annotations
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Optional
import uuid

from agent_commander.adapters.base import BasePlatformAdapter
from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession, UnifiedMessage, ToolCall


class ClaudeAdapter(BasePlatformAdapter):
    """Adapter for Claude Code sessions in ~/.claude/projects."""

    platform = AgentPlatform.CLAUDE

    def scan_sessions(self, limit: int = 200) -> list[UnifiedSession]:
        sessions: list[UnifiedSession] = []
        if not self.base_dir.exists():
            return sessions

        jsonl_files = sorted(
            self.base_dir.glob("*/*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for path in jsonl_files[:limit]:
            try:
                session = self._parse_session_file(path)
                if session:
                    sessions.append(session)
            except Exception:
                continue

        return sessions

    def _parse_session_file(self, path: Path) -> Optional[UnifiedSession]:
        stat = path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime)
        session_id = path.stem
        project_name = path.parent.name
        title = ""
        created_at = mtime
        cwd = None
        model = "Claude"
        message_count = 0

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for idx, line in enumerate(f):
                if idx > 50 and title:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if "sessionId" in data:
                        session_id = data["sessionId"]
                    if "cwd" in data:
                        cwd = data["cwd"]
                    if "timestamp" in data and idx < 5:
                        try:
                            created_at = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
                        except Exception:
                            pass

                    msg = data.get("message")
                    if msg:
                        message_count += 1
                        if "model" in msg and not model:
                            model = msg["model"]
                        role = msg.get("role") or data.get("type")
                        if role == "user" and not title:
                            content = msg.get("content")
                            if isinstance(content, str):
                                title = content.strip().splitlines()[0]
                            elif isinstance(content, list):
                                for item in content:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        txt = item.get("text", "").strip()
                                        if txt:
                                            title = txt.splitlines()[0]
                                            break
                except Exception:
                    continue

        if not title:
            title = f"Claude ({project_name} - {session_id[:8]})"
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
            model=model,
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
                    ts_str = data.get("timestamp")
                    ts = None
                    if ts_str:
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        except Exception:
                            pass

                    msg = data.get("message")
                    if not msg:
                        continue

                    role = msg.get("role", "assistant")
                    raw_content = msg.get("content")
                    text_parts = []
                    thinking_parts = []
                    tool_calls = []

                    if isinstance(raw_content, str):
                        text_parts.append(raw_content)
                    elif isinstance(raw_content, list):
                        for part in raw_content:
                            if not isinstance(part, dict):
                                continue
                            ptype = part.get("type")
                            if ptype == "text":
                                text_parts.append(part.get("text", ""))
                            elif ptype == "thinking":
                                thinking_parts.append(part.get("thinking", ""))
                            elif ptype == "tool_use":
                                tool_calls.append(ToolCall(
                                    name=part.get("name", "tool"),
                                    args=part.get("input", {}),
                                ))
                            elif ptype == "tool_result":
                                res_content = part.get("content", "")
                                tool_calls.append(ToolCall(
                                    name="tool_result",
                                    output=str(res_content),
                                ))

                    body = "\n".join(text_parts).strip()
                    thinking = "\n".join(thinking_parts).strip() or None

                    if body or thinking or tool_calls:
                        messages.append(UnifiedMessage(
                            role=role,
                            content=body,
                            thinking=thinking,
                            tool_calls=tool_calls,
                            timestamp=ts,
                        ))
                except Exception:
                    continue

        session.messages = messages
        return messages

    def write_session(self, session: UnifiedSession, dest_dir: Optional[Path] = None) -> Path:
        target_dir = dest_dir or (self.base_dir / "imported")
        target_dir.mkdir(parents=True, exist_ok=True)

        new_id = str(uuid.uuid4())
        out_path = target_dir / f"{new_id}.jsonl"
        now_iso = datetime.now().isoformat() + "Z"

        records: list[dict] = []
        for msg in session.messages:
            msg_iso = (msg.timestamp or datetime.now()).isoformat() + "Z"
            content_blocks = []
            if msg.thinking:
                content_blocks.append({"type": "thinking", "thinking": msg.thinking})
            if msg.content:
                content_blocks.append({"type": "text", "text": msg.content})
            for tc in msg.tool_calls:
                content_blocks.append({
                    "type": "tool_use",
                    "id": str(uuid.uuid4()),
                    "name": tc.name,
                    "input": tc.args,
                })
                if tc.output:
                    content_blocks.append({
                        "type": "tool_result",
                        "content": tc.output,
                    })

            records.append({
                "sessionId": new_id,
                "cwd": session.cwd or os.getcwd(),
                "timestamp": msg_iso,
                "type": msg.role,
                "message": {
                    "role": msg.role if msg.role in ("user", "assistant") else "assistant",
                    "content": content_blocks,
                    "model": session.model or "claude-3-7-sonnet",
                }
            })

        with open(out_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

        return out_path

    def get_resume_command(self, session: UnifiedSession) -> list[str] | None:
        cli = self.platform.resolve_cli_path() or "claude"
        return [cli, "--resume", session.id]

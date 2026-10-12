"""Claude Code platform adapter."""

from __future__ import annotations
from datetime import datetime, timedelta
import json
import os
import re
from pathlib import Path
from typing import Optional
import uuid

from agent_commander.adapters._util import file_mtime, first_line_title, iter_jsonl, parse_ts, stringify, utc_iso
from agent_commander.adapters.base import BasePlatformAdapter
from agent_commander.converters.portable import import_note, to_portable_turns
from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession, UnifiedMessage, ToolCall


# Transcript schema version written into imported sessions (matches Claude Code 2.1.x).
CLAUDE_TRANSCRIPT_VERSION = "2.1.296"
# Model name recorded on imported assistant turns, which no Claude model actually produced.
IMPORTED_MODEL = "agent-commander-import"

# Text Claude Code injects as "user" turns that the person never typed.
_NOISE_PREFIXES = (
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<local-command-caveat>",
    "<system-reminder>",
    "<bash-input>",
    "<bash-stdout>",
    "<bash-stderr>",
    "Caveat: The messages below were generated",
    "[Request interrupted",
)


def _is_noise(text: str) -> bool:
    return text.lstrip().startswith(_NOISE_PREFIXES)


def _user_text(content) -> str:
    """Return the typed text of a user message, ignoring tool results."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text", "").strip():
                return block["text"].strip()
    return ""


class ClaudeAdapter(BasePlatformAdapter):
    """Adapter for Claude Code sessions in ~/.claude/projects/<encoded-cwd>/<session-id>.jsonl."""

    platform = AgentPlatform.CLAUDE

    def __init__(self, base_dir: Optional[Path] = None):
        super().__init__(base_dir)
        self._cache: dict[Path, tuple[tuple[float, int], UnifiedSession]] = {}

    def scan_sessions(self, limit: int = 200) -> list[UnifiedSession]:
        sessions: list[UnifiedSession] = []
        if not self.base_dir.exists():
            return sessions

        # Only top-level transcripts; subagent transcripts live in <session-id>/subagents/.
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
        key = (stat.st_mtime, stat.st_size)
        cached = self._cache.get(path)
        if cached and cached[0] == key:
            return cached[1]

        session_id = path.stem
        custom_title = ai_title = summary = first_prompt = ""
        created_at: Optional[datetime] = None
        cwd = None
        model = None
        prompts = 0
        replies: set[str] = set()

        for data in iter_jsonl(path):
            dtype = data.get("type")
            if dtype == "custom-title":
                custom_title = data.get("customTitle") or custom_title
                continue
            if dtype == "ai-title":
                ai_title = data.get("aiTitle") or ai_title
                continue
            if dtype == "summary":
                summary = data.get("summary") or summary
                continue
            if dtype not in ("user", "assistant") or data.get("isSidechain"):
                continue

            session_id = data.get("sessionId") or session_id
            cwd = cwd or data.get("cwd")
            created_at = created_at or parse_ts(data.get("timestamp"))
            msg = data.get("message") or {}

            if dtype == "assistant":
                if msg.get("model") and msg["model"] != "<synthetic>":
                    model = msg["model"]
                replies.add(msg.get("id") or data.get("uuid") or str(len(replies)))
                continue

            if data.get("isMeta") or data.get("isCompactSummary"):
                continue
            text = _user_text(msg.get("content"))
            if text and not _is_noise(text):
                prompts += 1
                if not first_prompt:
                    first_prompt = text

        if not prompts and not replies:
            return None

        mtime = file_mtime(path)
        title = first_line_title(custom_title or ai_title or summary or first_prompt)
        session = UnifiedSession(
            id=session_id,
            platform=self.platform,
            title=title or f"Claude ({path.parent.name} - {session_id[:8]})",
            raw_path=path,
            created_at=created_at or mtime,
            updated_at=mtime,
            cwd=cwd,
            model=model or "Claude",
            message_count=prompts + len(replies),
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
        current: Optional[UnifiedMessage] = None
        current_id: Optional[str] = None

        for data in iter_jsonl(session.raw_path):
            dtype = data.get("type")
            if dtype not in ("user", "assistant") or data.get("isSidechain") or data.get("isMeta"):
                continue
            msg = data.get("message") or {}
            ts = parse_ts(data.get("timestamp"))
            content = msg.get("content")
            blocks = [{"type": "text", "text": content}] if isinstance(content, str) else (content or [])

            if dtype == "assistant":
                # Claude Code writes one line per content block; merge lines of the same API message.
                msg_id = msg.get("id")
                if current is None or msg_id is None or msg_id != current_id:
                    current = UnifiedMessage(role="assistant", content="", timestamp=ts, raw_payload=data)
                    current_id = msg_id
                    messages.append(current)
                for block in blocks:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "text" and block.get("text", "").strip():
                        current.content = "\n\n".join(p for p in (current.content, block["text"].strip()) if p)
                    elif btype == "thinking" and block.get("thinking", "").strip():
                        current.thinking = "\n\n".join(
                            p for p in (current.thinking or "", block["thinking"].strip()) if p
                        )
                    elif btype == "tool_use":
                        tc = ToolCall(name=block.get("name", "tool"), args=block.get("input", {}), id=block.get("id"))
                        current.tool_calls.append(tc)
                        if tc.id:
                            pending[tc.id] = tc
                continue

            # User line: either a real prompt, tool results, or injected noise.
            current, current_id = None, None
            texts = []
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result":
                    output = stringify(block.get("content"))
                    tc = pending.get(block.get("tool_use_id", ""))
                    if tc is not None:
                        tc.output = output
                    else:
                        messages.append(UnifiedMessage(
                            role="tool",
                            content="",
                            timestamp=ts,
                            tool_calls=[ToolCall(name="tool_result", output=output, id=block.get("tool_use_id"))],
                        ))
                elif block.get("type") == "text" and block.get("text", "").strip():
                    texts.append(block["text"].strip())

            text = "\n\n".join(t for t in texts if not _is_noise(t))
            if not text:
                continue
            role = "system" if data.get("isCompactSummary") else "user"
            messages.append(UnifiedMessage(role=role, content=text, timestamp=ts, raw_payload=data))

        session.messages = messages
        return messages

    def project_dir(self, cwd: str) -> Path:
        """Claude Code keeps each project's sessions in a folder named after the encoded cwd."""
        encoded = re.sub(r"[^a-zA-Z0-9]", "-", cwd)
        return self.base_dir / encoded[:200]

    def write_session(self, session: UnifiedSession, dest_dir: Optional[Path] = None) -> Path:
        """Write a native Claude Code transcript that `claude --resume <id>` can load."""
        cwd = session.cwd or os.getcwd()
        target_dir = dest_dir or self.project_dir(cwd)
        target_dir.mkdir(parents=True, exist_ok=True)

        new_id = str(uuid.uuid4())
        out_path = target_dir / f"{new_id}.jsonl"
        note = import_note(session) if session.platform != self.platform else None
        turns = to_portable_turns(session, note=note)

        base = {
            "isSidechain": False,
            "userType": "external",
            "cwd": cwd,
            "sessionId": new_id,
            "version": CLAUDE_TRANSCRIPT_VERSION,
            "entrypoint": "cli",
        }
        start = session.created_at or datetime.now().astimezone()
        records: list[dict] = []
        parent = None
        for idx, turn in enumerate(turns):
            entry_id = str(uuid.uuid4())
            ts = utc_iso(start + timedelta(seconds=idx))
            if turn.role == "user":
                message = {"role": "user", "content": turn.text}
            else:
                message = {
                    "id": f"msg_ac_{uuid.uuid4().hex[:24]}",
                    "type": "message",
                    "role": "assistant",
                    "model": IMPORTED_MODEL,
                    "content": [{"type": "text", "text": turn.text}],
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                }
            records.append({
                **base,
                "parentUuid": parent,
                "type": turn.role,
                "message": message,
                "uuid": entry_id,
                "timestamp": ts,
            })
            parent = entry_id

        title = session.title if session.platform == self.platform else f"{session.title} (from {session.platform.display_name})"
        records.append({"type": "custom-title", "customTitle": title, "sessionId": new_id})

        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        return out_path

    def owned_paths(self, session: UnifiedSession) -> list[Path]:
        # <id>.jsonl plus the <id>/ folder that holds subagent transcripts and tool results.
        return [session.raw_path, session.raw_path.with_suffix("")]

    def rename_session(self, session: UnifiedSession, title: str) -> None:
        # Same record /rename writes; the last one in the file wins.
        with open(session.raw_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"type": "custom-title", "customTitle": title, "sessionId": session.id}, ensure_ascii=False) + "\n")
        session.title = first_line_title(title)
        self._cache.pop(session.raw_path, None)

    def get_resume_command(self, session: UnifiedSession) -> list[str] | None:
        cli = self.platform.resolve_cli_path() or "claude"
        return [cli, "--resume", session.id]

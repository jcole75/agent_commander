"""Codex platform adapter."""

from __future__ import annotations
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import time
from typing import Optional
import uuid

from agent_commander.adapters._util import file_mtime, first_line_title, iter_jsonl, parse_ts, stringify, utc_iso
from agent_commander.adapters.base import BasePlatformAdapter
from agent_commander.converters.portable import import_note, to_portable_turns
from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession, UnifiedMessage, ToolCall


# cli_version recorded in imported rollouts' session_meta.
CODEX_ROLLOUT_VERSION = "0.162.1"


def _uuid7() -> str:
    """Time-ordered UUID (v7), the format Codex uses for thread ids."""
    value = (int(time.time() * 1000) << 80) | secrets.randbits(80)
    value = (value & ~(0xF << 76)) | (0x7 << 76)  # version 7
    value = (value & ~(0x3 << 62)) | (0x2 << 62)  # RFC 4122 variant
    return str(uuid.UUID(int=value))


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


def _rollouts(folder: Path) -> list[Path]:
    return [f for f in folder.iterdir() if f.is_file() and f.name.startswith("rollout-")
            and (f.name.endswith(".jsonl") or f.name.endswith(".jsonl.zst"))]


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
    # Shell outputs are often a JSON string of the form {"output": ..., "metadata": {...}}.
    if isinstance(output, str) and output.startswith("{"):
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and isinstance(parsed.get("output"), str):
            return parsed["output"]
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
        if not self.base_dir.exists():
            return []

        # sessions/YYYY/MM/DD/rollout-<timestamp>-<uuid>.jsonl; names sort chronologically.
        found_files: list[Path] = []

        def _dirs(parent: Path) -> list[Path]:
            return sorted((d for d in parent.iterdir() if d.is_dir() and d.name.isdigit()), reverse=True)

        for y in _dirs(self.base_dir):
            for m in _dirs(y):
                for d in _dirs(m):
                    found_files.extend(sorted(_rollouts(d), key=lambda f: f.name, reverse=True))
                    if len(found_files) >= limit:
                        break
                if len(found_files) >= limit:
                    break
            if len(found_files) >= limit:
                break

        return self._sessions_from_files(found_files[:limit])

    def _sessions_from_files(self, files: list[Path]) -> list[UnifiedSession]:
        sessions: list[UnifiedSession] = []
        names = self._thread_names()
        for path in files:
            try:
                session = self._parse_session_header(path)
                if session:
                    if session.id in names:
                        session.title = first_line_title(names[session.id])
                    sessions.append(session)
            except Exception:
                continue
        return sessions

    # --- Archive: Codex's own layout, CODEX_HOME/archived_sessions/<rollout file> ---------------

    @property
    def archive_dir(self) -> Path:
        return self.base_dir.parent / "archived_sessions"

    def scan_archived_sessions(self, limit: int = 200) -> list[UnifiedSession]:
        if not self.archive_dir.exists():
            return []
        files = sorted(_rollouts(self.archive_dir), key=lambda f: f.name, reverse=True)[:limit]
        sessions = self._sessions_from_files(files)
        for s in sessions:
            s.archived = True
        return sessions

    def _run_codex(self, *args: str) -> bool:
        """Use the Codex CLI when it is installed, so its own index stays in step with the files."""
        if os.environ.get("AC_NO_AGENT_CLI"):
            return False
        cli = self.platform.resolve_cli_path()
        if not cli:
            return False
        env = dict(os.environ, CODEX_HOME=str(self.base_dir.parent))
        try:
            result = subprocess.run([cli, *args], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    def archive_session(self, session: UnifiedSession) -> Path:
        target = self.archive_dir / session.raw_path.name
        if self._run_codex("archive", session.id) and target.exists():
            return target
        if not session.raw_path.exists():
            raise FileNotFoundError(f"{session.raw_path} no longer exists")
        if target.exists():
            raise FileExistsError(f"{target} already exists")
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(session.raw_path), str(target))
        return target

    def restore_session(self, session: UnifiedSession) -> Path:
        match = re.match(r"rollout-(\d{4})-(\d{2})-(\d{2})T", session.raw_path.name)
        if not match:
            raise ValueError(f"Unexpected rollout name {session.raw_path.name}")
        target = self.base_dir.joinpath(*match.groups()) / session.raw_path.name
        if self._run_codex("unarchive", session.id) and target.exists():
            return target
        if not session.raw_path.exists():
            raise FileNotFoundError(f"{session.raw_path} no longer exists")
        if target.exists():
            raise FileExistsError(f"{target} already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(session.raw_path), str(target))
        return target

    def delete_session(self, session: UnifiedSession) -> bool:
        if self._run_codex("delete", "--force", session.id) and not session.raw_path.exists():
            return True
        if session.raw_path.exists():
            session.raw_path.unlink()
            return True
        return False

    def rename_session(self, session: UnifiedSession, title: str) -> None:
        self._append_thread_name(session.id, title)
        session.title = first_line_title(title)

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
        """Write a native Codex rollout that `codex resume <id>` can load."""
        now = datetime.now(timezone.utc)
        target_dir = dest_dir or (self.base_dir / now.strftime("%Y/%m/%d"))
        target_dir.mkdir(parents=True, exist_ok=True)

        new_id = _uuid7()
        out_path = target_dir / f"rollout-{now.strftime('%Y-%m-%dT%H-%M-%S')}-{new_id}.jsonl"
        note = import_note(session) if session.platform != self.platform else None
        turns = to_portable_turns(session, note=note)
        cwd = session.cwd or os.getcwd()

        def line(ts: str, kind: str, payload: dict) -> dict:
            return {"timestamp": ts, "type": kind, "payload": payload}

        records: list[dict] = [line(utc_iso(now), "session_meta", {
            "session_id": new_id,
            "id": new_id,
            "timestamp": utc_iso(now),
            "cwd": cwd,
            "originator": "agent_commander",
            "cli_version": CODEX_ROLLOUT_VERSION,
            "source": "cli",
        })]
        start = session.created_at or now
        for idx, turn in enumerate(turns):
            ts = utc_iso(start + timedelta(seconds=idx))
            # response_item is what the model sees on resume; event_msg is what the Codex UI shows.
            if turn.role == "user":
                records.append(line(ts, "response_item", {
                    "type": "message", "role": "user",
                    "content": [{"type": "input_text", "text": turn.text}],
                }))
                records.append(line(ts, "event_msg", {"type": "user_message", "message": turn.text, "images": []}))
            else:
                records.append(line(ts, "response_item", {
                    "type": "message", "role": "assistant",
                    "content": [{"type": "output_text", "text": turn.text}],
                }))
                records.append(line(ts, "event_msg", {"type": "agent_message", "message": turn.text}))

        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        title = session.title if session.platform == self.platform else f"{session.title} (from {session.platform.display_name})"
        if dest_dir is None:
            self._append_thread_name(new_id, title)
        return out_path

    @property
    def session_index_path(self) -> Path:
        # Thread names set with /rename (or by us) live in CODEX_HOME/session_index.jsonl.
        return self.base_dir.parent / "session_index.jsonl"

    def _append_thread_name(self, thread_id: str, name: str) -> None:
        entry = {"id": thread_id, "thread_name": name, "updated_at": utc_iso().replace(".000Z", "Z")}
        with open(self.session_index_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _thread_names(self) -> dict[str, str]:
        names: dict[str, str] = {}
        if self.session_index_path.exists():
            for entry in iter_jsonl(self.session_index_path):
                if entry.get("id") and entry.get("thread_name"):
                    names[entry["id"]] = entry["thread_name"]  # newest entry wins
        return names

    def get_resume_command(self, session: UnifiedSession) -> list[str] | None:
        cli = self.platform.resolve_cli_path() or "codex"
        return [cli, "resume", session.id]

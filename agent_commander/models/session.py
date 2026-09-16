"""Unified conversation and session models."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from agent_commander.models.platform import AgentPlatform


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any] | str = field(default_factory=dict)
    output: Optional[str] = None


@dataclass
class UnifiedMessage:
    role: str  # "user", "assistant", "system", "tool"
    content: str
    timestamp: Optional[datetime] = None
    thinking: Optional[str] = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_payload: Optional[dict[str, Any]] = None

    @property
    def preview(self) -> str:
        text = self.content.strip().replace("\r\n", " ").replace("\n", " ")
        if len(text) > 100:
            return text[:97] + "..."
        return text or "(empty message)"


@dataclass
class UnifiedSession:
    id: str
    platform: AgentPlatform
    title: str
    raw_path: Path
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    cwd: Optional[str] = None
    model: Optional[str] = None
    message_count: int = 0
    size_bytes: int = 0
    messages: list[UnifiedMessage] = field(default_factory=list)
    tagged: bool = False

    @property
    def date_str(self) -> str:
        dt = self.updated_at or self.created_at
        if dt:
            return dt.strftime("%Y-%m-%d %H:%M")
        return "Unknown Date"

    @property
    def size_str(self) -> str:
        if self.size_bytes < 1024:
            return f"{self.size_bytes} B"
        elif self.size_bytes < 1024 * 1024:
            return f"{self.size_bytes / 1024:.1f} KB"
        else:
            return f"{self.size_bytes / (1024 * 1024):.1f} MB"

    @property
    def short_id(self) -> str:
        if len(self.id) > 12:
            return f"{self.id[:6]}..{self.id[-4:]}"
        return self.id

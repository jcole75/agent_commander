"""Base class for agent platform adapters."""

from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession, UnifiedMessage


class BasePlatformAdapter(ABC):
    """Abstract interface for reading, writing, and entering agent platform sessions."""

    platform: AgentPlatform

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or self.platform.default_dir

    @abstractmethod
    def scan_sessions(self, limit: int = 200) -> list[UnifiedSession]:
        """Scan the storage directory and return discovered sessions with metadata."""
        pass

    @abstractmethod
    def load_messages(self, session: UnifiedSession) -> list[UnifiedMessage]:
        """Read and parse all messages for a specific session."""
        pass

    @abstractmethod
    def write_session(self, session: UnifiedSession, dest_dir: Optional[Path] = None) -> Path:
        """Write or import a session into this platform's storage format."""
        pass

    @abstractmethod
    def get_resume_command(self, session: UnifiedSession) -> list[str] | None:
        """Return the CLI command line arguments to resume/enter this session, if supported."""
        pass

    def delete_session(self, session: UnifiedSession) -> bool:
        """Delete or archive a session from disk."""
        try:
            if session.raw_path.is_file():
                session.raw_path.unlink()
                return True
            elif session.raw_path.is_dir():
                import shutil
                shutil.rmtree(session.raw_path)
                return True
        except Exception:
            return False
        return False

"""Base class for agent platform adapters."""

from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
import shutil
from typing import Optional

from agent_commander.adapters._util import open_text
from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession, UnifiedMessage


def archive_home() -> Path:
    """Agent Commander's own archive, for agents that have no archive of their own."""
    return Path.home() / "AgentCommander" / "archive"


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

    # --- Archive -------------------------------------------------------------------------------
    # By default an archived session keeps its relative layout under
    # ~/AgentCommander/archive/<platform>/, so scanning that folder with the normal reader works.

    @property
    def archive_dir(self) -> Path:
        return archive_home() / self.platform.value

    def owned_paths(self, session: UnifiedSession) -> list[Path]:
        """Every file or folder that belongs to the session (moved together on archive)."""
        return [session.raw_path]

    def _archive_reader(self) -> "BasePlatformAdapter":
        return type(self)(self.archive_dir)

    def scan_archived_sessions(self, limit: int = 200) -> list[UnifiedSession]:
        if not self.archive_dir.exists():
            return []
        sessions = self._archive_reader().scan_sessions(limit=limit)
        for s in sessions:
            s.archived = True
        return sessions

    def archive_session(self, session: UnifiedSession) -> Path:
        """Move a session out of the agent's list into the archive. Returns its new main file."""
        return _move_tree(self.owned_paths(session), session.raw_path, self.base_dir, self.archive_dir)

    def restore_session(self, session: UnifiedSession) -> Path:
        """Move an archived session back where the agent will find it."""
        owned = self._archive_reader().owned_paths(session)
        return _move_tree(owned, session.raw_path, self.archive_dir, self.base_dir)

    def delete_session(self, session: UnifiedSession) -> bool:
        """Permanently delete a session's files."""
        root = self.archive_dir if session.archived else self.base_dir
        reader = self._archive_reader() if session.archived else self
        removed = False
        for path in reader.owned_paths(session):
            if not _inside(path, root):
                continue
            if path.is_dir():
                shutil.rmtree(path)
                removed = True
            elif path.exists():
                path.unlink()
                removed = True
        return removed

    # --- Rename and search ---------------------------------------------------------------------

    def rename_session(self, session: UnifiedSession, title: str) -> None:
        raise NotImplementedError(f"Renaming is not supported for {self.platform.display_name}.")

    def contains_text(self, session: UnifiedSession, query: str) -> bool:
        """Case-insensitive search through the raw session file."""
        needle = query.lower()
        try:
            with open_text(session.raw_path) as f:
                for line in f:
                    if needle in line.lower():
                        return True
        except OSError:
            return False
        return False


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _move_tree(paths: list[Path], main: Path, src_root: Path, dest_root: Path) -> Path:
    """Move paths from src_root to the same relative place under dest_root; return main's new path."""
    src_root = src_root.resolve()
    existing = [p.resolve() for p in paths if p.exists()]
    if main.resolve() not in existing and not any(_inside(main, p) for p in existing):
        raise FileNotFoundError(f"{main} no longer exists")
    targets = []
    for path in existing:
        if not _inside(path, src_root):
            raise ValueError(f"{path} is not inside {src_root}")
        target = dest_root / path.relative_to(src_root)
        if target.exists():
            raise FileExistsError(f"{target} already exists")
        targets.append((path, target))
    for path, target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target))
    _prune_empty_dirs(existing, src_root)
    return dest_root / main.resolve().relative_to(src_root)


def _prune_empty_dirs(paths: list[Path], root: Path) -> None:
    """Remove folders left empty by a move (e.g. a Codex day folder), stopping at root."""
    for path in paths:
        parent = path.parent
        while parent != root and _inside(parent, root):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

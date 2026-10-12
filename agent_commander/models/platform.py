"""Supported agent platform enumerations and metadata."""

from __future__ import annotations
from enum import Enum
from pathlib import Path
import shutil
import os


class AgentPlatform(str, Enum):
    CODEX = "codex"
    AGY = "agy"
    CLAUDE = "claude"
    GROK = "grok"

    @property
    def display_name(self) -> str:
        names = {
            AgentPlatform.CODEX: "OpenAI Codex",
            AgentPlatform.AGY: "Google Antigravity",
            AgentPlatform.CLAUDE: "Claude Code",
            AgentPlatform.GROK: "Grok Build",
        }
        return names.get(self, self.value)

    @property
    def badge(self) -> str:
        badges = {
            AgentPlatform.CODEX: "[CODEX]",
            AgentPlatform.AGY: "[AGY]",
            AgentPlatform.CLAUDE: "[CLAUDE]",
            AgentPlatform.GROK: "[GROK]",
        }
        return badges.get(self, f"[{self.value.upper()}]")

    @property
    def default_dir(self) -> Path:
        home = Path.home()
        # Honour the same overrides the agent CLIs themselves use.
        codex_home = Path(os.environ["CODEX_HOME"]) if os.environ.get("CODEX_HOME") else home / ".codex"
        claude_home = (
            Path(os.environ["CLAUDE_CONFIG_DIR"]) if os.environ.get("CLAUDE_CONFIG_DIR") else home / ".claude"
        )
        paths = {
            AgentPlatform.CODEX: codex_home / "sessions",
            AgentPlatform.AGY: home / ".gemini" / "antigravity" / "brain",
            AgentPlatform.CLAUDE: claude_home / "projects",
            AgentPlatform.GROK: home / ".grok" / "sessions",
        }
        return paths.get(self, home)

    @property
    def cli_candidates(self) -> list[str]:
        home = Path.home()
        appdata_local = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        appdata_roaming = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))

        candidates = {
            AgentPlatform.CODEX: [
                "codex",
                str(home / ".codex" / ".sandbox-bin" / "codex.exe"),
                str(home / ".codex" / "bin" / "codex.exe"),
            ],
            AgentPlatform.GROK: [
                "grok",
                str(home / ".grok" / "bin" / "grok.exe"),
                str(home / ".grok" / "grok.exe"),
            ],
            AgentPlatform.CLAUDE: [
                "claude",
                str(appdata_roaming / "npm" / "claude.cmd"),
                str(appdata_local / "Programs" / "claude" / "claude.exe"),
            ],
            AgentPlatform.AGY: [
                "agy",
                str(appdata_roaming / "Antigravity" / "bin" / "agy-node.cmd"),
                str(appdata_local / "Programs" / "antigravity" / "Antigravity.exe"),
            ],
        }
        return candidates.get(self, [])

    def resolve_cli_path(self) -> str | None:
        """Finds the executable on PATH or known default install locations."""
        for candidate in self.cli_candidates:
            if shutil.which(candidate) or Path(candidate).is_file():
                return candidate
        return None

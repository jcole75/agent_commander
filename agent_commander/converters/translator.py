"""Bidirectional cross-platform conversation translation."""

from __future__ import annotations
from pathlib import Path
import re
from typing import Optional

from agent_commander.adapters.registry import get_adapter
from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession


def default_export_dir() -> Path:
    """Where Markdown transcripts go unless the user picks a folder."""
    return Path.home() / "AgentCommander" / "exports"


def export_path(session: UnifiedSession, export_dir: Optional[Path] = None) -> Path:
    stamp = (session.updated_at or session.created_at).strftime("%Y%m%d-%H%M") if (session.updated_at or session.created_at) else "undated"
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", session.title).strip("-").lower()[:40] or "session"
    return (export_dir or default_export_dir()) / f"{session.platform.value}_{stamp}_{slug}_{session.id[:8]}.md"


class SessionTranslator:
    """Translates and exports sessions across platforms."""

    @staticmethod
    def copy_session(
        session: UnifiedSession,
        dest_platform: AgentPlatform,
        dest_dir: Optional[Path] = None,
    ) -> Path:
        """Copy a session into another platform's native storage; returns the new file."""
        if not session.messages:
            get_adapter(session.platform).load_messages(session)
        # The destination adapter reads session.platform to label where the copy came from.
        return get_adapter(dest_platform).write_session(session, dest_dir=dest_dir)

    @staticmethod
    def export_to_markdown(session: UnifiedSession, out_path: Path) -> Path:
        """Exports a session to standard formatted Markdown."""
        source_adapter = get_adapter(session.platform)
        if not session.messages:
            source_adapter.load_messages(session)

        lines = [
            f"# {session.title}",
            "",
            f"- **Platform**: {session.platform.display_name}",
            f"- **Session ID**: `{session.id}`",
            f"- **Date**: {session.date_str}",
            f"- **Model**: {session.model or 'Unknown'}",
            f"- **Working Directory**: `{session.cwd or 'N/A'}`",
            "",
            "---",
            "",
        ]

        for idx, msg in enumerate(session.messages, 1):
            role_badge = msg.role.upper()
            ts_str = f" ({msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')})" if msg.timestamp else ""
            lines.append(f"### Turn {idx}: {role_badge}{ts_str}")
            lines.append("")

            if msg.thinking:
                lines.append("> [!NOTE]")
                lines.append("> **Reasoning / Thinking:**")
                for tline in msg.thinking.splitlines():
                    lines.append(f"> {tline}")
                lines.append("")

            if msg.content:
                lines.append(msg.content)
                lines.append("")

            for tc in msg.tool_calls:
                lines.append(f"**Tool Call**: `{tc.name}`")
                lines.append("```json")
                import json
                try:
                    lines.append(json.dumps(tc.args, indent=2))
                except Exception:
                    lines.append(str(tc.args))
                lines.append("```")
                if tc.output:
                    lines.append("**Tool Output:**")
                    lines.append("```")
                    lines.append(tc.output[:1000] + ("..." if len(tc.output) > 1000 else ""))
                    lines.append("```")
                lines.append("")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return out_path

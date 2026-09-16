"""Bidirectional cross-platform conversation translation."""

from __future__ import annotations
from pathlib import Path
from typing import Optional

from agent_commander.adapters.registry import get_adapter
from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession


class SessionTranslator:
    """Translates and exports sessions across platforms."""

    @staticmethod
    def copy_session(
        session: UnifiedSession,
        dest_platform: AgentPlatform,
        dest_dir: Optional[Path] = None,
    ) -> Path:
        """Copies and translates a unified session to a target agent platform."""
        source_adapter = get_adapter(session.platform)
        dest_adapter = get_adapter(dest_platform)

        # Ensure messages are loaded
        if not session.messages:
            source_adapter.load_messages(session)

        # Clone metadata for target platform
        translated_session = UnifiedSession(
            id=session.id,
            platform=dest_platform,
            title=session.title,
            raw_path=session.raw_path,
            created_at=session.created_at,
            updated_at=session.updated_at,
            cwd=session.cwd,
            model=session.model,
            message_count=len(session.messages),
            size_bytes=session.size_bytes,
            messages=session.messages,
        )

        dest_path = dest_adapter.write_session(translated_session, dest_dir=dest_dir)
        return dest_path

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

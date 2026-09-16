"""Main Textual application for Agent Commander."""

from __future__ import annotations
from pathlib import Path
import subprocess
import sys
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Static

from agent_commander import __version__
from agent_commander.adapters.registry import get_adapter
from agent_commander.converters.translator import SessionTranslator
from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession
from agent_commander.ui.commander import DualPaneCommander
from agent_commander.ui.dialogs import (
    CopyConfirmDialog,
    PlatformSelectDialog,
    ActionResumeDialog,
    HelpDialog,
)
from agent_commander.ui.function_bar import FunctionBar
from agent_commander.ui.pane import CommanderPane
from agent_commander.ui.theme import NC_CSS
from agent_commander.ui.viewer import ConversationViewer


class AgentCommanderApp(App):
    """The Norton Commander TUI for AI Agents."""

    TITLE = f"Agent Commander v{__version__} - The Orthodox AI Agent Manager"
    CSS = NC_CSS

    BINDINGS = [
        Binding("tab", "switch_pane", "Switch Pane", priority=True, show=False),
        Binding("space", "toggle_tag", "Tag", priority=True, show=False),
        Binding("insert", "toggle_tag", "Tag", priority=True, show=False),
        Binding("enter", "enter_session", "Resume/Enter", priority=True, show=False),
        Binding("f1", "help", "Help"),
        Binding("question_mark", "help", "Help", show=False),
        Binding("f2", "select_platform", "Platform"),
        Binding("p", "select_platform", "Platform", show=False),
        Binding("1", "quick_plat_1", "Codex", show=False),
        Binding("2", "quick_plat_2", "AGY", show=False),
        Binding("3", "quick_plat_3", "Claude", show=False),
        Binding("4", "quick_plat_4", "Grok", show=False),
        Binding("f3", "view_session", "View"),
        Binding("v", "view_session", "View", show=False),
        Binding("f4", "filter_sessions", "Filter"),
        Binding("slash", "filter_sessions", "Filter", show=False),
        Binding("f5", "copy_sessions", "Copy"),
        Binding("c", "copy_sessions", "Copy", show=False),
        Binding("f6", "refresh_pane", "Refresh"),
        Binding("r", "refresh_pane", "Refresh", show=False),
        Binding("f7", "export_session", "Export"),
        Binding("e", "export_session", "Export", show=False),
        Binding("f8", "delete_session", "Delete"),
        Binding("d", "delete_session", "Delete", show=False),
        Binding("f10", "quit", "Quit"),
        Binding("q", "quit", "Quit", show=False),
    ]

    def __init__(
        self,
        left_platform: AgentPlatform = AgentPlatform.CODEX,
        right_platform: AgentPlatform = AgentPlatform.CLAUDE,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.initial_left = left_platform
        self.initial_right = right_platform

    def compose(self) -> ComposeResult:
        yield Static(
            f" 🎖️ Agent Commander v{__version__} │ Norton Commander for AI Agent Histories",
            id="title-bar",
        )
        yield DualPaneCommander(
            left_platform=self.initial_left,
            right_platform=self.initial_right,
        )
        yield FunctionBar()

    @property
    def commander(self) -> DualPaneCommander:
        return self.query_one(DualPaneCommander)

    def action_switch_pane(self) -> None:
        self.commander.switch_active_pane()

    def action_toggle_tag(self) -> None:
        self.commander.active_pane.toggle_tag_current()

    def action_help(self) -> None:
        self.push_screen(HelpDialog())

    def action_select_platform(self) -> None:
        def on_platform_chosen(plat: AgentPlatform | None) -> None:
            if plat:
                self.commander.active_pane.switch_platform(plat)

        self.push_screen(PlatformSelectDialog(), on_platform_chosen)

    def action_quick_plat_1(self) -> None:
        self.commander.active_pane.switch_platform(AgentPlatform.CODEX)

    def action_quick_plat_2(self) -> None:
        self.commander.active_pane.switch_platform(AgentPlatform.AGY)

    def action_quick_plat_3(self) -> None:
        self.commander.active_pane.switch_platform(AgentPlatform.CLAUDE)

    def action_quick_plat_4(self) -> None:
        self.commander.active_pane.switch_platform(AgentPlatform.GROK)

    def action_filter_sessions(self) -> None:
        self.commander.active_pane.toggle_filter()

    def action_refresh_pane(self) -> None:
        self.commander.active_pane.refresh_sessions()
        self.notify("Refreshed active pane from disk.")

    def action_view_session(self) -> None:
        session = self.commander.active_pane.get_current_session()
        if session:
            self.push_screen(ConversationViewer(session))
        else:
            self.notify("No conversation selected.", severity="warning")

    def action_copy_sessions(self) -> None:
        source_pane = self.commander.active_pane
        dest_pane = self.commander.inactive_pane
        selected = source_pane.get_selected_sessions()

        if not selected:
            self.notify("No conversation selected to copy.", severity="warning")
            return

        if source_pane.platform == dest_pane.platform:
            self.notify("Source and destination panes are the same platform!", severity="warning")
            return

        def on_confirm(confirmed: bool) -> None:
            if not confirmed:
                return
            copied_count = 0
            for session in selected:
                try:
                    SessionTranslator.copy_session(
                        session=session,
                        dest_platform=dest_pane.platform,
                    )
                    copied_count += 1
                except Exception as e:
                    self.notify(f"Error copying {session.short_id}: {e}", severity="error")

            # Refresh destination pane and clear tags on source
            dest_pane.refresh_sessions()
            source_pane.untag_all()
            self.notify(
                f"Successfully copied {copied_count} session(s) to {dest_pane.platform.display_name}!"
            )

        self.push_screen(
            CopyConfirmDialog(
                sessions=selected,
                source_platform=source_pane.platform,
                dest_platform=dest_pane.platform,
            ),
            on_confirm,
        )

    def action_export_session(self) -> None:
        session = self.commander.active_pane.get_current_session()
        if not session:
            self.notify("No conversation selected to export.", severity="warning")
            return

        export_dir = Path.cwd() / "exports"
        export_file = export_dir / f"{session.platform.value}_{session.id[:8]}.md"
        try:
            out_path = SessionTranslator.export_to_markdown(session, export_file)
            self.notify(f"Exported to: {out_path.name}")
        except Exception as e:
            self.notify(f"Export failed: {e}", severity="error")

    def action_delete_session(self) -> None:
        session = self.commander.active_pane.get_current_session()
        if not session:
            self.notify("No conversation selected.", severity="warning")
            return

        adapter = get_adapter(session.platform)
        if adapter.delete_session(session):
            self.commander.active_pane.refresh_sessions()
            self.notify(f"Deleted {session.short_id}.")
        else:
            self.notify(f"Could not delete {session.short_id}.", severity="error")

    def action_enter_session(self) -> None:
        session = self.commander.active_pane.get_current_session()
        if not session:
            self.notify("No conversation selected.", severity="warning")
            return

        def on_action(choice: str | None) -> None:
            if choice == "resume":
                self.resume_session_cli(session)
            elif choice == "view":
                self.push_screen(ConversationViewer(session))
            elif choice == "export":
                self.action_export_session()

        self.push_screen(ActionResumeDialog(session), on_action)

    def on_commander_pane_session_selected(self, event: CommanderPane.SessionSelected) -> None:
        self.action_enter_session()

    def resume_session_cli(self, session: UnifiedSession) -> None:
        """Suspends TUI and launches the native interactive agent CLI in console."""
        adapter = get_adapter(session.platform)
        cmd = adapter.get_resume_command(session)
        if not cmd:
            self.notify(f"Resuming not configured for {session.platform.display_name}.", severity="warning")
            return

        with self.suspend():
            print("\n" + "=" * 60)
            print(f"🎖️ Entering Agent: {session.platform.display_name}")
            print(f"Session: {session.title} ({session.id})")
            print(f"Command: {' '.join(cmd)}")
            print("=" * 60 + "\n")
            try:
                subprocess.run(cmd, check=False)
            except FileNotFoundError:
                print(f"\n[Error] Executable '{cmd[0]}' not found on system PATH.")
                print("Press Enter to return to Agent Commander...")
                input()
            except Exception as e:
                print(f"\n[Error] Failed to run agent: {e}")
                print("Press Enter to return to Agent Commander...")
                input()

    def fn_action(self, key_num: str) -> None:
        actions = {
            "1": self.action_help,
            "2": self.action_select_platform,
            "3": self.action_view_session,
            "4": self.action_filter_sessions,
            "5": self.action_copy_sessions,
            "6": self.action_refresh_pane,
            "7": self.action_export_session,
            "8": self.action_delete_session,
            "Enter": self.action_enter_session,
            "10": self.action_quit,
        }
        fn = actions.get(key_num)
        if fn:
            fn()

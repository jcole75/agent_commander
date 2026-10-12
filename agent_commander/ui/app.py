"""Main Textual application for Agent Commander."""

from __future__ import annotations
from pathlib import Path
import subprocess
import sys
from typing import Optional

from rich.markup import escape
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Input, Static

from agent_commander import __version__
from agent_commander.adapters.registry import get_adapter
from agent_commander.converters.translator import SessionTranslator, default_export_dir, export_path
from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession
from agent_commander.ui.commander import DualPaneCommander
from agent_commander.ui.dialogs import (
    ConfirmDialog,
    CopyConfirmDialog,
    RenameDialog,
    PlatformSelectDialog,
    ActionResumeDialog,
    HelpDialog,
)
from agent_commander.ui.function_bar import FunctionBar
from agent_commander.ui.pane import CommanderPane
from agent_commander.ui.theme import NC_CSS
from agent_commander.ui.viewer import ConversationViewer

PANE_ONLY_ACTIONS = {"switch_pane", "toggle_tag", "enter_session"}


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
        Binding("f6", "rename_session", "Rename"),
        Binding("n", "rename_session", "Rename", show=False),
        Binding("ctrl+r", "refresh_pane", "Refresh", show=False),
        Binding("r", "refresh_pane", "Refresh", show=False),
        Binding("f7", "export_session", "Export"),
        Binding("e", "export_session", "Export", show=False),
        Binding("f8", "archive_session", "Archive"),
        Binding("d", "archive_session", "Archive", show=False),
        Binding("shift+f8", "delete_session", "Delete", show=False),
        Binding("delete", "delete_session", "Delete", show=False),
        Binding("f9", "toggle_archive", "Archive view"),
        Binding("a", "toggle_archive", "Archive view", show=False),
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
            f" [bold]≡ AGENT COMMANDER v{__version__} ≡[/]   [italic]Norton Commander for AI Agent Histories[/]",
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

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        # Tab, Space and Enter are priority bindings for the panes; inside a dialog they belong to the dialog.
        # The same goes for the filter box, which needs Space and Enter for typing and searching.
        if action in PANE_ONLY_ACTIONS and (len(self.screen_stack) > 1 or isinstance(self.focused, Input)):
            return False
        return True

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

        def on_confirm(mode: str | None) -> None:
            if not mode:
                return
            done: list[Path] = []
            for session in selected:
                try:
                    if mode == "markdown":
                        done.append(SessionTranslator.export_to_markdown(session, export_path(session)))
                    else:
                        done.append(SessionTranslator.copy_session(session=session, dest_platform=dest_pane.platform))
                except Exception as e:
                    self.notify(f"Error copying {session.short_id}: {e}", severity="error")

            source_pane.untag_all()
            if not done:
                return
            if mode == "markdown":
                if len(done) == 1:
                    self.copy_to_clipboard(done[0].read_text(encoding="utf-8"))
                    self.notify(f"Saved {done[0]} and copied it to the clipboard.")
                else:
                    self.notify(f"Saved {len(done)} transcripts to {default_export_dir()}.")
            else:
                dest_pane.refresh_sessions()
                self.notify(
                    f"Copied {len(done)} session(s) to {dest_pane.platform.display_name}. "
                    "Press Enter on one there to resume it."
                )

        self.push_screen(
            CopyConfirmDialog(
                sessions=selected,
                source_platform=source_pane.platform,
                dest_platform=dest_pane.platform,
                export_dir=default_export_dir(),
            ),
            on_confirm,
        )

    def action_export_session(self) -> None:
        session = self.commander.active_pane.get_current_session()
        if not session:
            self.notify("No conversation selected to export.", severity="warning")
            return

        try:
            out_path = SessionTranslator.export_to_markdown(session, export_path(session))
            self.notify(f"Exported to {out_path}")
        except Exception as e:
            self.notify(f"Export failed: {e}", severity="error")

    def action_archive_session(self) -> None:
        """F8: archive the selected sessions, or restore them when viewing the archive."""
        pane = self.commander.active_pane
        selected = pane.get_selected_sessions()
        if not selected:
            self.notify("No conversation selected.", severity="warning")
            return
        adapter = get_adapter(pane.platform)
        restoring = pane.show_archived
        done = 0
        for session in selected:
            try:
                (adapter.restore_session if restoring else adapter.archive_session)(session)
                done += 1
            except Exception as e:
                self.notify(f"Could not {'restore' if restoring else 'archive'} {session.short_id}: {e}", severity="error")
        pane.refresh_sessions()
        if done and restoring:
            self.notify(f"Restored {done} session(s); {pane.platform.display_name} can resume them again.")
        elif done:
            self.notify(f"Archived {done} session(s). F9 shows the archive; F8 there restores.")

    def action_delete_session(self) -> None:
        """Shift+F8 / Del: permanently delete the selected sessions, after confirmation."""
        pane = self.commander.active_pane
        selected = pane.get_selected_sessions()
        if not selected:
            self.notify("No conversation selected.", severity="warning")
            return
        names = "\n".join(f" • {escape(s.title)}" for s in selected[:5])
        more = f"\n • ... and {len(selected) - 5} more" if len(selected) > 5 else ""
        hint = "" if pane.show_archived else "\n\nF8 archives instead, which you can undo."

        def on_confirm(confirmed: bool) -> None:
            if not confirmed:
                return
            adapter = get_adapter(pane.platform)
            deleted = sum(1 for s in selected if adapter.delete_session(s))
            pane.refresh_sessions()
            self.notify(f"Permanently deleted {deleted} session(s).")

        self.push_screen(
            ConfirmDialog(
                f"Delete {len(selected)} session(s) for good?",
                f"{names}{more}{hint}",
                confirm_label="Delete",
            ),
            on_confirm,
        )

    def action_toggle_archive(self) -> None:
        pane = self.commander.active_pane
        pane.toggle_archive_view()
        self.notify("Showing the archive. F8 restores, Shift+F8 deletes." if pane.show_archived
                    else f"Showing {pane.platform.display_name} sessions.")

    def action_rename_session(self) -> None:
        pane = self.commander.active_pane
        session = pane.get_current_session()
        if not session:
            self.notify("No conversation selected.", severity="warning")
            return

        def on_title(title: str | None) -> None:
            if not title:
                return
            try:
                get_adapter(session.platform).rename_session(session, title)
            except Exception as e:
                self.notify(str(e), severity="error")
                return
            pane.refresh_sessions()
            self.notify(f"Renamed to \"{title}\".")

        self.push_screen(RenameDialog(session), on_title)

    def action_enter_session(self) -> None:
        session = self.commander.active_pane.get_current_session()
        if not session:
            self.notify("No conversation selected.", severity="warning")
            return

        def on_action(choice: str | None) -> None:
            if choice == "resume" and session.archived:
                self.notify("Restore this session first (F8), then resume it.", severity="warning")
            elif choice == "resume":
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
            # Both CLIs look sessions up by project folder, so resume from the session's own cwd.
            cwd = session.cwd if session.cwd and Path(session.cwd).is_dir() else None
            if session.cwd and not cwd:
                print(f"Note: the session's folder {session.cwd} does not exist here; resuming from the current folder.")
            try:
                subprocess.run(cmd, check=False, cwd=cwd)
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
            "6": self.action_rename_session,
            "7": self.action_export_session,
            "8": self.action_archive_session,
            "9": self.action_toggle_archive,
            "Enter": self.action_enter_session,
            "10": self.action_quit,
        }
        fn = actions.get(key_num)
        if fn:
            fn()

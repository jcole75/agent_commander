"""Orthodox pane widget for displaying and managing agent conversation sessions."""

from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import DataTable, Input, Static

from agent_commander.adapters.registry import get_adapter
from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession


class CommanderPane(Widget):
    """A single Norton Commander pane displaying conversations for an agent platform."""

    class SessionSelected(Message):
        """Emitted when user presses Enter on a session row."""
        def __init__(self, session: UnifiedSession, pane: CommanderPane) -> None:
            self.session = session
            self.pane = pane
            super().__init__()

    class TagToggled(Message):
        """Emitted when a session tag state changes."""
        def __init__(self, pane: CommanderPane) -> None:
            self.pane = pane
            super().__init__()

    def __init__(
        self,
        pane_id: str,
        initial_platform: AgentPlatform = AgentPlatform.CODEX,
        **kwargs,
    ) -> None:
        super().__init__(id=pane_id, classes="pane-container", **kwargs)
        self.pane_id = pane_id
        self.platform = initial_platform
        self.sessions: list[UnifiedSession] = []
        self.filtered_sessions: list[UnifiedSession] = []
        self.filter_query: str = ""
        self.is_active: bool = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", id=f"{self.pane_id}-header", classes="pane-header")
            yield Input(
                placeholder="Filter sessions (Esc to cancel)...",
                id=f"{self.pane_id}-filter",
                classes="pane-filter-box",
            )
            yield DataTable(
                id=f"{self.pane_id}-table",
                classes="pane-table",
                cursor_type="row",
                show_header=True,
                zebra_stripes=False,
            )
            yield Static("", id=f"{self.pane_id}-status", classes="pane-status")

    def on_mount(self) -> None:
        table = self.query_one(f"#{self.pane_id}-table", DataTable)
        table.add_column("Tag", width=4)
        table.add_column("Date / Time", width=17)
        table.add_column("Prompt / Title", width=None)
        table.add_column("Turns", width=6)
        table.add_column("Size", width=8)
        table.add_column("ID", width=13)
        self.refresh_sessions()

    def set_active(self, active: bool) -> None:
        self.is_active = active
        if active:
            self.add_class("active-pane")
            self.query_one(f"#{self.pane_id}-table", DataTable).focus()
        else:
            self.remove_class("active-pane")
        self._update_header()

    def switch_platform(self, new_platform: AgentPlatform) -> None:
        if self.platform != new_platform:
            self.platform = new_platform
            self.filter_query = ""
            self.refresh_sessions()

    def refresh_sessions(self) -> None:
        adapter = get_adapter(self.platform)
        try:
            self.sessions = adapter.scan_sessions(limit=300)
        except Exception as e:
            self.sessions = []

        self._apply_filter()
        self._update_header()
        self._update_status()

    def _apply_filter(self) -> None:
        if not self.filter_query:
            self.filtered_sessions = list(self.sessions)
        else:
            q = self.filter_query.lower()
            self.filtered_sessions = [
                s for s in self.sessions
                if q in s.title.lower() or q in s.id.lower() or (s.cwd and q in s.cwd.lower())
            ]
        self._populate_table()

    def _populate_table(self) -> None:
        table = self.query_one(f"#{self.pane_id}-table", DataTable)
        current_row = table.cursor_row
        table.clear()

        for idx, session in enumerate(self.filtered_sessions):
            tag_str = "[bold yellow]*[/]" if session.tagged else " "
            title_text = session.title or f"Session {session.short_id}"
            table.add_row(
                tag_str,
                session.date_str,
                title_text,
                str(session.message_count),
                session.size_str,
                session.short_id,
                key=f"{session.id}_{idx}",
            )

        if self.filtered_sessions:
            if current_row is not None and current_row < len(self.filtered_sessions):
                table.move_cursor(row=current_row)
            else:
                table.move_cursor(row=0)

    def _update_header(self) -> None:
        header = self.query_one(f"#{self.pane_id}-header", Static)
        pane_name = "LEFT" if "left" in self.pane_id else "RIGHT"
        active_mark = "► " if self.is_active else "  "
        header.update(
            f"{active_mark}[bold]{pane_name}: {self.platform.display_name}[/]  "
            f"({len(self.filtered_sessions)} sessions)  "
            f"[italic]{str(self.platform.default_dir)}[/]"
        )

    def _update_status(self) -> None:
        status = self.query_one(f"#{self.pane_id}-status", Static)
        tagged = [s for s in self.sessions if s.tagged]
        tagged_bytes = sum(s.size_bytes for s in tagged)
        total_bytes = sum(s.size_bytes for s in self.sessions)
        
        tagged_size_str = f"{tagged_bytes / 1024:.1f} KB" if tagged_bytes < 1024 * 1024 else f"{tagged_bytes / (1024*1024):.1f} MB"
        total_size_str = f"{total_bytes / 1024:.1f} KB" if total_bytes < 1024 * 1024 else f"{total_bytes / (1024*1024):.1f} MB"

        status.update(
            f"Tagged: [bold]{len(tagged)}[/] ({tagged_size_str})  |  "
            f"Total: [bold]{len(self.sessions)}[/] ({total_size_str})"
        )

    def toggle_tag_current(self) -> None:
        session = self.get_current_session()
        if session:
            session.tagged = not session.tagged
            self._populate_table()
            self._update_status()
            # Move down one row classic Norton Commander style!
            table = self.query_one(f"#{self.pane_id}-table", DataTable)
            if table.cursor_row is not None and table.cursor_row + 1 < len(self.filtered_sessions):
                table.move_cursor(row=table.cursor_row + 1)
            self.post_message(self.TagToggled(self))

    def tag_all(self) -> None:
        for s in self.filtered_sessions:
            s.tagged = True
        self._populate_table()
        self._update_status()

    def untag_all(self) -> None:
        for s in self.sessions:
            s.tagged = False
        self._populate_table()
        self._update_status()

    def get_current_session(self) -> Optional[UnifiedSession]:
        table = self.query_one(f"#{self.pane_id}-table", DataTable)
        if table.cursor_row is not None and 0 <= table.cursor_row < len(self.filtered_sessions):
            return self.filtered_sessions[table.cursor_row]
        return None

    def get_selected_sessions(self) -> list[UnifiedSession]:
        tagged = [s for s in self.sessions if s.tagged]
        if tagged:
            return tagged
        current = self.get_current_session()
        return [current] if current else []

    def toggle_filter(self) -> None:
        box = self.query_one(f"#{self.pane_id}-filter", Input)
        if box.has_class("visible"):
            box.remove_class("visible")
            self.query_one(f"#{self.pane_id}-table", DataTable).focus()
        else:
            box.add_class("visible")
            box.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == f"{self.pane_id}-filter":
            self.filter_query = event.value
            self._apply_filter()
            self._update_status()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        session = self.get_current_session()
        if session:
            self.post_message(self.SessionSelected(session, self))

"""Orthodox pane widget for displaying and managing agent conversation sessions."""

from __future__ import annotations
from typing import Optional
from rich.markup import escape
from rich.text import Text
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
        self.content_matches: Optional[set[str]] = None  # ids whose text matched a full-text search
        self.show_archived: bool = False
        self.is_active: bool = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", id=f"{self.pane_id}-header", classes="pane-header")
            yield Input(
                placeholder="Filter by title; Enter searches inside conversations (Esc closes)",
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
        table.add_column("Date", width=12)
        table.add_column("Turns", width=6)
        table.add_column("Size", width=8)
        table.add_column("Prompt / Title", width=None)
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
            self.content_matches = None
            self.refresh_sessions()

    def toggle_archive_view(self) -> None:
        self.show_archived = not self.show_archived
        self.content_matches = None
        self.refresh_sessions()

    def refresh_sessions(self) -> None:
        adapter = get_adapter(self.platform)
        try:
            if self.show_archived:
                self.sessions = adapter.scan_archived_sessions(limit=1000)
            else:
                self.sessions = adapter.scan_sessions(limit=300)
        except Exception:
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
                or (self.content_matches is not None and s.id in self.content_matches)
            ]
        self._populate_table()

    def search_contents(self, query: str) -> int:
        """Full-text search through every session in the pane; returns how many matched."""
        self.filter_query = query
        adapter = get_adapter(self.platform)
        self.content_matches = {s.id for s in self.sessions if query and adapter.contains_text(s, query)}
        self._apply_filter()
        self._update_header()
        self._update_status()
        return len(self.filtered_sessions)

    def _populate_table(self) -> None:
        table = self.query_one(f"#{self.pane_id}-table", DataTable)
        current_row = table.cursor_row
        table.clear()

        for idx, session in enumerate(self.filtered_sessions):
            tag_str = "[bold yellow]*[/]" if session.tagged else " "
            title_text = Text(session.title or f"Session {session.short_id}")
            table.add_row(
                tag_str,
                session.date_short,
                str(session.message_count),
                session.size_str,
                title_text,
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
        adapter = get_adapter(self.platform)
        where = adapter.archive_dir if self.show_archived else adapter.base_dir
        view = " [bold reverse] ARCHIVE [/]" if self.show_archived else ""
        header.update(
            f"{active_mark}[bold]{pane_name}: {self.platform.display_name}[/]{view}  "
            f"({len(self.filtered_sessions)} sessions)  "
            f"[italic]{escape(str(where))}[/]"
        )

    def _update_status(self) -> None:
        status = self.query_one(f"#{self.pane_id}-status", Static)
        tagged = [s for s in self.sessions if s.tagged]
        tagged_bytes = sum(s.size_bytes for s in tagged)
        total_bytes = sum(s.size_bytes for s in self.sessions)
        
        tagged_size_str = f"{tagged_bytes / 1024:.1f} KB" if tagged_bytes < 1024 * 1024 else f"{tagged_bytes / (1024*1024):.1f} MB"
        total_size_str = f"{total_bytes / 1024:.1f} KB" if total_bytes < 1024 * 1024 else f"{total_bytes / (1024*1024):.1f} MB"

        cur = self.get_current_session()
        active_info = f" | [bold yellow]{cur.short_id}[/] ({cur.model or 'Agent'})" if cur else ""

        status.update(
            f"Tagged: [bold]{len(tagged)}[/] ({tagged_size_str}) | "
            f"Total: [bold]{len(self.sessions)}[/] ({total_size_str}){active_info}"
        )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._update_status()

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

    def key_escape(self) -> None:
        box = self.query_one(f"#{self.pane_id}-filter", Input)
        if box.has_class("visible"):
            box.value = ""  # clears the filter via on_input_changed
            self.toggle_filter()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == f"{self.pane_id}-filter":
            self.filter_query = event.value
            self.content_matches = None
            self._apply_filter()
            self._update_header()
            self._update_status()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == f"{self.pane_id}-filter" and event.value.strip():
            found = self.search_contents(event.value.strip())
            self.app.notify(f"{found} conversation(s) mention \"{event.value.strip()}\".")
            self.query_one(f"#{self.pane_id}-table", DataTable).focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        session = self.get_current_session()
        if session:
            self.post_message(self.SessionSelected(session, self))

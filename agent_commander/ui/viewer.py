"""Conversation viewer modal screen."""

from __future__ import annotations
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from agent_commander.adapters.registry import get_adapter
from agent_commander.models.session import UnifiedSession


class ConversationViewer(ModalScreen[None]):
    """Fullscreen viewer for conversation transcripts and turns."""

    DEFAULT_CSS = """
    ConversationViewer {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    """

    def __init__(self, session: UnifiedSession) -> None:
        super().__init__()
        self.session = session

    def compose(self) -> ComposeResult:
        with Vertical(id="viewer-box"):
            with Vertical(id="viewer-header"):
                yield Static(f"[bold yellow]{self.session.title}[/]")
                yield Static(
                    f"Platform: [bold]{self.session.platform.display_name}[/] | "
                    f"Model: {self.session.model or 'Unknown'} | "
                    f"Date: {self.session.date_str} | "
                    f"Path: [italic]{self.session.raw_path}[/]"
                )

            with ScrollableContainer(id="viewer-scroll"):
                adapter = get_adapter(self.session.platform)
                if not self.session.messages:
                    adapter.load_messages(self.session)

                if not self.session.messages:
                    yield Static("[italic yellow]No messages parsed or session is empty.[/]")

                for idx, msg in enumerate(self.session.messages, 1):
                    role_cls = "message-user" if msg.role == "user" else ("message-assistant" if msg.role == "assistant" else "message-card")
                    badge_color = "green" if msg.role == "user" else ("cyan" if msg.role == "assistant" else "yellow")
                    ts_str = f" • {msg.timestamp.strftime('%H:%M:%S')}" if msg.timestamp else ""

                    with Vertical(classes=f"message-card {role_cls}"):
                        yield Static(f"[{badge_color} bold]Turn {idx}: {msg.role.upper()}[/][dim]{ts_str}[/]")

                        if msg.thinking:
                            with Vertical(classes="message-thinking"):
                                yield Static("[bold yellow]Thinking / Chain of Thought:[/]")
                                yield Static(msg.thinking)

                        if msg.content:
                            yield Static(msg.content)

                        for tc in msg.tool_calls:
                            yield Static(f"[bold magenta]⚡ Tool Call:[/] [bold]{tc.name}[/]")
                            if tc.args:
                                import json
                                try:
                                    args_str = json.dumps(tc.args, indent=2)
                                except Exception:
                                    args_str = str(tc.args)
                                yield Static(f"[dim]{args_str}[/]")
                            if tc.output:
                                yield Static(f"[italic]Output: {tc.output[:500]}[/]")

            with Horizontal(classes="dialog-buttons"):
                yield Button("Resume in Agent CLI", id="btn-resume", variant="success")
                yield Button("Close (Esc)", id="btn-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-resume":
            self.dismiss(None)
            self.app.resume_session_cli(self.session)
        else:
            self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)

    def key_r(self) -> None:
        self.dismiss(None)
        self.app.resume_session_cli(self.session)

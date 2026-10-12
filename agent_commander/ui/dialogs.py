"""Modal dialogs for Agent Commander."""

from __future__ import annotations
from pathlib import Path

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static, Label

from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession


class CopyConfirmDialog(ModalScreen[str | None]):
    """Dialog confirming a copy between panes; returns "native", "markdown" or None."""

    DEFAULT_CSS = """
    CopyConfirmDialog {
        align: center middle;
        background: rgba(0, 0, 0, 0.6);
    }
    """

    def __init__(
        self,
        sessions: list[UnifiedSession],
        source_platform: AgentPlatform,
        dest_platform: AgentPlatform,
        export_dir: Path,
    ) -> None:
        super().__init__()
        self.sessions = sessions
        self.source_platform = source_platform
        self.dest_platform = dest_platform
        self.export_dir = export_dir

    def compose(self) -> ComposeResult:
        count = len(self.sessions)
        with Vertical(classes="dialog-box"):
            yield Static(f"COPY {count} CONVERSATION{'S' if count > 1 else ''}", classes="dialog-title")
            yield Static(f"From: [bold yellow]{self.source_platform.display_name}[/]")
            yield Static(f"To:   [bold #55ff55]{self.dest_platform.display_name}[/]")
            yield Static("")

            summary_items = [f" • [bold]{escape(s.title)}[/] ({s.date_str})" for s in self.sessions[:3]]
            if count > 3:
                summary_items.append(f" • ... and {count - 3} more")
            yield Static("\n".join(summary_items))
            yield Static("")
            yield Static(
                f"[bold]\\[N][/] Native session: resume it with [italic]{self.dest_platform.value}[/] "
                f"in the same folder. Tool calls are kept as text."
            )
            yield Static(f"[bold]\\[M][/] Markdown transcript: saved to {escape(str(self.export_dir))} to paste anywhere.")

            with Horizontal(classes="dialog-buttons"):
                yield Button("Native (Enter)", id="btn-native", variant="success")
                yield Button("Markdown (M)", id="btn-markdown", variant="primary")
                yield Button("Cancel (Esc)", id="btn-cancel", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss({"btn-native": "native", "btn-markdown": "markdown"}.get(event.button.id))

    def key_enter(self) -> None:
        self.dismiss("native")

    def key_n(self) -> None:
        self.dismiss("native")

    def key_m(self) -> None:
        self.dismiss("markdown")

    def key_escape(self) -> None:
        self.dismiss(None)


class PlatformSelectDialog(ModalScreen[AgentPlatform | None]):
    """Dialog for picking an agent platform."""

    DEFAULT_CSS = """
    PlatformSelectDialog {
        align: center middle;
        background: rgba(0, 0, 0, 0.6);
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog-box"):
            yield Static("Select Agent Platform", classes="dialog-title")
            yield Static("Choose platform to display in active pane:")
            yield Static("")

            with Vertical():
                yield Button("[1] OpenAI Codex", id="plat-codex")
                yield Button("[2] Google Antigravity (agy)", id="plat-agy")
                yield Button("[3] Claude Code", id="plat-claude")
                yield Button("[4] Grok Build", id="plat-grok")

            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel (Esc)", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        mapping = {
            "plat-codex": AgentPlatform.CODEX,
            "plat-agy": AgentPlatform.AGY,
            "plat-claude": AgentPlatform.CLAUDE,
            "plat-grok": AgentPlatform.GROK,
        }
        if event.button.id in mapping:
            self.dismiss(mapping[event.button.id])
        else:
            self.dismiss(None)

    def key_1(self) -> None:
        self.dismiss(AgentPlatform.CODEX)

    def key_2(self) -> None:
        self.dismiss(AgentPlatform.AGY)

    def key_3(self) -> None:
        self.dismiss(AgentPlatform.CLAUDE)

    def key_4(self) -> None:
        self.dismiss(AgentPlatform.GROK)

    def key_escape(self) -> None:
        self.dismiss(None)


class ActionResumeDialog(ModalScreen[str | None]):
    """Dialog shown when user presses Enter on a session."""

    DEFAULT_CSS = """
    ActionResumeDialog {
        align: center middle;
        background: rgba(0, 0, 0, 0.6);
    }
    """

    def __init__(self, session: UnifiedSession) -> None:
        super().__init__()
        self.session = session

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog-box"):
            yield Static(f"Enter Agent: {self.session.platform.display_name}", classes="dialog-title")
            yield Static(f"Session: [bold yellow]{escape(self.session.title)}[/]")
            yield Static(f"ID: [italic]{self.session.id}[/] | Turns: {self.session.message_count}")
            yield Static("")

            cli_avail = self.session.platform.resolve_cli_path()
            cli_info = f"[green]CLI Available ({cli_avail})[/]" if cli_avail else "[yellow]CLI not on path (will try default)[/]"
            yield Static(f"Agent Engine: {cli_info}")
            yield Static("")

            with Vertical():
                yield Button("► [R] Resume in Agent CLI (Interactive)", id="action-resume")
                yield Button("  [V] View Transcript & Tool Calls", id="action-view")
                yield Button("  [E] Export to Markdown", id="action-export")

            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel (Esc)", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {
            "action-resume": "resume",
            "action-view": "view",
            "action-export": "export",
        }
        self.dismiss(actions.get(event.button.id, None))

    def key_r(self) -> None:
        self.dismiss("resume")

    def key_enter(self) -> None:
        self.dismiss("resume")

    def key_v(self) -> None:
        self.dismiss("view")

    def key_e(self) -> None:
        self.dismiss("export")

    def key_escape(self) -> None:
        self.dismiss(None)


class HelpDialog(ModalScreen[None]):
    """Norton Commander keyboard shortcuts help modal."""

    DEFAULT_CSS = """
    HelpDialog {
        align: center middle;
        background: rgba(0, 0, 0, 0.6);
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog-box"):
            yield Static("Agent Commander - Help & Shortcuts", classes="dialog-title")
            yield Static(
                "• [bold cyan]Tab[/]           : Switch active pane (Left ⇄ Right)\n"
                "• [bold cyan]Space / Ins[/]   : Tag / Untag current conversation [*]\n"
                "• [bold cyan]Enter[/]         : Enter Agent (Resume interactive CLI or inspect)\n"
                "• [bold cyan]F1 / ?[/]        : Show this Help dialog\n"
                "• [bold cyan]F2 / p[/]        : Select Platform for active pane\n"
                "• [bold cyan]1, 2, 3, 4[/]    : Quick switch (1:Codex, 2:AGY, 3:Claude, 4:Grok)\n"
                "• [bold cyan]F3 / v[/]        : View conversation transcript & tool calls\n"
                "• [bold cyan]F4 / /[/]        : Filter conversations by search term\n"
                "• [bold cyan]F5 / c[/]        : Copy to the other pane (native session or Markdown)\n"
                "• [bold cyan]F6 / r[/]        : Refresh pane from disk\n"
                "• [bold cyan]F7 / e[/]        : Export session to Markdown (~/AgentCommander/exports)\n"
                "• [bold cyan]F8 / d[/]        : Delete / Archive session\n"
                "• [bold cyan]F10 / q[/]       : Quit Agent Commander\n"
            )
            with Horizontal(classes="dialog-buttons"):
                yield Button("Close (Esc)", id="btn-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)

    def key_enter(self) -> None:
        self.dismiss(None)

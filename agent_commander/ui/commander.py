"""Dual pane orthodox container managing Left and Right panes."""

from __future__ import annotations
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget

from agent_commander.models.platform import AgentPlatform
from agent_commander.ui.pane import CommanderPane


class DualPaneCommander(Widget):
    """Container holding Left and Right orthodox panes."""

    DEFAULT_CSS = """
    DualPaneCommander {
        height: 1fr;
        layout: horizontal;
    }
    """

    def __init__(
        self,
        left_platform: AgentPlatform = AgentPlatform.CODEX,
        right_platform: AgentPlatform = AgentPlatform.CLAUDE,
        **kwargs,
    ) -> None:
        super().__init__(id="commander-container", **kwargs)
        self.left_platform = left_platform
        self.right_platform = right_platform
        self.active_pane_side = "left"

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield CommanderPane(
                pane_id="pane-left",
                initial_platform=self.left_platform,
            )
            yield CommanderPane(
                pane_id="pane-right",
                initial_platform=self.right_platform,
            )

    def on_mount(self) -> None:
        self.left_pane.set_active(True)
        self.right_pane.set_active(False)

    @property
    def left_pane(self) -> CommanderPane:
        return self.query_one("#pane-left", CommanderPane)

    @property
    def right_pane(self) -> CommanderPane:
        return self.query_one("#pane-right", CommanderPane)

    @property
    def active_pane(self) -> CommanderPane:
        return self.left_pane if self.active_pane_side == "left" else self.right_pane

    @property
    def inactive_pane(self) -> CommanderPane:
        return self.right_pane if self.active_pane_side == "left" else self.left_pane

    def switch_active_pane(self) -> None:
        if self.active_pane_side == "left":
            self.active_pane_side = "right"
            self.left_pane.set_active(False)
            self.right_pane.set_active(True)
        else:
            self.active_pane_side = "left"
            self.right_pane.set_active(False)
            self.left_pane.set_active(True)

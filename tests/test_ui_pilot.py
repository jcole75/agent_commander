"""UI tests using Textual headless pilot."""

import pytest
from agent_commander.models.platform import AgentPlatform
from agent_commander.ui.app import AgentCommanderApp
from agent_commander.ui.dialogs import (
    HelpDialog,
    PlatformSelectDialog,
    ActionResumeDialog,
    CopyConfirmDialog,
)


@pytest.mark.anyio
async def test_app_startup_and_tab_switch():
    app = AgentCommanderApp(
        left_platform=AgentPlatform.CODEX,
        right_platform=AgentPlatform.CLAUDE,
    )
    async with app.run_test() as pilot:
        commander = app.commander
        assert commander.active_pane_side == "left"
        assert commander.left_pane.is_active is True
        assert commander.right_pane.is_active is False

        # Press Tab to switch active pane to right
        await pilot.press("tab")
        assert commander.active_pane_side == "right"
        assert commander.left_pane.is_active is False
        assert commander.right_pane.is_active is True

        # Press Tab again to switch back to left
        await pilot.press("tab")
        assert commander.active_pane_side == "left"


@pytest.mark.anyio
async def test_tag_toggle_and_help():
    app = AgentCommanderApp(
        left_platform=AgentPlatform.CODEX,
        right_platform=AgentPlatform.CLAUDE,
    )
    async with app.run_test() as pilot:
        # Press Space to toggle tag on first item
        assert len(app.commander.active_pane.sessions) > 0
        first_session = app.commander.active_pane.filtered_sessions[0]
        initial_tag = first_session.tagged
        await pilot.press("space")
        assert first_session.tagged != initial_tag

        # Press F1 to open help dialog
        await pilot.press("f1")
        assert isinstance(app.screen, HelpDialog)

        # Press Esc to close help dialog
        await pilot.press("escape")
        assert not isinstance(app.screen, HelpDialog)


@pytest.mark.anyio
async def test_enter_action_resume_dialog():
    app = AgentCommanderApp(
        left_platform=AgentPlatform.CODEX,
        right_platform=AgentPlatform.CLAUDE,
    )
    async with app.run_test() as pilot:
        # Press Enter on active session
        await pilot.press("enter")
        assert isinstance(app.screen, ActionResumeDialog)

        # Press Esc to dismiss
        await pilot.press("escape")
        assert not isinstance(app.screen, ActionResumeDialog)


@pytest.mark.anyio
async def test_platform_switch_dialog():
    app = AgentCommanderApp(
        left_platform=AgentPlatform.CODEX,
        right_platform=AgentPlatform.CLAUDE,
    )
    async with app.run_test() as pilot:
        # Press F2 to open platform picker
        await pilot.press("f2")
        assert isinstance(app.screen, PlatformSelectDialog)

        # Press 4 for Grok
        await pilot.press("4")
        assert not isinstance(app.screen, PlatformSelectDialog)
        assert app.commander.left_pane.platform == AgentPlatform.GROK


@pytest.mark.anyio
async def test_copy_dialog_trigger():
    app = AgentCommanderApp(
        left_platform=AgentPlatform.CLAUDE,
        right_platform=AgentPlatform.CODEX,
    )
    async with app.run_test() as pilot:
        # Press F5 to trigger copy
        await pilot.press("f5")
        assert isinstance(app.screen, CopyConfirmDialog)

        # Press Esc to cancel
        await pilot.press("escape")
        assert not isinstance(app.screen, CopyConfirmDialog)

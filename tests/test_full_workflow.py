"""Full end-to-end user workflow test with Textual pilot."""

import pytest
from agent_commander.models.platform import AgentPlatform
from agent_commander.ui.app import AgentCommanderApp
from agent_commander.ui.dialogs import (
    CopyConfirmDialog,
    ActionResumeDialog,
    PlatformSelectDialog,
    HelpDialog,
)
from agent_commander.ui.viewer import ConversationViewer


@pytest.mark.anyio
async def test_full_user_workflow():
    app = AgentCommanderApp(
        left_platform=AgentPlatform.CODEX,
        right_platform=AgentPlatform.GROK,
    )
    async with app.run_test() as pilot:
        # 1. Startup verification
        assert app.commander.active_pane_side == "left"
        assert len(app.commander.left_pane.sessions) > 0
        assert len(app.commander.right_pane.sessions) > 0

        # 2. Switch to Right pane (Grok)
        await pilot.press("tab")
        assert app.commander.active_pane_side == "right"
        assert app.commander.right_pane.is_active is True

        # 3. Multi-select tagging on Right pane
        right_pane = app.commander.right_pane
        assert len(right_pane.filtered_sessions) >= 2
        await pilot.press("space")  # tags item 0, moves to item 1
        await pilot.press("space")  # tags item 1, moves to item 2
        tagged = [s for s in right_pane.sessions if s.tagged]
        assert len(tagged) == 2

        # 4. Trigger F5 Copy from Grok to Codex
        await pilot.press("f5")
        assert isinstance(app.screen, CopyConfirmDialog)
        copy_dialog = app.screen
        assert copy_dialog.source_platform == AgentPlatform.GROK
        assert copy_dialog.dest_platform == AgentPlatform.CODEX
        assert len(copy_dialog.sessions) == 2

        # Cancel dialog with Escape
        await pilot.press("escape")
        assert not isinstance(app.screen, CopyConfirmDialog)

        # 5. Untag all and tag single
        right_pane.untag_all()
        assert len([s for s in right_pane.sessions if s.tagged]) == 0

        # 6. Test F3 / View Conversation Screen
        await pilot.press("f3")
        assert isinstance(app.screen, ConversationViewer)
        viewer = app.screen
        assert viewer.session is not None
        assert len(viewer.session.messages) > 0

        # Dismiss viewer with Escape
        await pilot.press("escape")
        assert not isinstance(app.screen, ConversationViewer)

        # 7. Test Enter key Action Resume Dialog
        await pilot.press("enter")
        assert isinstance(app.screen, ActionResumeDialog)
        await pilot.press("escape")
        assert not isinstance(app.screen, ActionResumeDialog)

        # 8. Test F2 Platform Switching to Claude Code
        await pilot.press("f2")
        assert isinstance(app.screen, PlatformSelectDialog)
        await pilot.press("3")  # Platform 3 is Claude
        assert app.commander.right_pane.platform == AgentPlatform.CLAUDE
        assert len(app.commander.right_pane.sessions) > 0

        # 9. Test F2 Platform Switching to AGY
        await pilot.press("f2")
        await pilot.press("2")  # Platform 2 is AGY
        assert app.commander.right_pane.platform == AgentPlatform.AGY
        assert len(app.commander.right_pane.sessions) > 0

        # 10. Switch back to Left pane
        await pilot.press("tab")
        assert app.commander.active_pane_side == "left"

        # 11. Test Search Filter
        left_pane = app.commander.left_pane
        initial_count = len(left_pane.filtered_sessions)
        await pilot.press("f4")  # opens filter input
        left_pane.filter_query = "paperclips"
        left_pane._apply_filter()
        assert len(left_pane.filtered_sessions) <= initial_count

        # Clear filter
        left_pane.filter_query = ""
        left_pane._apply_filter()
        assert len(left_pane.filtered_sessions) == initial_count

        # 12. Test F1 Help Dialog
        await pilot.press("f1")
        assert isinstance(app.screen, HelpDialog)
        await pilot.press("escape")
        assert not isinstance(app.screen, HelpDialog)

"""Shared fixtures: every test runs against a fake home directory with sample sessions."""

from pathlib import Path
import shutil

import pytest

from agent_commander.adapters import registry

FIXTURE_HOME = Path(__file__).parent / "fixtures" / "home"


@pytest.fixture(autouse=True)
def agent_home(tmp_path, monkeypatch):
    """Point every platform at a throwaway copy of tests/fixtures/home."""
    home = tmp_path / "home"
    shutil.copytree(FIXTURE_HOME, home)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    # Archive/delete use file moves, not an installed agent CLI, unless a test opts in.
    monkeypatch.setenv("AC_NO_AGENT_CLI", "1")
    registry._INSTANCES.clear()
    yield home
    registry._INSTANCES.clear()

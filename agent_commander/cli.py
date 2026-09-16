"""CLI entrypoint for Agent Commander."""

from __future__ import annotations
import sys
import click

from agent_commander import __version__
from agent_commander.adapters.registry import get_adapter
from agent_commander.models.platform import AgentPlatform
from agent_commander.ui.app import AgentCommanderApp


@click.command(name="agent_commander", help="Orthodox dual-pane AI agent conversation manager.")
@click.option(
    "--left", "-l",
    type=click.Choice([p.value for p in AgentPlatform], case_sensitive=False),
    default="codex",
    show_default=True,
    help="Initial platform for the left pane.",
)
@click.option(
    "--right", "-r",
    type=click.Choice([p.value for p in AgentPlatform], case_sensitive=False),
    default="claude",
    show_default=True,
    help="Initial platform for the right pane.",
)
@click.option(
    "--list-platforms",
    is_flag=True,
    help="List all supported agent platforms and detected session counts on this machine.",
)
@click.version_option(version=__version__, prog_name="agent_commander")
def main(left: str, right: str, list_platforms: bool) -> None:
    """Launch Agent Commander or inspect platform stats."""
    if list_platforms:
        click.secho(f"Agent Commander v{__version__} - Discovered Agent Platforms:", bold=True, fg="cyan")
        click.echo("=" * 65)
        for p in AgentPlatform:
            adapter = get_adapter(p)
            try:
                sessions = adapter.scan_sessions(limit=500)
                count_str = f"{len(sessions)} session(s)"
            except Exception as e:
                count_str = f"Error scanning: {e}"

            cli_path = p.resolve_cli_path() or "Not found on PATH"
            click.secho(f"• {p.display_name:<22} [{p.value}]", bold=True, fg="yellow")
            click.echo(f"  Sessions Directory : {p.default_dir}")
            click.echo(f"  Sessions Detected  : {count_str}")
            click.echo(f"  Agent Executable   : {cli_path}")
            click.echo("")
        sys.exit(0)

    left_plat = AgentPlatform(left.lower())
    right_plat = AgentPlatform(right.lower())

    app = AgentCommanderApp(
        left_platform=left_plat,
        right_platform=right_plat,
    )
    app.run()


if __name__ == "__main__":
    main()

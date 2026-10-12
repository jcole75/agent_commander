"""CLI entrypoint for Agent Commander."""

from __future__ import annotations
from pathlib import Path
import sys
from typing import Optional

import click

from agent_commander import __version__
from agent_commander.adapters.registry import get_adapter
from agent_commander.converters.translator import SessionTranslator, export_path
from agent_commander.models.platform import AgentPlatform
from agent_commander.models.session import UnifiedSession

PLATFORM_CHOICE = click.Choice([p.value for p in AgentPlatform], case_sensitive=False)


def _find_session(session_id: str, platform: Optional[str], archived: bool = False) -> UnifiedSession:
    """Find a session by full id or unique id prefix, optionally on one platform."""
    platforms = [AgentPlatform(platform.lower())] if platform else list(AgentPlatform)
    matches = []
    for p in platforms:
        adapter = get_adapter(p)
        try:
            sessions = adapter.scan_archived_sessions(limit=10_000) if archived else adapter.scan_sessions(limit=10_000)
        except Exception:
            continue
        matches.extend(s for s in sessions if s.id == session_id or s.id.startswith(session_id))
    exact = [s for s in matches if s.id == session_id]
    if len(exact) == 1:
        return exact[0]
    if not matches:
        raise click.ClickException(f"No session matches '{session_id}'.")
    if len(matches) > 1:
        listed = ", ".join(f"{s.platform.value}:{s.id}" for s in matches[:5])
        raise click.ClickException(f"'{session_id}' matches several sessions ({listed}). Use more of the id or --from.")
    return matches[0]


@click.group(name="agent_commander", invoke_without_command=True,
             help="Orthodox dual-pane AI agent conversation manager. Run with no command to open the commander.")
@click.option("--left", "-l", type=PLATFORM_CHOICE, default="codex", show_default=True,
              help="Initial platform for the left pane.")
@click.option("--right", "-r", type=PLATFORM_CHOICE, default="claude", show_default=True,
              help="Initial platform for the right pane.")
@click.option("--list-platforms", is_flag=True,
              help="List all supported agent platforms and detected session counts on this machine.")
@click.version_option(version=__version__, prog_name="agent_commander")
@click.pass_context
def main(ctx: click.Context, left: str, right: str, list_platforms: bool) -> None:
    """Launch Agent Commander or inspect platform stats."""
    if ctx.invoked_subcommand:
        return
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

    from agent_commander.ui.app import AgentCommanderApp

    app = AgentCommanderApp(
        left_platform=AgentPlatform(left.lower()),
        right_platform=AgentPlatform(right.lower()),
    )
    app.run()


def _print_sessions(sessions: list[UnifiedSession]) -> None:
    for s in sessions:
        click.echo(f"{s.id}  {s.date_str}  {s.message_count:>4}  {s.title}")
    if not sessions:
        click.echo("No sessions found.")


@main.command(name="list")
@click.argument("platform", type=PLATFORM_CHOICE)
@click.option("--limit", "-n", default=30, show_default=True, help="How many sessions to show, newest first.")
@click.option("--archived", is_flag=True, help="List archived sessions instead.")
def list_sessions(platform: str, limit: int, archived: bool) -> None:
    """List sessions for PLATFORM (codex, claude, agy, grok)."""
    adapter = get_adapter(AgentPlatform(platform.lower()))
    _print_sessions(adapter.scan_archived_sessions(limit=limit) if archived else adapter.scan_sessions(limit=limit))


@main.command()
@click.argument("platform", type=PLATFORM_CHOICE)
@click.argument("text")
@click.option("--archived", is_flag=True, help="Search archived sessions instead.")
def search(platform: str, text: str, archived: bool) -> None:
    """List PLATFORM sessions whose conversation mentions TEXT (case-insensitive)."""
    adapter = get_adapter(AgentPlatform(platform.lower()))
    sessions = adapter.scan_archived_sessions(limit=10_000) if archived else adapter.scan_sessions(limit=10_000)
    _print_sessions([s for s in sessions if adapter.contains_text(s, text)])


@main.command()
@click.argument("session_id")
@click.option("--from", "source", type=PLATFORM_CHOICE, help="Only look for SESSION_ID on this platform.")
def archive(session_id: str, source: Optional[str]) -> None:
    """Move a session into the archive (undo with `restore`)."""
    session = _find_session(session_id, source)
    path = get_adapter(session.platform).archive_session(session)
    click.echo(f"Archived {session.platform.display_name} session {session.id} to {path}")


@main.command()
@click.argument("session_id")
@click.option("--from", "source", type=PLATFORM_CHOICE, help="Only look for SESSION_ID on this platform.")
def restore(session_id: str, source: Optional[str]) -> None:
    """Move an archived session back so its agent can resume it."""
    session = _find_session(session_id, source, archived=True)
    path = get_adapter(session.platform).restore_session(session)
    click.echo(f"Restored {session.platform.display_name} session {session.id} to {path}")


@main.command()
@click.argument("session_id")
@click.argument("title")
@click.option("--from", "source", type=PLATFORM_CHOICE, help="Only look for SESSION_ID on this platform.")
def rename(session_id: str, title: str, source: Optional[str]) -> None:
    """Give a session a new TITLE, shown by Agent Commander and by the agent itself."""
    session = _find_session(session_id, source)
    try:
        get_adapter(session.platform).rename_session(session, title)
    except NotImplementedError as e:
        raise click.ClickException(str(e))
    click.echo(f"Renamed {session.id} to \"{title}\"")


@main.command()
@click.argument("session_id")
@click.option("--to", "dest", type=PLATFORM_CHOICE, help="Platform to copy into as a native, resumable session.")
@click.option("--from", "source", type=PLATFORM_CHOICE, help="Only look for SESSION_ID on this platform.")
@click.option("--markdown", "-m", is_flag=True, help="Write a Markdown transcript instead of a native session.")
@click.option("--out", "-o", type=click.Path(path_type=Path), help="Markdown output file (with --markdown).")
def copy(session_id: str, dest: Optional[str], source: Optional[str], markdown: bool, out: Optional[Path]) -> None:
    """Copy a session to another agent, or to a Markdown transcript.

    SESSION_ID can be a unique prefix of the id shown by `list`.
    """
    if not markdown and not dest:
        raise click.UsageError("Give --to PLATFORM for a native copy, or --markdown for a transcript.")
    session = _find_session(session_id, source)
    if markdown:
        path = SessionTranslator.export_to_markdown(session, out or export_path(session))
        click.echo(f"Wrote {path}")
        return

    dest_platform = AgentPlatform(dest.lower())
    path = SessionTranslator.copy_session(session, dest_platform)
    copied = get_adapter(dest_platform)
    new_id = path.stem if dest_platform == AgentPlatform.CLAUDE else path.stem[-36:]
    click.echo(f"Copied {session.platform.display_name} session {session.id} to {dest_platform.display_name}:")
    click.echo(f"  {path}")
    resume = copied.get_resume_command(
        UnifiedSession(id=new_id, platform=dest_platform, title=session.title, raw_path=path)
    )
    if resume:
        where = f"cd {session.cwd} && " if session.cwd else ""
        click.echo(f"Resume it with: {where}{' '.join(resume)}")


@main.command()
@click.argument("session_id")
@click.option("--from", "source", type=PLATFORM_CHOICE, help="Only look for SESSION_ID on this platform.")
@click.option("--out", "-o", type=click.Path(path_type=Path), help="Output file.")
def export(session_id: str, source: Optional[str], out: Optional[Path]) -> None:
    """Export a session to a Markdown transcript (same as `copy --markdown`)."""
    session = _find_session(session_id, source)
    click.echo(f"Wrote {SessionTranslator.export_to_markdown(session, out or export_path(session))}")


if __name__ == "__main__":
    main()

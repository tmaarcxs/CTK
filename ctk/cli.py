"""CTK CLI commands."""

import subprocess
import sys
import time
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .core.config import get_config
from .core.metrics import MetricsDB, get_metrics
from .core.rewriter import COMMAND_CATEGORIES, should_rewrite_command
from .utils.filters import filter_output
from .utils.tokenizer import calculate_savings

console = Console()

# Context settings to allow passthrough of flags like -T, -e, etc.
CONTEXT_SETTINGS = {
    "ignore_unknown_options": True,
    "allow_extra_args": True,
    "allow_interspersed_args": True,
}

# Command registry - single source of truth for proxy commands
# Format: (group_path, command): (cmd_template, category)
# group_path can be:
#   - "" for top-level commands
#   - "group" for single-level groups (e.g., "git")
#   - "parent.child" for nested groups (e.g., "docker.compose")
COMMAND_REGISTRY = {
    # Docker commands
    ("docker", "ps"): ("docker ps ", "docker"),
    ("docker", "images"): ("docker images ", "docker"),
    ("docker", "logs"): ("docker logs ", "docker"),
    ("docker", "exec"): ("docker exec ", "docker"),
    ("docker", "run"): ("docker run ", "docker"),
    ("docker", "build"): ("docker build ", "docker"),
    ("docker", "network"): ("docker network ", "docker"),
    ("docker", "volume"): ("docker volume ", "docker"),
    ("docker", "system"): ("docker system ", "docker"),
    # Docker Compose commands (nested under docker)
    ("docker.compose", "ps"): ("docker compose ps ", "docker-compose"),
    ("docker.compose", "logs"): ("docker compose logs ", "docker-compose"),
    ("docker.compose", "up"): ("docker compose up ", "docker-compose"),
    ("docker.compose", "down"): ("docker compose down ", "docker-compose"),
    ("docker.compose", "exec"): ("docker compose exec ", "docker-compose"),
    ("docker.compose", "build"): ("docker compose build ", "docker-compose"),
    ("docker.compose", "restart"): ("docker compose restart ", "docker-compose"),
    ("docker.compose", "stop"): ("docker compose stop ", "docker-compose"),
    # Git commands
    ("git", "status"): ("git status ", "git"),
    ("git", "diff"): ("git diff ", "git-diff"),
    ("git", "log"): ("git log --oneline ", "git-log"),
    ("git", "add"): ("git add ", "git"),
    ("git", "commit"): ("git commit ", "git"),
    ("git", "push"): ("git push ", "git"),
    ("git", "pull"): ("git pull ", "git"),
    ("git", "branch"): ("git branch -a ", "git"),
    ("git", "remote"): ("git remote -v ", "git"),
    ("git", "stash"): ("git stash list ", "git"),
    ("git", "tag"): ("git tag ", "git"),
    ("git", "show"): ("git show --stat ", "git-log"),
    ("git", "fetch"): ("git fetch ", "git"),
    # File commands
    ("", "ls"): ("ls ", "files"),
    ("", "tree"): ("tree ", "files"),
    ("", "grep"): ("grep ", "files"),
    ("", "find"): ("find ", "files"),
    ("", "du"): ("du ", "files"),
    ("", "wc"): ("wc ", "files"),
    ("", "stat"): ("stat ", "files"),
    ("", "file"): ("file ", "files"),
    ("", "sed"): ("sed ", "files"),
    ("", "jq"): ("jq ", "files"),
    # Python commands
    ("", "pytest"): ("pytest  -q --tb=short 2>&1", "python"),
    ("", "ruff"): ("ruff ", "python"),
    ("", "pip"): ("pip ", "python"),
    # Node.js commands
    ("", "npm"): ("npm ", "nodejs"),
    ("", "pnpm"): ("pnpm ", "nodejs"),
    ("", "vitest"): ("npx vitest run --reporter=verbose 2>&1", "vitest"),
    ("", "tsc"): ("npx tsc --pretty 2>&1", "nodejs"),
    ("", "lint"): ("npx eslint --format compact 2>&1", "nodejs"),
    ("", "prettier"): ("npx prettier ", "nodejs"),
    # Network commands
    ("", "curl"): ("curl -s ", "network"),
    ("", "wget"): ("wget -q ", "network"),
    ("", "ip"): ("ip ", "network"),
    ("", "ss"): ("ss -tuln ", "network"),
    ("", "gh"): ("gh ", "gh"),
    # System commands
    ("", "ps"): ("ps aux --sort=-%mem | head -20", "system"),
    ("", "free"): ("free -h", "system"),
    ("", "df"): ("df -h ", "system"),
    ("", "uname"): ("uname -a", "system"),
    ("", "date"): ("date '+%Y-%m-%d %H:%M:%S'", "system"),
    ("", "env"): ("env | head -30", "system"),
    ("", "which"): ("which ", "system"),
    ("", "id"): ("id", "system"),
    ("", "pwd"): ("pwd", "system"),
    ("", "hostname"): ("hostname", "system"),
    ("", "uptime"): ("uptime", "system"),
    ("", "apt"): ("apt ", "system"),
    ("", "sqlite3"): ("sqlite3 ", "system"),
    ("", "alembic"): ("alembic ", "alembic"),
    ("", "uvicorn"): ("uvicorn ", "uvicorn"),
    ("", "make"): ("make ", "make"),
}


def _make_proxy_handler(cmd_template: str, category: str):
    """Factory function to create proxy command handlers."""

    def handler(args: tuple[str, ...] = ()):
        _run_command(cmd_template + " ".join(args), category)

    return handler


def _register_proxy_commands():
    """Register all proxy commands from the registry."""
    groups: dict[str, click.Group] = {}

    for (group_path, cmd_name), (cmd_template, category) in COMMAND_REGISTRY.items():
        # Handle nested groups (e.g., "docker.compose" -> ["docker", "compose"])
        group_parts = group_path.split(".") if group_path else []
        parent_group = None

        # Create group hierarchy if needed
        for i, part in enumerate(group_parts):
            full_path = ".".join(group_parts[: i + 1])
            if full_path not in groups:
                groups[full_path] = click.Group(
                    name=part,
                    context_settings=CONTEXT_SETTINGS,
                )
                # Add to parent group or CLI
                if parent_group:
                    parent_group.add_command(groups[full_path])
                else:
                    cli.add_command(groups[full_path], name=part)
            parent_group = groups[full_path]

        # Create command
        handler = _make_proxy_handler(cmd_template, category)
        handler = click.argument("args", nargs=-1)(handler)

        cmd = click.command(
            cmd_name,
            context_settings=CONTEXT_SETTINGS,
        )(handler)

        # Add to group or CLI
        if parent_group:
            parent_group.add_command(cmd)
        else:
            cli.add_command(cmd)


class ProxyVersionGroup(click.Group):
    """Custom Group that handles --version for CTK while passing it through to subcommands."""

    def main(self, args: list[str] | None = None, prog_name: str | None = None, **kwargs) -> None:  # type: ignore[override]
        """Override main to handle --version before Click processes it."""
        if args is None:
            args = sys.argv[1:]

        # Check if --version is the only argument (no subcommand)
        has_version = "--version" in args or "-v" in args
        has_subcommand = any(
            arg in self.commands for arg in args if not arg.startswith("-")
        )

        if has_version and not has_subcommand:
            click.echo("ctk, version 1.4.0")
            sys.exit(0)

        # Otherwise, let Click handle it normally (version flag will be passed to subcommand)
        super().main(args, prog_name, **kwargs)


@click.group(
    cls=ProxyVersionGroup,
    invoke_without_command=True,
    context_settings=CONTEXT_SETTINGS,
)
@click.pass_context
def cli(ctx: click.Context):
    """CTK - Claude Token Killer: Token-optimized CLI proxy.

    This tool runs shell commands as a proxy - subprocess usage is intentional.
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# Auto-register proxy commands from registry
_register_proxy_commands()


# ==================== Meta Commands ====================


@cli.command()
@click.option(
    "--history", is_flag=True, help="Show command history with detailed token info"
)
@click.option("--daily", is_flag=True, help="Show daily statistics")
@click.option("--weekly", is_flag=True, help="Show weekly statistics")
@click.option("--monthly", is_flag=True, help="Show monthly statistics")
@click.option("--top", "-t", default=10, help="Number of top commands to show")
@click.option("--export", type=click.Choice(["json", "csv"]), help="Export data")
@click.option("--output", "-o", type=click.Path(), help="Output file for export")
def gain(
    history: bool,
    daily: bool,
    weekly: bool,
    monthly: bool,
    top: int,
    export: str | None,
    output: str | None,
):
    """Show token savings summary and analytics."""
    metrics = get_metrics()

    if export:
        data = metrics.export(
            format=export, output_path=Path(output) if output else None
        )
        if not output:
            click.echo(data)
        console.print(
            f"[green]Exported to {output}[/green]"
            if output
            else "[green]Exported[/green]"
        )
        return

    if history:
        _show_history(metrics, detailed=True)
        return

    days = 30 if monthly else (7 if weekly else (1 if daily else 0))
    _show_summary(metrics, days, top)


def _show_summary(metrics: MetricsDB, days: int = 0, top: int = 10):
    """Display token savings summary with detailed analytics."""
    summary = metrics.get_summary(days=days)
    by_category = metrics.get_by_category(days=days)
    top_commands = metrics.get_top_commands(days=days, limit=top)
    top_savers = metrics.get_top_savers(days=days, limit=top)

    period = "all time" if days == 0 else f"last {days} day{'s' if days > 1 else ''}"

    console.print(
        Panel(f"[bold cyan]Token Savings Summary ({period})[/bold cyan]", expand=False)
    )

    # Overall statistics with before/after tokens
    console.print("\n[bold]Overall Statistics[/bold]")
    console.print(f"  Commands tracked: {summary['total_commands']:,}")
    console.print(f"  Commands rewritten: {summary['rewritten_commands']:,}")

    # Token breakdown
    console.print("\n[bold]Token Breakdown[/bold]")
    orig = summary["total_original_tokens"]
    filt = summary["total_filtered_tokens"]
    saved = summary["total_tokens_saved"]
    pct = summary["avg_savings_percent"]

    console.print(f"  Tokens before: [yellow]{orig:,}[/yellow]")
    console.print(f"  Tokens after:  [cyan]{filt:,}[/cyan]")
    console.print(f"  Tokens saved:  [green]{saved:,}[/green] ({pct}%)")

    if summary["max_tokens_saved"] > 0:
        console.print(
            f"\n  Max saved (single cmd): [green]{summary['max_tokens_saved']:,}[/green]"
        )

    # By category
    if by_category:
        console.print("\n[bold]By Category[/bold]")
        table = Table(show_header=True, header_style="bold")
        table.add_column("Category")
        table.add_column("Commands", justify="right")
        table.add_column("Before", justify="right")
        table.add_column("After", justify="right")
        table.add_column("Saved", justify="right")
        table.add_column("%", justify="right")

        for cat, stats in sorted(
            by_category.items(), key=lambda x: x[1]["tokens_saved"], reverse=True
        ):
            table.add_row(
                cat,
                str(stats["count"]),
                f"{stats.get('original_tokens', 0):,}",
                f"{stats.get('filtered_tokens', 0):,}",
                f"[green]{stats['tokens_saved']:,}[/green]",
                f"{stats['avg_savings_percent']}%",
            )

        console.print(table)

    # Top used commands
    if top_commands:
        console.print(f"\n[bold]Top {top} Commands (by usage)[/bold]")
        table = Table(show_header=True, header_style="bold")
        table.add_column("#", justify="right", width=3)
        table.add_column("Command")
        table.add_column("Count", justify="right")
        table.add_column("Before", justify="right")
        table.add_column("After", justify="right")
        table.add_column("Saved", justify="right")
        table.add_column("%", justify="right")

        for i, cmd in enumerate(top_commands, 1):
            orig_cmd = cmd["original_command"]
            if len(orig_cmd) > 35:
                orig_cmd = orig_cmd[:32] + "..."

            saved_pct = cmd["avg_savings"] or 0
            color = (
                "green"
                if saved_pct >= 50
                else ("yellow" if saved_pct >= 25 else "white")
            )

            table.add_row(
                str(i),
                orig_cmd,
                str(cmd["count"]),
                f"{cmd.get('original_tokens', 0):,}",
                f"{cmd.get('filtered_tokens', 0):,}",
                f"[{color}]{cmd['tokens_saved'] or 0:,}[/{color}]",
                f"{saved_pct:.1f}%",
            )

        console.print(table)

    # Top savers
    if top_savers and top_savers != top_commands:
        console.print(f"\n[bold]Top {top} Token Savers[/bold]")
        table = Table(show_header=True, header_style="bold")
        table.add_column("#", justify="right", width=3)
        table.add_column("Command")
        table.add_column("Count", justify="right")
        table.add_column("Total Saved", justify="right")
        table.add_column("Avg %", justify="right")

        for i, cmd in enumerate(top_savers, 1):
            orig_cmd = cmd["original_command"]
            if len(orig_cmd) > 45:
                orig_cmd = orig_cmd[:42] + "..."

            table.add_row(
                str(i),
                orig_cmd,
                str(cmd["count"]),
                f"[green]{cmd['tokens_saved'] or 0:,}[/green]",
                f"{cmd['avg_savings'] or 0:.1f}%",
            )

        console.print(table)

    daily_stats = metrics.get_daily_stats(days=7)
    if daily_stats:
        console.print("\n[bold]Daily Breakdown (Last 7 Days)[/bold]")
        table = Table(show_header=True, header_style="bold")
        table.add_column("Date")
        table.add_column("Commands", justify="right")
        table.add_column("Tokens Saved", justify="right")
        table.add_column("Avg %", justify="right")

        for stat in daily_stats:
            table.add_row(
                stat["date"],
                str(stat["commands"]),
                f"[green]{stat['tokens_saved'] or 0:,}[/green]",
                f"{stat['avg_savings'] or 0:.1f}%",
            )

        console.print(table)


def _show_history(metrics: MetricsDB, limit: int = 20, detailed: bool = False):
    """Display command history with optional detailed token info."""
    history = metrics.get_history(limit=limit)

    if not history:
        console.print("[yellow]No command history found[/yellow]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Time")
    table.add_column("Category")
    table.add_column("Command")
    if detailed:
        table.add_column("Before", justify="right")
        table.add_column("After", justify="right")
    table.add_column("Saved", justify="right")
    if detailed:
        table.add_column("%", justify="right")

    for entry in history:
        cmd = entry["original_command"]
        if len(cmd) > 35:
            cmd = cmd[:32] + "..."

        row = [
            entry["timestamp"][:19] if entry["timestamp"] else "",
            entry["category"] or "",
            cmd,
        ]

        if detailed:
            row.extend(
                [
                    str(entry.get("original_tokens", 0)),
                    str(entry.get("filtered_tokens", 0)),
                ]
            )

        row.append(f"[green]{entry['tokens_saved'] or 0}[/green]")

        if detailed:
            pct = entry.get("savings_percent", 0) or 0
            row.append(f"{pct:.1f}%")

        table.add_row(*row)

    console.print(table)


@cli.command()
@click.option("--all", "show_all", is_flag=True, help="Show all missed opportunities")
def discover(show_all: bool):
    """Analyze Claude Code history for missed optimization opportunities."""
    console.print(
        "[cyan]Analyzing Claude Code history for missed opportunities...[/cyan]"
    )

    history_paths = [
        Path.home() / ".claude" / "projects",
        Path.home() / ".config" / "claude" / "projects",
    ]

    found = False
    for base_path in history_paths:
        if base_path.exists():
            found = True
            _analyze_history_dir(base_path, show_all)

    if not found:
        console.print("[yellow]No Claude Code history found[/yellow]")


def _analyze_history_dir(base_path: Path, show_all: bool):
    """Analyze Claude Code history directory for missed opportunities."""
    import json
    from collections import Counter

    missed = Counter()

    for jsonl_file in base_path.rglob("*.jsonl"):
        try:
            with open(jsonl_file) as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        if data.get("type") == "human":
                            msg = data.get("message", "")
                            for category, cat_config in COMMAND_CATEGORIES.items():
                                for pattern, _ in cat_config.patterns:
                                    import re

                                    if re.search(pattern, msg):
                                        result = should_rewrite_command(msg)
                                        if not result.should_rewrite:
                                            missed[category] += 1
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

    if missed:
        console.print("\n[bold]Potential missed opportunities by category:[/bold]")
        limit = None if show_all else 10
        for cat, count in missed.most_common(limit):
            console.print(f"  {cat}: {count} commands")
    else:
        console.print("[green]No significant missed opportunities found[/green]")


@cli.command("proxy")
@click.argument("command", nargs=-1, required=True)
def proxy_command(command: tuple[str, ...]):
    """Execute command without filtering but track usage."""
    cmd_str = " ".join(command)
    metrics = get_metrics()

    start = time.time()
    result = subprocess.run(
        cmd_str, shell=True
    )  # noqa: S602 - intentional for CLI proxy
    exec_time = int((time.time() - start) * 1000)

    metrics.record(
        original_command=cmd_str,
        rewritten_command=None,
        category="proxy",
        exec_time_ms=exec_time,
    )

    sys.exit(result.returncode)


# ==================== Utility Functions ====================


def _run_command(cmd: str, category: str):
    """Run a command and track metrics.

    Also runs the raw equivalent command to measure actual token savings.
    """
    metrics = get_metrics()

    # Determine the raw command (what would have run without CTK)
    raw_cmd = _get_raw_command(cmd, category)

    # Run raw command first to measure original output size
    raw_output = ""
    if raw_cmd and raw_cmd != cmd:
        try:
            raw_result = subprocess.run(
                raw_cmd, shell=True, capture_output=True, text=True, timeout=5
            )  # noqa: S602
            raw_output = raw_result.stdout + raw_result.stderr
        except Exception:
            raw_output = ""

    # Run the CTK-optimized command
    start = time.time()
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True
    )  # noqa: S602 - intentional for CLI proxy
    exec_time = int((time.time() - start) * 1000)

    output = result.stdout + result.stderr
    filtered = filter_output(output, category)

    # Calculate savings: compare raw output vs CTK filtered output
    if raw_output:
        savings = calculate_savings(raw_output, filtered)
    else:
        # Fallback: compare before/after filtering
        savings = calculate_savings(output, filtered)

    click.echo(filtered)

    metrics.record(
        original_command=raw_cmd or cmd,
        rewritten_command=f"ctk {cmd}",
        category=category,
        exec_time_ms=exec_time,
        original_tokens=savings["original_tokens"],
        filtered_tokens=savings["filtered_tokens"],
        tokens_saved=savings["tokens_saved"],
        savings_percent=savings["savings_percent"],
    )

    sys.exit(result.returncode)


def _get_raw_command(ctk_cmd: str, category: str) -> str:
    """Get the raw command equivalent for a CTK command.

    This is used to measure actual token savings by running both
    the raw command and the CTK version.
    """
    # Commands that are identical (filtering only, no modification)
    identical_cmds = {
        "whoami",
        "hostname",
        "id",
        "uname -a",
    }

    if ctk_cmd in identical_cmds:
        return ""  # No savings from command modification, only from filtering

    # Commands with compact flags
    compact_map = {
        "git log --oneline": "git log",
        "git status -s": "git status",
        "docker ps --format table": "docker ps",
        "free -h": "free",
        "df -h": "df",
    }

    for ctk, raw in compact_map.items():
        if ctk_cmd.startswith(ctk):
            return ctk_cmd.replace(ctk, raw)

    # Partial matches for commands that add compact flags
    if ctk_cmd.startswith("git log --oneline"):
        return ctk_cmd.replace(" --oneline", "")
    if ctk_cmd.startswith("docker compose logs "):
        return ctk_cmd  # Same command, filtering only
    if ctk_cmd.startswith("npm "):
        return ctk_cmd  # Same command, filtering only
    if ctk_cmd.startswith("pnpm "):
        return ctk_cmd  # Same command, filtering only
    if "pytest" in ctk_cmd and "-q" in ctk_cmd:
        return ctk_cmd.replace(" -q", "").replace(" --tb=short", "")
    if "tail -5" in ctk_cmd and "ping" in ctk_cmd:
        # ping with tail gets only summary
        return ctk_cmd.replace(" 2>&1 | tail -5", "")

    return ""  # No raw equivalent - use CTK output as baseline


# ==================== Custom Commands (with special options) ====================


@cli.command("read")
@click.argument("file", type=click.Path(exists=True))
@click.option("--max-lines", "-n", default=100, help="Maximum lines to show")
def read_command(file: str, max_lines: int):
    """Read file with filtering."""
    _run_command(f"head -{max_lines} {file}", "files")


@cli.command("tail")
@click.argument("file", type=click.Path(exists=True))
@click.option("--lines", "-n", default=20, help="Number of lines")
def tail_command(file: str, lines: int):
    """File tail (limited)."""
    _run_command(f"tail -{lines} {file}", "files")


@cli.command("cat")
@click.argument("file", type=click.Path(exists=True))
@click.option("--max-lines", "-n", default=100, help="Maximum lines")
def cat_command(file: str, max_lines: int):
    """Cat with line limit (alias for read)."""
    _run_command(f"head -{max_lines} {file}", "files")


@cli.command("ping")
@click.argument("host")
@click.option("--count", "-c", default=3, help="Ping count")
def ping_command(host: str, count: int):
    """Ping with limited output."""
    _run_command(f"ping -c {count} {host} 2>&1 | tail -5", "network")


@cli.command("config")
@click.option("--show", is_flag=True, help="Show current configuration")
@click.option("--init", is_flag=True, help="Initialize configuration file")
def config_command(show: bool, init: bool):
    """Manage CTK configuration."""
    config = get_config()

    if init:
        config.save()
        console.print(f"[green]Configuration saved to {config.config_path}[/green]")
        return

    console.print(f"[bold]Configuration file:[/bold] {config.config_path}")
    console.print(f"[bold]Database:[/bold] {config.database_path}")
    console.print("\n[bold]Enabled commands:[/bold]")
    for cat, cmds in config._config.get("commands", {}).items():
        if isinstance(cmds, dict) and cmds.get("enabled"):
            console.print(f"  {cat}: enabled")

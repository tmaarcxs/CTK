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
from .core.rewriter import COMMAND_PATTERNS, should_rewrite_command
from .utils.output_filter import filter_output
from .utils.tokenizer import calculate_savings

console = Console()

# Context settings to allow passthrough of flags like -T, -e, etc.
CONTEXT_SETTINGS = {"ignore_unknown_options": True}


@click.group(invoke_without_command=True, context_settings=CONTEXT_SETTINGS)
@click.pass_context
@click.version_option(version="1.0.0", prog_name="ctk")
def cli(ctx: click.Context):
    """CTK - Claude Token Killer: Token-optimized CLI proxy.

    This tool runs shell commands as a proxy - subprocess usage is intentional.
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# ==================== Meta Commands ====================

@cli.command()
@click.option("--history", is_flag=True, help="Show command history with detailed token info")
@click.option("--daily", is_flag=True, help="Show daily statistics")
@click.option("--weekly", is_flag=True, help="Show weekly statistics")
@click.option("--monthly", is_flag=True, help="Show monthly statistics")
@click.option("--top", "-t", default=10, help="Number of top commands to show")
@click.option("--export", type=click.Choice(["json", "csv"]), help="Export data")
@click.option("--output", "-o", type=click.Path(), help="Output file for export")
def gain(history: bool, daily: bool, weekly: bool, monthly: bool,
         top: int, export: str | None, output: str | None):
    """Show token savings summary and analytics."""
    metrics = get_metrics()

    if export:
        data = metrics.export(format=export, output_path=Path(output) if output else None)
        if not output:
            click.echo(data)
        console.print(f"[green]Exported to {output}[/green]" if output else "[green]Exported[/green]")
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

    console.print(Panel(f"[bold cyan]Token Savings Summary ({period})[/bold cyan]", expand=False))

    # Overall statistics with before/after tokens
    console.print("\n[bold]Overall Statistics[/bold]")
    console.print(f"  Commands tracked: {summary['total_commands']:,}")
    console.print(f"  Commands rewritten: {summary['rewritten_commands']:,}")

    # Token breakdown
    console.print("\n[bold]Token Breakdown[/bold]")
    orig = summary['total_original_tokens']
    filt = summary['total_filtered_tokens']
    saved = summary['total_tokens_saved']
    pct = summary['avg_savings_percent']

    # Visual bar for savings
    if orig > 0:
        bar_len = 30
        saved_ratio = min(saved / orig, 1.0) if orig > 0 else 0
        saved_bar = int(bar_len * saved_ratio)
        bar_visual = "[green]" + "█" * saved_bar + "[/green]" + "░" * (bar_len - saved_bar)
    else:
        bar_visual = "░" * 30

    console.print(f"  Tokens before: [yellow]{orig:,}[/yellow]")
    console.print(f"  Tokens after:  [cyan]{filt:,}[/cyan]")
    console.print(f"  Tokens saved:  [green]{saved:,}[/green] ({pct}%)")
    console.print(f"  Savings bar:   {bar_visual}")

    if summary['max_tokens_saved'] > 0:
        console.print(f"\n  Max saved (single cmd): [green]{summary['max_tokens_saved']:,}[/green]")

    # By category with visual bars
    if by_category:
        console.print("\n[bold]By Category[/bold]")
        table = Table(show_header=True, header_style="bold")
        table.add_column("Category")
        table.add_column("Commands", justify="right")
        table.add_column("Before", justify="right")
        table.add_column("After", justify="right")
        table.add_column("Saved", justify="right")
        table.add_column("%", justify="right")
        table.add_column("Visual", justify="left")

        max_saved = max((s["tokens_saved"] for s in by_category.values()), default=0) or 1

        for cat, stats in sorted(by_category.items(), key=lambda x: x[1]["tokens_saved"], reverse=True):
            bar_len = 15
            saved_ratio = stats["tokens_saved"] / max_saved if max_saved > 0 else 0
            saved_bar = int(bar_len * saved_ratio)
            bar_visual = "[green]" + "█" * saved_bar + "[/green]" + "░" * (bar_len - saved_bar)

            table.add_row(
                cat,
                str(stats["count"]),
                f"{stats.get('original_tokens', 0):,}",
                f"{stats.get('filtered_tokens', 0):,}",
                f"[green]{stats['tokens_saved']:,}[/green]",
                f"{stats['avg_savings_percent']}%",
                bar_visual
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
            color = "green" if saved_pct >= 50 else ("yellow" if saved_pct >= 25 else "white")

            table.add_row(
                str(i),
                orig_cmd,
                str(cmd["count"]),
                f"{cmd.get('original_tokens', 0):,}",
                f"{cmd.get('filtered_tokens', 0):,}",
                f"[{color}]{cmd['tokens_saved'] or 0:,}[/{color}]",
                f"{saved_pct:.1f}%"
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
                f"{cmd['avg_savings'] or 0:.1f}%"
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
                f"{stat['avg_savings'] or 0:.1f}%"
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
            row.extend([
                str(entry.get("original_tokens", 0)),
                str(entry.get("filtered_tokens", 0)),
            ])

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
    console.print("[cyan]Analyzing Claude Code history for missed opportunities...[/cyan]")

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
                            for category, config in COMMAND_PATTERNS.items():
                                for pattern, _ in config["patterns"]:
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
    result = subprocess.run(cmd_str, shell=True)  # noqa: S602 - intentional for CLI proxy
    exec_time = int((time.time() - start) * 1000)

    metrics.record(
        original_command=cmd_str,
        rewritten_command=None,
        category="proxy",
        exec_time_ms=exec_time,
    )

    sys.exit(result.returncode)


# ==================== Docker Commands ====================

@cli.group(context_settings=CONTEXT_SETTINGS)
def docker():
    """Docker commands with compact output."""
    pass


@docker.command("ps")
@click.argument("args", nargs=-1)
def docker_ps(args: tuple[str, ...]):
    """Compact container listing."""
    _run_command("docker ps " + " ".join(args), "docker")


@docker.command("images")
@click.argument("args", nargs=-1)
def docker_images(args: tuple[str, ...]):
    """Compact image listing."""
    _run_command("docker images " + " ".join(args), "docker")


@docker.command("logs")
@click.argument("args", nargs=-1)
def docker_logs(args: tuple[str, ...]):
    """Deduplicated log output."""
    _run_command("docker logs " + " ".join(args), "docker")


@docker.command("exec")
@click.argument("args", nargs=-1)
def docker_exec(args: tuple[str, ...]):
    """Execute command in container."""
    _run_command("docker exec " + " ".join(args), "docker")


@docker.command("run")
@click.argument("args", nargs=-1)
def docker_run(args: tuple[str, ...]):
    """Run container with compact output."""
    _run_command("docker run " + " ".join(args), "docker")


@docker.command("build")
@click.argument("args", nargs=-1)
def docker_build(args: tuple[str, ...]):
    """Build image with compact output."""
    _run_command("docker build " + " ".join(args), "docker")


# Docker Compose group
@docker.group("compose", context_settings=CONTEXT_SETTINGS)
def docker_compose():
    """Docker Compose commands."""
    pass


@docker_compose.command("ps", context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1)
def compose_ps(args: tuple[str, ...]):
    """Compact compose container listing."""
    _run_command("docker compose ps " + " ".join(args), "docker-compose")


@docker_compose.command("logs", context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1)
def compose_logs(args: tuple[str, ...]):
    """Deduplicated compose logs."""
    _run_command("docker compose logs " + " ".join(args), "docker-compose")


@docker_compose.command("up", context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1)
def compose_up(args: tuple[str, ...]):
    """Start services with summary."""
    _run_command("docker compose up " + " ".join(args), "docker-compose")


@docker_compose.command("down", context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1)
def compose_down(args: tuple[str, ...]):
    """Stop services with summary."""
    _run_command("docker compose down " + " ".join(args), "docker-compose")


@docker_compose.command("exec", context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1)
def compose_exec(args: tuple[str, ...]):
    """Execute in compose service."""
    _run_command("docker compose exec " + " ".join(args), "docker-compose")


# ==================== Git Commands ====================

@cli.group(context_settings=CONTEXT_SETTINGS)
def git():
    """Git commands with compact output."""
    pass


@git.command("status")
@click.argument("args", nargs=-1)
def git_status(args: tuple[str, ...]):
    """Compact status output."""
    _run_command("git status " + " ".join(args), "git")


@git.command("diff")
@click.argument("args", nargs=-1)
def git_diff(args: tuple[str, ...]):
    """Ultra-condensed diff."""
    _run_command("git diff " + " ".join(args), "git")


@git.command("log")
@click.argument("args", nargs=-1)
def git_log(args: tuple[str, ...]):
    """Compact log output."""
    _run_command("git log --oneline " + " ".join(args), "git")


@git.command("add")
@click.argument("args", nargs=-1)
def git_add(args: tuple[str, ...]):
    """Stage files."""
    _run_command("git add " + " ".join(args), "git")


@git.command("commit")
@click.argument("args", nargs=-1)
def git_commit(args: tuple[str, ...]):
    """Commit changes."""
    _run_command("git commit " + " ".join(args), "git")


@git.command("push")
@click.argument("args", nargs=-1)
def git_push(args: tuple[str, ...]):
    """Push changes."""
    _run_command("git push " + " ".join(args), "git")


@git.command("pull")
@click.argument("args", nargs=-1)
def git_pull(args: tuple[str, ...]):
    """Pull changes."""
    _run_command("git pull " + " ".join(args), "git")


# ==================== System Commands ====================

@cli.command("ps")
@click.argument("args", nargs=-1)
def ps_command(args: tuple[str, ...]):
    """Top processes by CPU/memory."""
    _run_command("ps aux --sort=-%mem | head -20", "system")


@cli.command("free")
@click.argument("args", nargs=-1)
def free_command(args: tuple[str, ...]):
    """Single line memory summary."""
    _run_command("free -h", "system")


@cli.command("date")
@click.argument("args", nargs=-1)
def date_command(args: tuple[str, ...]):
    """Compact date output."""
    _run_command("date '+%Y-%m-%d %H:%M:%S'", "system")


@cli.command("whoami")
def whoami_command():
    """Current user."""
    _run_command("whoami", "system")


# ==================== File Commands ====================

@cli.command("ls")
@click.argument("args", nargs=-1)
def ls_command(args: tuple[str, ...]):
    """Compact directory listing."""
    args_str = " ".join(args) if args else "-1"
    _run_command(f"ls {args_str}", "files")


@cli.command("tree")
@click.argument("args", nargs=-1)
def tree_command(args: tuple[str, ...]):
    """Compact tree output."""
    _run_command("tree " + " ".join(args), "files")


@cli.command("read")
@click.argument("file", type=click.Path(exists=True))
@click.option("--max-lines", "-n", default=100, help="Maximum lines to show")
def read_command(file: str, max_lines: int):
    """Read file with filtering."""
    _run_command(f"head -{max_lines} {file}", "files")


@cli.command("grep")
@click.argument("args", nargs=-1)
def grep_command(args: tuple[str, ...]):
    """Compact grep output."""
    _run_command("grep " + " ".join(args), "files")


@cli.command("find")
@click.argument("args", nargs=-1)
def find_command(args: tuple[str, ...]):
    """Compact find output."""
    _run_command("find " + " ".join(args), "files")


@cli.command("du")
@click.argument("args", nargs=-1)
def du_command(args: tuple[str, ...]):
    """Disk usage summary."""
    args_str = " ".join(args) if args else "-sh ."
    _run_command(f"du {args_str}", "files")


# ==================== Python Commands ====================

@cli.command("pytest")
@click.argument("args", nargs=-1)
def pytest_command(args: tuple[str, ...]):
    """Pytest with compact output."""
    args_str = " ".join(args) if args else ""
    _run_command(f"pytest {args_str} -q --tb=short 2>&1", "python")


@cli.command("ruff")
@click.argument("args", nargs=-1)
def ruff_command(args: tuple[str, ...]):
    """Ruff with compact output."""
    _run_command("ruff " + " ".join(args), "python")


@cli.command("pip")
@click.argument("args", nargs=-1)
def pip_command(args: tuple[str, ...]):
    """Pip with compact output."""
    _run_command("pip " + " ".join(args), "python")


# ==================== Node.js Commands ====================

@cli.command("npm")
@click.argument("args", nargs=-1)
def npm_command(args: tuple[str, ...]):
    """npm with filtered output."""
    _run_command("npm " + " ".join(args), "nodejs")


@cli.command("pnpm")
@click.argument("args", nargs=-1)
def pnpm_command(args: tuple[str, ...]):
    """pnpm with compact output."""
    _run_command("pnpm " + " ".join(args), "nodejs")


@cli.command("vitest")
@click.argument("args", nargs=-1)
def vitest_command(args: tuple[str, ...]):
    """Vitest with compact output."""
    _run_command("npx vitest run --reporter=verbose 2>&1", "nodejs")


@cli.command("tsc")
@click.argument("args", nargs=-1)
def tsc_command(args: tuple[str, ...]):
    """TypeScript compiler with grouped errors."""
    _run_command("npx tsc --pretty 2>&1", "nodejs")


@cli.command("lint")
@click.argument("args", nargs=-1)
def lint_command(args: tuple[str, ...]):
    """ESLint with grouped violations."""
    _run_command("npx eslint --format compact 2>&1", "nodejs")


@cli.command("prettier")
@click.argument("args", nargs=-1)
def prettier_command(args: tuple[str, ...]):
    """Prettier with compact output."""
    _run_command("npx prettier " + " ".join(args), "nodejs")


# ==================== Kubernetes Commands ====================

@cli.group(context_settings=CONTEXT_SETTINGS)
def kubectl():
    """Kubectl commands with compact output."""
    pass


@kubectl.command("get")
@click.argument("args", nargs=-1)
def kubectl_get(args: tuple[str, ...]):
    """Get resources."""
    _run_command("kubectl get " + " ".join(args), "kubernetes")


@kubectl.command("logs")
@click.argument("args", nargs=-1)
def kubectl_logs(args: tuple[str, ...]):
    """Pod logs."""
    _run_command("kubectl logs " + " ".join(args), "kubernetes")


@kubectl.command("describe")
@click.argument("args", nargs=-1)
def kubectl_describe(args: tuple[str, ...]):
    """Describe resource."""
    _run_command("kubectl describe " + " ".join(args), "kubernetes")


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
            raw_result = subprocess.run(raw_cmd, shell=True, capture_output=True, text=True, timeout=5)  # noqa: S602
            raw_output = raw_result.stdout + raw_result.stderr
        except Exception:
            raw_output = ""

    # Run the CTK-optimized command
    start = time.time()
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)  # noqa: S602 - intentional for CLI proxy
    exec_time = int((time.time() - start) * 1000)

    output = result.stdout + result.stderr
    filtered = _filter_output(output, category)

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
        "whoami", "hostname", "id", "uname -a",
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

# Alias for backward compatibility with tests
_filter_output = filter_output




# ==================== Additional Commands ====================

@cli.command("gh")
@click.argument("args", nargs=-1)
def gh_command(args: tuple[str, ...]):
    """GitHub CLI with compact output."""
    _run_command("gh " + " ".join(args), "gh")


@cli.command("cargo")
@click.argument("args", nargs=-1)
def cargo_command(args: tuple[str, ...]):
    """Cargo with compact output."""
    _run_command("cargo " + " ".join(args), "rust")


@cli.command("go")
@click.argument("args", nargs=-1)
def go_command(args: tuple[str, ...]):
    """Go commands with compact output."""
    _run_command("go " + " ".join(args), "go")


@cli.command("curl")
@click.argument("args", nargs=-1)
def curl_command(args: tuple[str, ...]):
    """Curl with auto-JSON detection."""
    _run_command("curl -s " + " ".join(args), "network")


@cli.command("wget")
@click.argument("args", nargs=-1)
def wget_command(args: tuple[str, ...]):
    """Wget with compact output."""
    _run_command("wget -q " + " ".join(args), "network")


# ==================== Extended System Commands ====================

@cli.command("df")
@click.argument("args", nargs=-1)
def df_command(args: tuple[str, ...]):
    """Disk space summary."""
    _run_command("df -h " + " ".join(args), "system")


@cli.command("uname")
@click.argument("args", nargs=-1)
def uname_command(args: tuple[str, ...]):
    """System info."""
    _run_command("uname -a", "system")


@cli.command("hostname")
def hostname_command():
    """Hostname."""
    _run_command("hostname", "system")


@cli.command("uptime")
def uptime_command():
    """System uptime."""
    _run_command("uptime", "system")


@cli.command("env")
@click.argument("args", nargs=-1)
def env_command(args: tuple[str, ...]):
    """Environment variables (filtered)."""
    if args:
        _run_command("env | grep -i " + " ".join(args), "system")
    else:
        _run_command("env | head -30", "system")


@cli.command("which")
@click.argument("args", nargs=-1)
def which_command(args: tuple[str, ...]):
    """Find command location."""
    _run_command("which " + " ".join(args), "system")


@cli.command("history")
@click.argument("args", nargs=-1)
def history_command(args: tuple[str, ...]):
    """Command history (limited)."""
    n = args[0] if args else "20"
    _run_command(f"history {n} 2>/dev/null || fc -l -{n}", "system")


@cli.command("id")
def id_command():
    """User/group IDs."""
    _run_command("id", "system")


# ==================== Extended File Commands ====================

@cli.command("tail")
@click.argument("file", type=click.Path(exists=True))
@click.option("--lines", "-n", default=20, help="Number of lines")
def tail_command(file: str, lines: int):
    """File tail (limited)."""
    _run_command(f"tail -{lines} {file}", "files")


@cli.command("wc")
@click.argument("args", nargs=-1)
def wc_command(args: tuple[str, ...]):
    """Word/line count."""
    _run_command("wc " + " ".join(args), "files")


@cli.command("stat")
@click.argument("args", nargs=-1)
def stat_command(args: tuple[str, ...]):
    """File status."""
    _run_command("stat " + " ".join(args), "files")


@cli.command("file")
@click.argument("args", nargs=-1)
def file_command(args: tuple[str, ...]):
    """File type."""
    _run_command("file " + " ".join(args), "files")


@cli.command("cat")
@click.argument("file", type=click.Path(exists=True))
@click.option("--max-lines", "-n", default=100, help="Maximum lines")
def cat_command(file: str, max_lines: int):
    """Cat with line limit (alias for read)."""
    _run_command(f"head -{max_lines} {file}", "files")


# ==================== Extended Docker Commands ====================

@docker.command("network")
@click.argument("args", nargs=-1)
def docker_network(args: tuple[str, ...]):
    """Docker network commands."""
    _run_command("docker network " + " ".join(args), "docker")


@docker.command("volume")
@click.argument("args", nargs=-1)
def docker_volume(args: tuple[str, ...]):
    """Docker volume commands."""
    _run_command("docker volume " + " ".join(args), "docker")


@docker.command("system")
@click.argument("args", nargs=-1)
def docker_system(args: tuple[str, ...]):
    """Docker system commands."""
    _run_command("docker system " + " ".join(args), "docker")


# ==================== Extended Git Commands ====================

@git.command("branch")
@click.argument("args", nargs=-1)
def git_branch(args: tuple[str, ...]):
    """List branches."""
    _run_command("git branch -a " + " ".join(args), "git")


@git.command("remote")
@click.argument("args", nargs=-1)
def git_remote(args: tuple[str, ...]):
    """Remote info."""
    _run_command("git remote -v " + " ".join(args), "git")


@git.command("stash")
@click.argument("args", nargs=-1)
def git_stash(args: tuple[str, ...]):
    """Stash operations."""
    _run_command("git stash list " + " ".join(args), "git")


@git.command("tag")
@click.argument("args", nargs=-1)
def git_tag(args: tuple[str, ...]):
    """Tag list."""
    _run_command("git tag " + " ".join(args), "git")


# ==================== Network Commands ====================

@cli.command("ip")
@click.argument("args", nargs=-1)
def ip_command(args: tuple[str, ...]):
    """IP/network info."""
    _run_command("ip " + " ".join(args), "network")


@cli.command("ss")
@click.argument("args", nargs=-1)
def ss_command(args: tuple[str, ...]):
    """Socket stats."""
    _run_command("ss -tuln " + " ".join(args), "network")


@cli.command("ping")
@click.argument("host")
@click.option("--count", "-c", default=3, help="Ping count")
def ping_command(host: str, count: int):
    """Ping with limited output."""
    _run_command(f"ping -c {count} {host} 2>&1 | tail -5", "network")


# Config command
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

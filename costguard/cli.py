"""CostGuard CLI - Main entry point"""

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from . import __version__
from .config.loader import load_config, get_api_key, save_api_key
from .config.schema import CostGuardConfig
from .api.client import CostGuardClient
from .utils.terraform import load_plan_json
from .formatters.table import TableFormatter
from .formatters.json_fmt import JsonFormatter
from .formatters.github import GitHubFormatter

app = typer.Typer(
    name="costguard",
    help="CostGuard CLI - Cloud Cost Analysis Tool",
    add_completion=False
)
console = Console()


@app.command()
def breakdown(
    path: Optional[str] = typer.Option(
        None, "--path", "-p",
        help="Path to Terraform directory or plan.json"
    ),
    config_file: Optional[str] = typer.Option(
        None, "--config", "-c",
        help="Path to costguard.yml config file"
    ),
    format: str = typer.Option(
        "table", "--format", "-f",
        help="Output format: table, json, github-comment"
    ),
    out: Optional[str] = typer.Option(
        None, "--out", "-o",
        help="Output file path"
    ),
    show_resources: bool = typer.Option(
        True, "--resources/--no-resources",
        help="Show resource breakdown"
    ),
    api_key: Optional[str] = typer.Option(
        None, "--api-key",
        help="CostGuard API key (or set COSTGUARD_API_KEY)"
    )
):
    """
    Analyze Terraform plans and show cost breakdown.

    Examples:
        costguard breakdown --path ./terraform
        costguard breakdown --config costguard.yml
        costguard breakdown --path ./infrastructure/aws --format json
    """
    # Get API key
    key = api_key or get_api_key()
    if not key:
        console.print("[red]Error:[/red] No API key found.")
        console.print("Set COSTGUARD_API_KEY or run: costguard configure --api-key YOUR_KEY")
        raise typer.Exit(1)

    # Load config
    try:
        if config_file:
            config = load_config(config_path=config_file)
        elif path:
            # Single path mode - create minimal config
            config = CostGuardConfig()
            from .config.schema import ProjectConfig
            config.projects = [ProjectConfig(path=path, name=Path(path).name)]
        else:
            # Try to find config in current directory
            config = load_config()
            if not config.projects:
                console.print("[red]Error:[/red] No projects found.")
                console.print("Use --path to specify a directory or --config for a config file.")
                raise typer.Exit(1)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Override config output format
    config.output.format = format
    config.output.show_resources = show_resources

    # Initialize client
    client = CostGuardClient(
        api_key=key,
        api_url=config.settings.api_url
    )

    # Analyze each project
    projects_data = []
    for project in config.get_active_projects():
        console.print(f"Analyzing [cyan]{project.get_name()}[/cyan]...")

        try:
            plan = load_plan_json(project.path)
            projects_data.append({
                "name": project.get_name(),
                "path": project.path,
                "plan": plan
            })
        except FileNotFoundError:
            console.print(f"  [yellow]Warning:[/yellow] No plan.json found in {project.path}")
            continue
        except Exception as e:
            console.print(f"  [red]Error:[/red] {e}")
            continue

    if not projects_data:
        console.print("[red]Error:[/red] No valid plans found to analyze.")
        raise typer.Exit(1)

    # Call API
    console.print("Sending to CostGuard API...")
    result = client.analyze_projects(projects_data)

    # Format output
    formatter = _get_formatter(format, config)
    output = formatter.format(result)

    # Write or print
    if out:
        Path(out).write_text(output)
        console.print(f"Output written to [green]{out}[/green]")
    else:
        console.print(output)

    # Check thresholds and exit code
    exit_code = _check_thresholds(result, config)
    raise typer.Exit(exit_code)


@app.command()
def configure(
    api_key: Optional[str] = typer.Option(
        None, "--api-key",
        help="Set CostGuard API key"
    ),
    show: bool = typer.Option(
        False, "--show",
        help="Show current configuration"
    )
):
    """
    Configure CostGuard CLI settings.

    Examples:
        costguard configure --api-key YOUR_API_KEY
        costguard configure --show
    """
    if show:
        key = get_api_key()
        if key:
            masked = key[:8] + "..." + key[-4:]
            console.print(f"API Key: {masked}")
        else:
            console.print("API Key: [yellow]Not set[/yellow]")
        return

    if api_key:
        save_api_key(api_key)
        console.print("[green]API key saved successfully.[/green]")
    else:
        console.print("Use --api-key to set your API key")


@app.command()
def version():
    """Show version information."""
    console.print(f"CostGuard CLI v{__version__}")


def _get_formatter(format: str, config: CostGuardConfig):
    """Get formatter based on format string"""
    if format == "json":
        return JsonFormatter()
    elif format == "github-comment":
        return GitHubFormatter(
            show_resources=config.output.show_resources,
            collapse_resources=config.ci.collapse_resources
        )
    else:
        return TableFormatter(
            show_resources=config.output.show_resources
        )


def _check_thresholds(result, config: CostGuardConfig) -> int:
    """Check thresholds and return exit code"""
    thresholds = config.thresholds

    # Check decision
    if config.settings.fail_on_deny and result.decision == "DENY":
        console.print("[red]BLOCKED:[/red] CostGuard denied this deployment.")
        return 1

    # Check cost thresholds
    if thresholds.fail_monthly_cost and result.total_monthly_cost > thresholds.fail_monthly_cost:
        console.print(
            f"[red]BLOCKED:[/red] Monthly cost ${result.total_monthly_cost:,.2f} "
            f"exceeds limit ${thresholds.fail_monthly_cost:,.2f}"
        )
        return 1

    if thresholds.warn_monthly_cost and result.total_monthly_cost > thresholds.warn_monthly_cost:
        console.print(
            f"[yellow]WARNING:[/yellow] Monthly cost ${result.total_monthly_cost:,.2f} "
            f"exceeds warning threshold ${thresholds.warn_monthly_cost:,.2f}"
        )

    return 0


def main():
    """Main entry point"""
    app()


if __name__ == "__main__":
    main()

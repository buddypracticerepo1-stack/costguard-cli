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
def analyze(
    path: str = typer.Argument(
        ...,
        help="Path to terraform plan JSON, CloudFormation template (YAML/JSON), "
             "or `aws cloudformation describe-change-set` output"
    ),
    iac_type: Optional[str] = typer.Option(
        None, "--iac-type",
        help="Override auto-detect: terraform | cloudformation"
    ),
    region: Optional[str] = typer.Option(
        None, "--region",
        help="Cloud region (required for CloudFormation; ignored for terraform)"
    ),
    budget_code: Optional[str] = typer.Option(
        None, "--budget-code",
        help="Budget code (or set --skip-budget for pricing-only mode)"
    ),
    skip_budget: bool = typer.Option(
        True, "--skip-budget/--check-budget",
        help="Skip budget validation (default: skip)"
    ),
    api_key: Optional[str] = typer.Option(
        None, "--api-key",
        help="CostGuard API key (or set COSTGUARD_API_KEY)"
    ),
    api_url: Optional[str] = typer.Option(
        None, "--api-url",
        help="CostGuard API base URL (or set COSTGUARD_API_URL)"
    ),
):
    """
    Analyze a single IaC plan file with auto-detection.

    Detects iac_type from file content (terraform plan JSON has
    format_version/resource_changes; CloudFormation template has
    Resources/AWSTemplateFormatVersion; CFN changeset has Changes[]),
    validates locally, and exits non-zero when the API returns errors
    even inside HTTP 200 envelopes.

    Examples:
        costguard analyze plan.json
        costguard analyze template.yaml --region us-east-1
        costguard analyze changeset.json --region eu-west-1
    """
    from .utils.detect import detect_payload
    from .utils.validate import validate_payload, ValidationError
    from .api.client import CostGuardClient

    # Build payload
    try:
        body = detect_payload(path)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Input error:[/red] {e}")
        raise typer.Exit(2)

    # Apply overrides
    if iac_type:
        body["iac_type"] = iac_type
    if region:
        body["region"] = region
    if budget_code:
        body["budget_code"] = budget_code
    body.setdefault("options", {})["skip_budget"] = skip_budget
    body["options"].setdefault("skip_guardrails", True)
    body["options"].setdefault("include_calculations", False)

    # Local validation
    try:
        validate_payload(body, region=region)
    except ValidationError as e:
        console.print(f"[red]Validation error:[/red] {e}")
        raise typer.Exit(2)

    # Resolve API key + URL
    import os
    key = api_key or get_api_key() or os.environ.get("COSTGUARD_API_KEY")
    if not key:
        console.print("[red]Error:[/red] No API key found.")
        console.print("Set COSTGUARD_API_KEY or run: costguard configure --api-key YOUR_KEY")
        raise typer.Exit(2)
    url = api_url or os.environ.get("COSTGUARD_API_URL")

    client = CostGuardClient(api_key=key, api_url=url) if url else CostGuardClient(api_key=key)

    console.print(
        f"Analyzing [cyan]{path}[/cyan] "
        f"(iac_type={body['iac_type']}, iac_format={body.get('iac_format', '-')})..."
    )

    outcome = client.analyze_raw(body)

    # Surface errors inside HTTP 200 envelopes
    if not outcome.ok:
        if outcome.transport_error:
            console.print(
                f"[red]API error (HTTP {outcome.http_status}):[/red] "
                f"{outcome.transport_error[:300]}"
            )
        if outcome.errors:
            console.print("[red]Analysis failed:[/red]")
            for err in outcome.errors:
                comp = err.get("component", "?")
                code = err.get("error_code", "?")
                msg = err.get("error_message", "?")
                console.print(f"  - [{comp}] {code}: {msg}")
        raise typer.Exit(outcome.exit_code())

    console.print(
        f"[green]OK[/green] decision={outcome.decision} "
        f"monthly=${outcome.total_monthly_usd:,.2f}"
    )
    raise typer.Exit(0)


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

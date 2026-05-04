"""CLI entrypoint for autoresearch-researcher."""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(name="autoresearch-researcher", help="Weekly tool briefing agent for experiment automation research.")

DEFAULT_OUTPUT_DIR = Path("weekly_runs")
DEFAULT_MAX_TOOLS = 12
DEFAULT_MAX_COST_USD = 20.0


async def run_briefing(
    week: str,
    output_dir: Path,
    max_tools: int,
    max_cost_usd: float,
    dry_run: bool,
) -> None:
    """Placeholder orchestrator call — replaced by real orchestrator in US7."""
    pass


@app.command()
def run(
    week: str = typer.Option(..., help="ISO week identifier, e.g. 2026-W19"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, help="Base output directory"),
    max_tools: int = typer.Option(DEFAULT_MAX_TOOLS, help="Maximum number of tools to profile"),
    max_cost_usd: float = typer.Option(DEFAULT_MAX_COST_USD, help="Abort if estimated cost exceeds this USD amount"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip actual LLM calls; validate pipeline only"),
    rerun: bool = typer.Option(False, "--rerun", help="Allow re-running a week that already has output"),
) -> None:
    """Discover, profile, and write a weekly briefing for experiment-automation tools."""
    week_dir = output_dir / week

    if week_dir.exists() and not rerun:
        typer.echo(f"ERROR: {week_dir} already exists. Use --rerun to overwrite.", err=True)
        raise typer.Exit(code=1)

    week_dir.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()
    metadata: dict = {
        "week": week,
        "started_at": started_at,
        "max_tools": max_tools,
        "max_cost_usd": max_cost_usd,
        "dry_run": dry_run,
    }
    metadata_path = week_dir / "run_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2))

    t_start = datetime.now(timezone.utc)
    try:
        asyncio.run(
            run_briefing(
                week=week,
                output_dir=week_dir,
                max_tools=max_tools,
                max_cost_usd=max_cost_usd,
                dry_run=dry_run,
            )
        )
    finally:
        t_end = datetime.now(timezone.utc)
        metadata["finished_at"] = t_end.isoformat()
        metadata["elapsed_seconds"] = round((t_end - t_start).total_seconds(), 2)
        metadata_path.write_text(json.dumps(metadata, indent=2))
        typer.echo(f"Run complete. Output: {week_dir}")


@app.command()
def diff(
    week: str = typer.Option(..., help="ISO week identifier, e.g. 2026-W19"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, help="Base output directory"),
) -> None:
    """Generate diff.md and feedback.md template from draft.md vs final.md."""
    week_dir = output_dir / week
    draft = week_dir / "draft.md"
    final = week_dir / "final.md"

    if not draft.exists():
        typer.echo(f"ERROR: {draft} not found.", err=True)
        raise typer.Exit(code=1)

    if not final.exists():
        typer.echo(f"ERROR: {final} not found. Write final.md first.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Diff not yet implemented (US8). draft={draft}, final={final}")

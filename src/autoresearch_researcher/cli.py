"""CLI entrypoint for autoresearch-researcher."""

import asyncio
import json
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

from autoresearch_researcher.tools.search import DEFAULT_SEARCH_BACKEND

load_dotenv()

app = typer.Typer(name="autoresearch-researcher", help="Weekly tool briefing agent for experiment automation research.")
feedback_app = typer.Typer(help="Ingest human feedback from Weave traces.")
improve_app = typer.Typer(help="Generate prompt-only improvement proposals.")
app.add_typer(feedback_app, name="feedback")
app.add_typer(improve_app, name="improve")

DEFAULT_OUTPUT_DIR = Path("weekly_runs")
DEFAULT_MAX_TOOLS = 12
DEFAULT_MAX_COST_USD = 20.0


class SearchBackendOption(str, Enum):
    serpapi = "serpapi"
    perplexity = "perplexity"


async def run_briefing(
    week: str,
    output_dir: Path,
    max_tools: int,
    max_cost_usd: float,
    dry_run: bool,
    search_backend: str,
) -> None:
    """Delegate to orchestrator.run_briefing."""
    from autoresearch_researcher.orchestrator import run_briefing as _run
    await _run(
        week=week,
        output_dir=output_dir,
        max_tools=max_tools,
        max_cost_usd=max_cost_usd,
        dry_run=dry_run,
        search_backend=search_backend,
    )


@app.command()
def run(
    week: str = typer.Option(..., help="ISO week identifier, e.g. 2026-W19"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, help="Base output directory"),
    max_tools: int = typer.Option(DEFAULT_MAX_TOOLS, help="Maximum number of tools to profile"),
    max_cost_usd: float = typer.Option(DEFAULT_MAX_COST_USD, help="Abort if estimated cost exceeds this USD amount"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip actual LLM calls; validate pipeline only"),
    rerun: bool = typer.Option(False, "--rerun", help="Allow re-running a week that already has output"),
    search_backend: SearchBackendOption = typer.Option(
        SearchBackendOption(DEFAULT_SEARCH_BACKEND),
        "--search-backend",
        help="Search backend for Discovery and Profiler",
    ),
) -> None:
    """Discover, profile, and write a weekly briefing for experiment-automation tools."""
    week_dir = output_dir / week

    if week_dir.exists() and not rerun:
        typer.echo(f"ERROR: {week_dir} already exists. Use --rerun to overwrite.", err=True)
        raise typer.Exit(code=1)

    if week_dir.exists() and rerun:
        from autoresearch_researcher.orchestrator import backup_week_dir
        backup = backup_week_dir(week_dir)
        typer.echo(f"Previous run backed up to: {backup}")

    week_dir.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()
    metadata: dict = {
        "week": week,
        "started_at": started_at,
        "max_tools": max_tools,
        "max_cost_usd": max_cost_usd,
        "dry_run": dry_run,
        "search_backend": search_backend.value,
    }
    metadata_path = week_dir / "run_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2))

    if not dry_run:
        try:
            from autoresearch_researcher.orchestrator import init_observability
            weave_client = init_observability(week_id=week)
            if weave_client is not None:
                typer.echo(f"Weave tracing: {getattr(weave_client, 'url', '(see W&B dashboard)')}")
        except Exception as e:
            typer.echo(f"Warning: Weave init failed ({e}). Continuing without tracing.", err=True)

    t_start = datetime.now(timezone.utc)
    try:
        asyncio.run(
            run_briefing(
                week=week,
                output_dir=week_dir,
                max_tools=max_tools,
                max_cost_usd=max_cost_usd,
                dry_run=dry_run,
                search_backend=search_backend.value,
            )
        )
    except Exception as e:
        typer.echo(f"Run aborted: {e}", err=True)
        raise typer.Exit(code=2)
    finally:
        t_end = datetime.now(timezone.utc)
        # Merge finished_at into existing metadata (orchestrator may have written cost info)
        existing = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
        existing["finished_at"] = t_end.isoformat()
        existing["elapsed_seconds"] = round((t_end - t_start).total_seconds(), 2)
        metadata_path.write_text(json.dumps(existing, indent=2))
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

    from autoresearch_researcher.tools.diff import generate_diff, generate_feedback_template

    diff_content = generate_diff(draft.read_text(), final.read_text())
    (week_dir / "diff.md").write_text(diff_content)
    typer.echo(f"diff.md written to {week_dir / 'diff.md'}")

    feedback_path = week_dir / "feedback.md"
    if not feedback_path.exists():
        feedback_path.write_text(generate_feedback_template(week=week))
        typer.echo(f"feedback.md template written to {feedback_path}")
    else:
        typer.echo(f"feedback.md already exists — not overwriting.")


@feedback_app.command("ingest")
def feedback_ingest(
    week: str = typer.Option(..., help="ISO week identifier, e.g. 2026-W19"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, help="Base output directory"),
) -> None:
    """Fetch Weave feedback for per-tool traces and write local review artifacts."""
    week_dir = output_dir / week
    profile_runs = week_dir / "_profile_runs.jsonl"
    if not profile_runs.exists():
        typer.echo(f"ERROR: {profile_runs} not found.", err=True)
        raise typer.Exit(code=1)

    try:
        from autoresearch_researcher.orchestrator import init_observability
        from autoresearch_researcher.tools.feedback import ingest_feedback

        client = init_observability(week_id=week)
        events = ingest_feedback(week_dir, client)
    except Exception as e:
        typer.echo(f"Feedback ingest failed: {e}", err=True)
        raise typer.Exit(code=2)

    typer.echo(f"Ingested {len(events)} feedback events into {week_dir / 'feedback_events.jsonl'}")


@improve_app.command("propose")
def improve_propose(
    week: str = typer.Option(..., help="ISO week identifier, e.g. 2026-W19"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, help="Base output directory"),
) -> None:
    """Run the proposer agent to synthesize a prompt-only improvement plan."""
    week_dir = output_dir / week
    if not week_dir.exists():
        typer.echo(f"ERROR: {week_dir} not found.", err=True)
        raise typer.Exit(code=1)

    try:
        from autoresearch_researcher.orchestrator import init_observability
        from autoresearch_researcher.tools.improvement import propose_prompt_improvements

        init_observability(week_id=week)
        result = propose_prompt_improvements(week_dir)
        plan_path = Path(result["plan_path"])
    except Exception as e:
        typer.echo(f"Improvement proposal failed: {e}", err=True)
        raise typer.Exit(code=2)

    typer.echo(f"Prompt improvement plan written to {plan_path}")


@improve_app.command("apply")
def improve_apply(
    week: str = typer.Option(..., help="ISO week identifier, e.g. 2026-W19"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, help="Base output directory"),
) -> None:
    """Run the applier agent to rewrite instructions/*.md from the saved plan."""
    week_dir = output_dir / week
    if not week_dir.exists():
        typer.echo(f"ERROR: {week_dir} not found.", err=True)
        raise typer.Exit(code=1)

    try:
        from autoresearch_researcher.orchestrator import init_observability
        from autoresearch_researcher.tools.improvement import apply_prompt_improvements_traced

        init_observability(week_id=week)
        result = apply_prompt_improvements_traced(week_dir)
        plan_path = Path(result["plan_path"])
        changed_paths = [Path(path) for path in result["changed_prompt_files"]]
        prompt_refs = result.get("prompt_refs") or {}
    except Exception as e:
        typer.echo(f"Improvement apply failed: {e}", err=True)
        raise typer.Exit(code=2)

    typer.echo(f"Prompt improvement plan: {plan_path}")
    if changed_paths:
        typer.echo("Updated prompt files:")
        for path in changed_paths:
            typer.echo(f"- {path}")
        if prompt_refs:
            typer.echo("Published Weave prompt refs:")
            for agent_name, ref in prompt_refs.items():
                typer.echo(f"- {agent_name}: {ref}")
    else:
        typer.echo("No prompt files updated.")

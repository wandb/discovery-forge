"""CLI entrypoint for discovery-forge."""

import asyncio
import json
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

from discovery_forge.tools.search import DEFAULT_SEARCH_BACKEND

load_dotenv()

app = typer.Typer(name="discovery-forge", help="Daily tool briefing agent for experiment automation research.")
feedback_app = typer.Typer(help="Ingest human feedback from Weave traces.")
improve_app = typer.Typer(help="Generate prompt-only improvement proposals.")
eval_app = typer.Typer(help="Build and run evaluation datasets.")
app.add_typer(feedback_app, name="feedback")
app.add_typer(improve_app, name="improve")
app.add_typer(eval_app, name="eval")

DEFAULT_OUTPUT_DIR = Path("daily_runs")
DEFAULT_MAX_TOOLS = 20
DEFAULT_MAX_COST_USD = 20.0


class SearchBackendOption(str, Enum):
    serper = "serper"
    perplexity = "perplexity"
    openai = "openai"


class RecencyOption(str, Enum):
    day = "day"
    week = "week"
    month = "month"
    year = "year"
    all = "all"


async def run_briefing(
    day: str,
    output_dir: Path,
    max_tools: int,
    max_cost_usd: float,
    dry_run: bool,
    search_backend: str,
    recency: str | None = None,
) -> None:
    """Delegate to orchestrator.run_briefing."""
    from discovery_forge.orchestrator import run_briefing as _run
    await _run(
        day=day,
        output_dir=output_dir,
        max_tools=max_tools,
        max_cost_usd=max_cost_usd,
        dry_run=dry_run,
        search_backend=search_backend,
        recency=recency,
    )


@app.command()
def run(
    day: str = typer.Option(..., "--day", help="Run date identifier, e.g. 2026-05-28"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, help="Base output directory"),
    max_tools: int = typer.Option(DEFAULT_MAX_TOOLS, help="Maximum number of tools to profile"),
    max_cost_usd: float = typer.Option(DEFAULT_MAX_COST_USD, help="Abort if estimated cost exceeds this USD amount"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip actual LLM calls; validate pipeline only"),
    rerun: bool = typer.Option(False, "--rerun", help="Allow re-running a day that already has output"),
    search_backend: SearchBackendOption = typer.Option(
        SearchBackendOption(DEFAULT_SEARCH_BACKEND),
        "--search-backend",
        help="Search backend for the ResearcherAgent",
    ),
    since: RecencyOption = typer.Option(
        RecencyOption.month,
        "--since",
        help="Restrict search results to this recency window (use 'all' for no date filter)",
    ),
) -> None:
    """Run the ResearcherAgent up to max_tools times and build the daily feed (items/* + manifest.json)."""
    day_dir = output_dir / day
    recency = None if since == RecencyOption.all else since.value
    previous_manifest_path: Path | None = None

    if day_dir.exists() and not rerun:
        typer.echo(f"ERROR: {day_dir} already exists. Use --rerun to overwrite.", err=True)
        raise typer.Exit(code=1)

    if day_dir.exists() and rerun:
        from discovery_forge.orchestrator import backup_run_dir
        backup = backup_run_dir(day_dir)
        candidate_manifest = backup / "manifest.json"
        if candidate_manifest.exists():
            previous_manifest_path = candidate_manifest
        typer.echo(f"Previous run backed up to: {backup}")

    day_dir.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()
    metadata: dict = {
        "day": day,
        "started_at": started_at,
        "max_tools": max_tools,
        "max_cost_usd": max_cost_usd,
        "dry_run": dry_run,
        "search_backend": search_backend.value,
        "recency": recency,
    }
    if previous_manifest_path is not None:
        metadata["previous_manifest_path"] = str(previous_manifest_path)
    metadata_path = day_dir / "run_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2))

    if not dry_run:
        try:
            from discovery_forge.orchestrator import init_observability
            weave_client = init_observability(day_id=day)
            if weave_client is not None:
                typer.echo(f"Weave tracing: {getattr(weave_client, 'url', '(see W&B dashboard)')}")
        except Exception as e:
            typer.echo(f"Warning: Weave init failed ({e}). Continuing without tracing.", err=True)

    t_start = datetime.now(timezone.utc)
    try:
        asyncio.run(
            run_briefing(
                day=day,
                output_dir=day_dir,
                max_tools=max_tools,
                max_cost_usd=max_cost_usd,
                dry_run=dry_run,
                search_backend=search_backend.value,
                recency=recency,
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
        typer.echo(f"Run complete. Output: {day_dir}")


@feedback_app.command("ingest")
def feedback_ingest(
    day: str = typer.Option(..., "--day", help="Run date identifier, e.g. 2026-05-28"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, help="Base output directory"),
) -> None:
    """Fetch Weave feedback for per-tool traces and write local review artifacts."""
    day_dir = output_dir / day
    profile_runs = day_dir / "_profile_runs.jsonl"
    if not profile_runs.exists():
        typer.echo(f"ERROR: {profile_runs} not found.", err=True)
        raise typer.Exit(code=1)

    try:
        from discovery_forge.orchestrator import init_observability
        from discovery_forge.tools.feedback import ingest_feedback

        client = init_observability(day_id=day)
        events = ingest_feedback(day_dir, client)
    except Exception as e:
        typer.echo(f"Feedback ingest failed: {e}", err=True)
        raise typer.Exit(code=2)

    typer.echo(f"Ingested {len(events)} feedback events into {day_dir / 'feedback_events.jsonl'}")


@eval_app.command("run-researcher")
def eval_run_researcher(
    dataset_path: Optional[Path] = typer.Option(None, "--dataset-path", help="Local JSONL dataset path"),
    dataset_ref: Optional[str] = typer.Option(None, "--dataset-ref", help="Weave Dataset ref URI"),
    output_dir: Path = typer.Option(Path("eval_runs/researcher"), help="Directory for researcher eval artifacts"),
    search_backend: SearchBackendOption = typer.Option(
        SearchBackendOption(DEFAULT_SEARCH_BACKEND),
        "--search-backend",
        help="Search backend for the ResearcherAgent",
    ),
    limit: Optional[int] = typer.Option(None, "--limit", help="Optional row limit for smoke runs"),
    researcher_prompt_ref: Optional[str] = typer.Option(
        None,
        "--researcher-prompt-ref",
        help="Optional Weave StringPrompt ref for researcher_instructions",
    ),
) -> None:
    """Run ResearcherAgent against a scope/profile evaluation dataset in Weave."""
    if (dataset_path is None) == (dataset_ref is None):
        typer.echo("ERROR: Provide exactly one of --dataset-path or --dataset-ref.", err=True)
        raise typer.Exit(code=1)
    if dataset_path is not None and not dataset_path.exists():
        typer.echo(f"ERROR: {dataset_path} not found.", err=True)
        raise typer.Exit(code=1)

    try:
        from discovery_forge.orchestrator import init_observability
        from discovery_forge.tools.evaluation import run_researcher_evaluation

        init_observability(day_id="researcher-eval")
        result = run_researcher_evaluation(
            dataset_path=dataset_path,
            dataset_ref=dataset_ref,
            output_dir=output_dir,
            search_backend=search_backend.value,
            limit=limit,
            researcher_prompt_ref=researcher_prompt_ref,
        )
    except Exception as e:
        typer.echo(f"Researcher evaluation failed: {e}", err=True)
        raise typer.Exit(code=2)

    typer.echo("Researcher evaluation complete.")
    typer.echo(str(result))


@eval_app.command("publish-dataset")
def eval_publish_dataset(
    dataset_path: Path = typer.Option(..., "--dataset", help="Local JSONL dataset path"),
    name: str = typer.Option(..., "--name", help="Weave Dataset object name"),
) -> None:
    """Publish a local JSONL eval dataset as a versioned Weave Dataset."""
    if not dataset_path.exists():
        typer.echo(f"ERROR: {dataset_path} not found.", err=True)
        raise typer.Exit(code=1)
    try:
        from discovery_forge.orchestrator import init_observability
        from discovery_forge.tools.discovery_evaluation import publish_eval_dataset

        init_observability(day_id="eval-dataset")
        result = publish_eval_dataset(dataset_path, name=name)
    except Exception as e:
        typer.echo(f"Dataset publish failed: {e}", err=True)
        raise typer.Exit(code=2)

    typer.echo(f"Published dataset `{result['name']}` with {result['row_count']} rows.")
    typer.echo(f"Ref: {result['ref']}")


@eval_app.command("run-discovery")
def eval_run_discovery(
    dataset_path: Optional[Path] = typer.Option(None, "--dataset", help="Local JSONL dataset path"),
    dataset_ref: Optional[str] = typer.Option(None, "--dataset-ref", help="Weave Dataset ref URI"),
    output_dir: Path = typer.Option(Path("eval_runs/discovery"), help="Directory for discovery eval artifacts"),
    search_backend: SearchBackendOption = typer.Option(
        SearchBackendOption(DEFAULT_SEARCH_BACKEND),
        "--search-backend",
        help="Search backend for the ResearcherAgent",
    ),
    limit: Optional[int] = typer.Option(None, "--limit", help="Optional row limit for smoke runs"),
    judge_model: str = typer.Option("gpt-5.4-mini", "--judge-model", help="Model used by the LLM judge scorer"),
    researcher_prompt_ref: Optional[str] = typer.Option(
        None,
        "--researcher-prompt-ref",
        help="Optional Weave StringPrompt ref for researcher_instructions",
    ),
) -> None:
    """Run discovery quality evaluation in Weave."""
    if (dataset_path is None) == (dataset_ref is None):
        typer.echo("ERROR: Provide exactly one of --dataset or --dataset-ref.", err=True)
        raise typer.Exit(code=1)
    if dataset_path is not None and not dataset_path.exists():
        typer.echo(f"ERROR: {dataset_path} not found.", err=True)
        raise typer.Exit(code=1)

    try:
        from discovery_forge.orchestrator import init_observability
        from discovery_forge.tools.discovery_evaluation import run_discovery_evaluation

        init_observability(day_id="discovery-eval")
        result = run_discovery_evaluation(
            dataset_path=dataset_path,
            dataset_ref=dataset_ref,
            output_dir=output_dir,
            search_backend=search_backend.value,
            limit=limit,
            judge_model=judge_model,
            researcher_prompt_ref=researcher_prompt_ref,
        )
    except Exception as e:
        typer.echo(f"Discovery evaluation failed: {e}", err=True)
        raise typer.Exit(code=2)

    typer.echo("Discovery evaluation complete.")
    typer.echo(str(result))


@improve_app.command("propose")
def improve_propose(
    day: str = typer.Option(..., "--day", help="Run date identifier, e.g. 2026-05-28"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, help="Base output directory"),
) -> None:
    """Run the proposer agent to synthesize a prompt-only improvement plan."""
    day_dir = output_dir / day
    if not day_dir.exists():
        typer.echo(f"ERROR: {day_dir} not found.", err=True)
        raise typer.Exit(code=1)

    try:
        from discovery_forge.orchestrator import init_observability
        from discovery_forge.tools.improvement import propose_prompt_improvements

        init_observability(day_id=day)
        result = propose_prompt_improvements(day_dir)
        plan_path = Path(result["plan_path"])
    except Exception as e:
        typer.echo(f"Improvement proposal failed: {e}", err=True)
        raise typer.Exit(code=2)

    typer.echo(f"Prompt improvement plan written to {plan_path}")


@improve_app.command("apply")
def improve_apply(
    day: str = typer.Option(..., "--day", help="Run date identifier, e.g. 2026-05-28"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, help="Base output directory"),
) -> None:
    """Run the applier agent to rewrite instructions/*.md from the saved plan."""
    day_dir = output_dir / day
    if not day_dir.exists():
        typer.echo(f"ERROR: {day_dir} not found.", err=True)
        raise typer.Exit(code=1)

    try:
        from discovery_forge.orchestrator import init_observability
        from discovery_forge.tools.improvement import apply_prompt_improvements_traced

        init_observability(day_id=day)
        result = apply_prompt_improvements_traced(day_dir)
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

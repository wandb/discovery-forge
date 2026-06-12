"""Hands-on friendly research run entrypoint helpers.

This module owns the small amount of run setup that used to live in the
production CLI: creating the run directory, recording run metadata, optionally
initializing Weave, and calling the orchestrator.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from discovery_forge.tools.search import DEFAULT_SEARCH_BACKEND, RecencyWindow, SearchBackend

DEFAULT_OUTPUT_DIR = Path("daily_runs")
DEFAULT_MAX_TOOLS = 10
DEFAULT_MAX_COST_USD = 20.0


@dataclass(frozen=True)
class ResearchRunConfig:
    """Configuration for one hands-on research run."""

    day: str
    output_dir: Path = DEFAULT_OUTPUT_DIR
    max_tools: int = DEFAULT_MAX_TOOLS
    max_cost_usd: float = DEFAULT_MAX_COST_USD
    dry_run: bool = False
    rerun: bool = False
    search_backend: SearchBackend = DEFAULT_SEARCH_BACKEND
    recency: RecencyWindow | None = "month"


def run_research(config: ResearchRunConfig) -> Path:
    """Prepare a run directory, run the ResearcherAgent loop, and return it."""
    load_dotenv()

    from discovery_forge.observability import init_observability
    from discovery_forge.orchestrator import backup_run_dir, run_briefing

    day_dir = config.output_dir / config.day
    previous_manifest_path: Path | None = None

    if day_dir.exists() and not config.rerun:
        raise FileExistsError(f"{day_dir} already exists. Re-run with rerun=True to replace it.")

    if day_dir.exists() and config.rerun:
        backup = backup_run_dir(day_dir)
        candidate_manifest = backup / "manifest.json"
        if candidate_manifest.exists():
            previous_manifest_path = candidate_manifest
        print(f"Previous run backed up to: {backup}")

    day_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = day_dir / "run_metadata.json"
    started_at = datetime.now(timezone.utc).isoformat()
    metadata: dict = {
        "day": config.day,
        "started_at": started_at,
        "max_tools": config.max_tools,
        "max_cost_usd": config.max_cost_usd,
        "dry_run": config.dry_run,
        "search_backend": config.search_backend,
        "recency": config.recency,
    }
    if previous_manifest_path is not None:
        metadata["previous_manifest_path"] = str(previous_manifest_path)
    metadata_path.write_text(json.dumps(metadata, indent=2))

    if not config.dry_run:
        weave_client = init_observability(day_id=config.day)
        if weave_client is not None:
            print(f"Weave tracing: {getattr(weave_client, 'url', '(see W&B dashboard)')}")

    t_start = datetime.now(timezone.utc)
    try:
        asyncio.run(
            run_briefing(
                day=config.day,
                output_dir=day_dir,
                max_tools=config.max_tools,
                max_cost_usd=config.max_cost_usd,
                dry_run=config.dry_run,
                search_backend=config.search_backend,
                recency=config.recency,
            )
        )
    finally:
        t_end = datetime.now(timezone.utc)
        existing = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
        existing["finished_at"] = t_end.isoformat()
        existing["elapsed_seconds"] = round((t_end - t_start).total_seconds(), 2)
        metadata_path.write_text(json.dumps(existing, indent=2))

    print(f"Run complete. Output: {day_dir}")
    return day_dir

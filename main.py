"""Run one discovery-forge ResearcherAgent loop.

After this script completes, start by opening:
- ``daily_runs/<day>/run_metadata.json`` for run metadata
- ``daily_runs/<day>/_profile_runs.jsonl`` for one row per ResearcherAgent trace
- ``daily_runs/<day>/items/`` and ``manifest.json`` for feed output
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from discovery_forge.research_run import (
    DEFAULT_MAX_COST_USD,
    DEFAULT_MAX_TOOLS,
    DEFAULT_OUTPUT_DIR,
    ResearchRunConfig,
    run_research,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--day",
        default=date.today().isoformat(),
        help="Run date identifier, defaults to today, e.g. 2026-05-29",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Base output directory")
    parser.add_argument("--max-tools", type=int, default=DEFAULT_MAX_TOOLS, help="Maximum ResearcherAgent runs")
    parser.add_argument(
        "--max-cost-usd",
        type=float,
        default=DEFAULT_MAX_COST_USD,
        help="Abort if estimated model cost exceeds this USD amount",
    )
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM calls and write synthetic outputs")
    parser.add_argument("--rerun", action="store_true", help="Back up an existing day directory and run again")
    parser.add_argument(
        "--search-backend",
        choices=["serper", "perplexity", "openai"],
        default="serper",
        help="Search backend. Hands-on default is serper; no fallback is attempted.",
    )
    parser.add_argument(
        "--since",
        choices=["day", "week", "month", "year", "all"],
        default="month",
        help="Search recency hint. Use all to disable date filtering where supported.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_research(
        ResearchRunConfig(
            day=args.day,
            output_dir=args.output_dir,
            max_tools=args.max_tools,
            max_cost_usd=args.max_cost_usd,
            dry_run=args.dry_run,
            rerun=args.rerun,
            search_backend=args.search_backend,
            recency=None if args.since == "all" else args.since,
        )
    )


if __name__ == "__main__":
    main()

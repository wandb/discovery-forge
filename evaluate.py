"""Run offline evaluations against published Weave datasets.

The verdict dataset is run by default. Discovery quality evaluation can be added
by passing ``--discovery-dataset-key`` or ``--discovery-dataset-ref``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from discovery_forge.evaluation.datasets import (
    DISCOVERY_DATASET_KEY,
    VERDICT_DATASET_KEY,
    get_eval_dataset_ref,
)
from discovery_forge.evaluation.discovery import run_discovery_evaluation
from discovery_forge.evaluation.verdict import run_researcher_evaluation
from discovery_forge.observability import init_observability
from discovery_forge.tools.search import DEFAULT_SEARCH_BACKEND
from discovery_forge.agents.researcher_model import DEFAULT_RESEARCHER_MAX_TURNS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    dataset_group = parser.add_mutually_exclusive_group()
    dataset_group.add_argument(
        "--verdict-dataset-key",
        default=VERDICT_DATASET_KEY,
        help="Configured verdict dataset key from evaluation/evaluation_config.yaml",
    )
    dataset_group.add_argument(
        "--verdict-dataset-ref",
        default=None,
        help="Published verdict dataset Weave ref (overrides evaluation/evaluation_config.yaml)",
    )
    discovery_group = parser.add_mutually_exclusive_group()
    discovery_group.add_argument(
        "--discovery-dataset-key",
        default=None,
        help=f"Configured discovery dataset key from evaluation/evaluation_config.yaml, e.g. {DISCOVERY_DATASET_KEY}",
    )
    discovery_group.add_argument(
        "--discovery-dataset-ref",
        default=None,
        help="Published discovery dataset Weave ref (overrides evaluation/evaluation_config.yaml)",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("eval_runs"), help="Base eval output directory")
    parser.add_argument(
        "--search-backend",
        choices=["serper", "perplexity", "openai"],
        default=DEFAULT_SEARCH_BACKEND,
        help="Search backend. Defaults to serper; no fallback is attempted.",
    )
    parser.add_argument(
        "--since",
        choices=["day", "week", "month", "year", "all"],
        default="month",
        help="Search recency hint. Use all to disable date filtering where supported.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=DEFAULT_RESEARCHER_MAX_TURNS,
        help="Maximum ResearcherAgent turns per evaluation row.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit for smoke runs")
    parser.add_argument("--judge-model", default="gpt-5.4-mini", help="Model used by discovery LLM judge")
    parser.add_argument("--researcher-prompt-ref", default=None, help="Optional Weave StringPrompt ref")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    init_observability(day_id="offline-eval")

    verdict_output_dir = args.output_dir / "verdict"
    verdict_dataset_ref = args.verdict_dataset_ref or get_eval_dataset_ref(args.verdict_dataset_key)

    print("Running verdict quality evaluation...")
    verdict_result = run_researcher_evaluation(
        dataset_ref=verdict_dataset_ref,
        output_dir=verdict_output_dir,
        search_backend=args.search_backend,
        recency=None if args.since == "all" else args.since,
        max_turns=args.max_turns,
        limit=args.limit,
        researcher_prompt_ref=args.researcher_prompt_ref,
    )
    print("Verdict evaluation complete.")
    print(verdict_result)

    if args.discovery_dataset_ref is None and args.discovery_dataset_key is None:
        return verdict_result

    discovery_dataset_ref = args.discovery_dataset_ref or get_eval_dataset_ref(args.discovery_dataset_key)
    discovery_output_dir = args.output_dir / "discovery"
    print("Running discovery quality evaluation...")
    discovery_result = run_discovery_evaluation(
        dataset_ref=discovery_dataset_ref,
        output_dir=discovery_output_dir,
        search_backend=args.search_backend,
        limit=args.limit,
        judge_model=args.judge_model,
        researcher_prompt_ref=args.researcher_prompt_ref,
    )
    print("Discovery evaluation complete.")
    print(discovery_result)
    return verdict_result, discovery_result


if __name__ == "__main__":
    main()

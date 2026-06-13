"""Run offline verdict quality evaluation against a published Weave dataset.

The verdict dataset is published to Weave as ``verdict_quality_dataset``. By
default this loads the pinned published ref from
``evaluation/evaluation_config.yaml``;
pass ``--verdict-dataset-key`` to choose a configured dataset or
``--verdict-dataset-ref`` to override with a full ref.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from discovery_forge.evaluation.datasets import (
    VERDICT_DATASET_KEY,
    get_eval_dataset_ref,
)
from discovery_forge.evaluation.verdict import run_researcher_evaluation
from discovery_forge.observability import init_observability
from discovery_forge.tools.search import DEFAULT_SEARCH_BACKEND


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
    parser.add_argument("--output-dir", type=Path, default=Path("eval_runs"), help="Base eval output directory")
    parser.add_argument(
        "--search-backend",
        choices=["serper", "perplexity", "openai"],
        default=DEFAULT_SEARCH_BACKEND,
        help="Search backend. Defaults to serper; no fallback is attempted.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit for smoke runs")
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
        limit=args.limit,
        researcher_prompt_ref=args.researcher_prompt_ref,
    )
    print("Verdict evaluation complete.")
    print(verdict_result)


if __name__ == "__main__":
    main()

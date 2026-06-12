"""Offline evaluation runners, scorers, and dataset helpers for ResearcherAgent."""

from discovery_forge.evaluation.datasets import (
    VERDICT_DATASET_NAME,
    dataset_rows,
    load_eval_dataset,
    load_jsonl_rows,
    publish_eval_dataset,
)
from discovery_forge.evaluation.verdict import (
    make_researcher_eval_predict_fn,
    profile_quality_scorer,
    run_researcher_evaluation,
    verdict_quality_scorer,
)

__all__ = [
    "VERDICT_DATASET_NAME",
    "dataset_rows",
    "load_eval_dataset",
    "load_jsonl_rows",
    "publish_eval_dataset",
    "make_researcher_eval_predict_fn",
    "profile_quality_scorer",
    "run_researcher_evaluation",
    "verdict_quality_scorer",
]

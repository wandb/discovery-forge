"""Offline evaluation runners, scorers, and dataset helpers for ResearcherAgent."""

from discovery_forge.evaluation.datasets import (
    DISCOVERY_DATASET_NAME,
    VERDICT_DATASET_NAME,
    dataset_rows,
    load_eval_dataset,
    load_jsonl_rows,
    publish_eval_dataset,
)
from discovery_forge.evaluation.discovery import (
    DiscoveryQualityJudge,
    aggregate_discovery_metrics,
    make_discovery_eval_predict_fn,
    run_discovery_evaluation,
)
from discovery_forge.evaluation.verdict import (
    make_researcher_eval_predict_fn,
    profile_quality_scorer,
    run_researcher_evaluation,
    verdict_quality_scorer,
)

__all__ = [
    "DISCOVERY_DATASET_NAME",
    "VERDICT_DATASET_NAME",
    "DiscoveryQualityJudge",
    "aggregate_discovery_metrics",
    "dataset_rows",
    "load_eval_dataset",
    "load_jsonl_rows",
    "publish_eval_dataset",
    "make_discovery_eval_predict_fn",
    "make_researcher_eval_predict_fn",
    "profile_quality_scorer",
    "run_discovery_evaluation",
    "run_researcher_evaluation",
    "verdict_quality_scorer",
]

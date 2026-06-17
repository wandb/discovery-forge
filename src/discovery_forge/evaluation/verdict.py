"""Weave Evaluation runner for the ResearcherAgent scope/profile decision."""

from __future__ import annotations

import asyncio
import json
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import weave

from discovery_forge.agents.researcher_model import (
    DEFAULT_RESEARCHER_MAX_TURNS,
    EvalPersistenceRecorder,
    ResearcherAgentModel,
    publish_researcher_model,
)
from discovery_forge.tools.prompts import (
    InstructionPromptVersion,
    prompt_contents,
    resolve_instruction_prompts,
)
from discovery_forge.tools.search import DEFAULT_SEARCH_BACKEND, RecencyWindow, SearchBackend


class VerdictQualityEvaluation(weave.Evaluation):
    """Named Weave Evaluation object for verdict quality runs."""


def make_researcher_eval_predict_fn(
    *,
    output_dir: Path,
    search_backend: SearchBackend = DEFAULT_SEARCH_BACKEND,
    recency: RecencyWindow | None = "month",
    max_turns: int = DEFAULT_RESEARCHER_MAX_TURNS,
    researcher_prompt_ref: str | None = None,
):
    """Create a backwards-compatible eval predict callable backed by the Weave Model."""
    prompt_versions = resolve_instruction_prompts(
        max_tools=1,
        researcher_prompt_ref=researcher_prompt_ref,
        publish_local=False,
    )
    model = _build_eval_model(
        output_dir=output_dir,
        search_backend=search_backend,
        recency=recency,
        max_turns=max_turns,
        prompt_version=prompt_versions["researcher"],
    )
    return model.predict

_EvalPersistenceRecorder = EvalPersistenceRecorder

_ACTIVE_RESEARCHER_EVAL_MODEL: ContextVar[ResearcherAgentModel | None] = ContextVar(
    "_ACTIVE_RESEARCHER_EVAL_MODEL",
    default=None,
)


@weave.op()
async def predict_researcher_eval_row(
    input_tool_name: str | None = None,
    input_candidate_url: str | None = None,
    input_candidate_description: str | None = None,
) -> dict[str, Any]:
    """Stable eval predict op that delegates to the runtime-bound researcher model."""
    model = _ACTIVE_RESEARCHER_EVAL_MODEL.get()
    if model is None:
        raise RuntimeError("No active ResearcherAgentModel is bound for evaluation.")
    return await model.predict(
        input_tool_name=input_tool_name,
        input_candidate_url=input_candidate_url,
        input_candidate_description=input_candidate_description,
    )


@weave.op()
def verdict_quality_scorer(
    output: dict[str, Any],
    expected_scope_status: str,
) -> dict[str, Any]:
    """Score whether the agent accepted/rejected the candidate correctly."""
    observed = _observed_scope_status(output)
    return {
        "is_correct": observed == expected_scope_status,
        "expected": expected_scope_status,
        "observed": observed,
    }


@weave.op()
def profile_quality_scorer(
    output: dict[str, Any],
    expected_scope_status: str,
    expected_issue_category: str | None = None,
) -> dict[str, Any]:
    """Score basic profile/rejection quality."""
    observed = _observed_scope_status(output)
    if observed != expected_scope_status:
        return {
            "passed": False,
            "reason": "scope_status_mismatch",
            "details": {
                "expected_scope_status": expected_scope_status,
                "observed_scope_status": observed,
            },
        }

    if expected_scope_status == "rejected":
        reason = str(output.get("verdict_reason") or "")
        has_reason = len(reason.strip()) >= 20
        category_match = _verdict_reason_matches_category(reason, expected_issue_category)
        return {
            "passed": has_reason and category_match,
            "has_verdict_reason": has_reason,
            "category_match": category_match,
            "expected_issue_category": expected_issue_category,
            "verdict_reason": reason,
        }

    profile = output.get("profile") if isinstance(output.get("profile"), dict) else {}
    critical_fields = [
        "domains",
        "autonomy_level",
        "autonomy_rationale",
        "interface",
        "key_limitations",
    ]
    advisory_fields = ["license", "resource_requirements"]
    missing = [field for field in critical_fields if _is_missing_profile_value(profile.get(field))]
    unknown_advisory_fields = [
        field for field in advisory_fields if _is_missing_profile_value(profile.get(field))
    ]
    has_url = any(profile.get(field) for field in ("github_url", "paper_url", "project_url"))
    source_ids = profile.get("source_ids")
    has_sources = isinstance(source_ids, list) and len(source_ids) > 0
    passed = not missing and has_url and has_sources
    return {
        "passed": passed,
        "missing_fields": missing,
        "unknown_advisory_fields": unknown_advisory_fields,
        "has_primary_url": has_url,
        "has_sources": has_sources,
    }


def run_researcher_evaluation(
    *,
    dataset_path: Path | None = None,
    dataset_ref: str | None = None,
    output_dir: Path,
    search_backend: SearchBackend = DEFAULT_SEARCH_BACKEND,
    recency: RecencyWindow | None = "month",
    max_turns: int = DEFAULT_RESEARCHER_MAX_TURNS,
    evaluation_name: str = "Verdict Quality Eval",
    limit: int | None = None,
    researcher_prompt_ref: str | None = None,
) -> Any:
    """Run the ResearcherAgent Weave evaluation."""
    dataset = _load_evaluation_dataset(dataset_path=dataset_path, dataset_ref=dataset_ref)
    # Pass the versioned Weave Dataset object straight through so the Evaluation
    # stays linked to `verdict_quality_dataset` instead of creating an anonymous
    # `Dataset` object. Only fall back to raw rows when slicing with `limit` or
    # when evaluating a local JSONL file.
    if isinstance(dataset, list):
        eval_dataset: Any = dataset[:limit] if limit is not None else dataset
    elif limit is not None:
        eval_dataset = _dataset_rows(dataset)[:limit]
    else:
        eval_dataset = dataset
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt_versions = resolve_instruction_prompts(
        max_tools=limit or 1,
        researcher_prompt_ref=researcher_prompt_ref,
        publish_local=True,
    )
    prompt_version = prompt_versions["researcher"]
    model = _build_eval_model(
        output_dir=output_dir,
        search_backend=search_backend,
        recency=recency,
        max_turns=max_turns,
        prompt_version=prompt_version,
    )
    publish_researcher_model(model)
    evaluation = VerdictQualityEvaluation(
        dataset=eval_dataset,
        scorers=[verdict_quality_scorer],
        evaluation_name=evaluation_name,
        metadata={
            "search_backend": search_backend,
            "recency": recency,
            "max_turns": max_turns,
        },
    )
    token = _ACTIVE_RESEARCHER_EVAL_MODEL.set(model)
    try:
        return asyncio.run(evaluation.evaluate(predict_researcher_eval_row))
    finally:
        _ACTIVE_RESEARCHER_EVAL_MODEL.reset(token)


def preprocess_verdict_model_input(row: dict[str, Any]) -> dict[str, Any]:
    """Expose only candidate inputs to the model, keeping labels for scorers."""
    return {
        "input_tool_name": row["input_tool_name"],
        "input_candidate_url": row["input_candidate_url"],
        "input_candidate_description": row["input_candidate_description"],
    }


def _build_eval_model(
    *,
    output_dir: Path,
    search_backend: SearchBackend,
    recency: RecencyWindow | None,
    max_turns: int,
    prompt_version: InstructionPromptVersion,
) -> ResearcherAgentModel:
    return ResearcherAgentModel(
        search_backend=search_backend,
        recency=recency,
        max_turns=max_turns,
        prompt_object_name=prompt_version.object_name,
        researcher_prompt_ref=prompt_version.ref_uri,
        researcher_prompt_hash=prompt_version.content_hash,
    ).bind_runtime(
        output_dir=output_dir,
        instructions_override=prompt_contents({"researcher": prompt_version})["researcher"],
        capture_persistence=True,
    )


def _load_evaluation_dataset(
    *,
    dataset_path: Path | None,
    dataset_ref: str | None,
) -> Any:
    if dataset_path is None and dataset_ref is None:
        raise ValueError("Provide either dataset_path or dataset_ref")
    if dataset_path is not None:
        return [
            json.loads(line)
            for line in dataset_path.read_text().splitlines()
            if line.strip()
        ]
    return weave.ref(str(dataset_ref)).get()


def _dataset_rows(dataset: Any) -> list[dict[str, Any]]:
    if isinstance(dataset, list):
        return [dict(row) for row in dataset]
    return [dict(row) for row in dataset.rows]


def _observed_scope_status(output: dict[str, Any]) -> Any:
    return output.get("scope_status") or output.get("verdict")


def _is_missing_profile_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == "" or value.strip().lower() == "unknown"
    if isinstance(value, list):
        return len(value) == 0 or all(_is_missing_profile_value(item) for item in value)
    return False


def _verdict_reason_matches_category(reason: str, category: str | None) -> bool:
    if category is None:
        return True
    text = reason.lower()
    if category == "out_of_scope":
        return any(token in text for token in ("out of scope", "curated", "survey", "resource", "not a tool", "does not"))
    if category == "missing_url":
        return any(token in text for token in ("url", "source", "verify", "verified"))
    if category == "duplicate_known_tool":
        return any(token in text for token in ("duplicate", "already", "known"))
    return True

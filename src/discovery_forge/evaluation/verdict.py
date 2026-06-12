"""Weave Evaluation runner for the ResearcherAgent scope/profile decision."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

import weave
from agents import Runner

from discovery_forge.agents.researcher import build_researcher_agent
from discovery_forge.schemas.tool_profile import RejectedProfile, ToolProfile
from discovery_forge.tools.prompts import load_prompt_ref_content
from discovery_forge.tools.search import DEFAULT_SEARCH_BACKEND, SearchBackend


class VerdictQualityEvaluation(weave.Evaluation):
    """Named Weave Evaluation object for verdict quality runs."""

    researcher_prompt_ref: str | None = None


class _EvalPersistenceRecorder:
    """Capture this eval row's final persistence tool result in memory."""

    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []

    def save_tool_profile(self, profile: ToolProfile) -> str:
        self.events.append(("accepted", profile))
        return f"Saved profile: {profile.slug}"

    def save_rejected_profile(self, rejected: RejectedProfile) -> str:
        self.events.append(("rejected", rejected))
        primary_url = rejected.github_url or rejected.project_url or rejected.paper_url or rejected.url or "unknown"
        return f"Rejected: {rejected.name} ({primary_url}) - {rejected.verdict_reason}"

    def report_no_new_tool(self, reason: str) -> str:
        self.events.append(("unknown", reason))
        return f"No new tool found: {reason}"

    def output(self) -> dict[str, Any]:
        if not self.events:
            return {
                "scope_status": "unknown",
                "verdict_reason": "ResearcherAgent did not save or reject a profile.",
                "profile": None,
            }

        status, payload = self.events[-1]
        if status == "accepted":
            return {
                "scope_status": "accepted",
                "verdict_reason": None,
                "profile": payload.model_dump(),
            }
        if status == "rejected":
            return {
                "scope_status": "rejected",
                "verdict_reason": payload.verdict_reason,
                "profile": None,
            }
        return {
            "scope_status": "unknown",
            "verdict_reason": str(payload),
            "profile": None,
        }


def make_researcher_eval_predict_fn(
    *,
    output_dir: Path,
    search_backend: SearchBackend = DEFAULT_SEARCH_BACKEND,
    researcher_prompt_ref: str | None = None,
):
    """Create the researcher evaluation predict op without publishing a Weave Model."""
    instructions_override = (
        load_prompt_ref_content(researcher_prompt_ref)
        if researcher_prompt_ref is not None
        else None
    )

    @weave.op(name="researcher_eval_predict")
    async def predict(
        input_tool_name: str,
        input_candidate_url: str,
        input_candidate_description: str,
        **_: Any,
    ) -> dict[str, Any]:
        row_dir = output_dir / _safe_name(input_tool_name)
        recorder = _EvalPersistenceRecorder()
        prompt = (
            "Profile this specific tool candidate and determine if it is in scope:\n"
            f"Name: {input_tool_name}\n"
            f"URL: {input_candidate_url}\n"
            f"Description: {input_candidate_description}\n"
            "If in scope, save sources then call save_tool_profile_tool. "
            "If out of scope, call save_rejected_profile_tool with a clear reason."
        )
        agent = build_researcher_agent(
            output_dir=row_dir,
            search_backend=search_backend,
            instructions_override=instructions_override,
            save_tool_profile_callback=recorder.save_tool_profile,
            save_rejected_profile_callback=recorder.save_rejected_profile,
            report_no_new_tool_callback=recorder.report_no_new_tool,
        )
        result = await Runner.run(agent, input=prompt, max_turns=15)
        return {
            **recorder.output(),
            "researcher_prompt_ref": researcher_prompt_ref,
            "final_output": str(getattr(result, "final_output", "")),
        }

    return predict


@weave.op()
def verdict_quality_scorer(
    output: dict[str, Any],
    expected_scope_status: str,
) -> dict[str, Any]:
    """Score whether the agent accepted/rejected the candidate correctly."""
    observed = output.get("scope_status")
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
    observed = output.get("scope_status")
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
    predict = make_researcher_eval_predict_fn(
        output_dir=output_dir,
        search_backend=search_backend,
        researcher_prompt_ref=researcher_prompt_ref,
    )
    evaluation = VerdictQualityEvaluation(
        dataset=eval_dataset,
        scorers=[verdict_quality_scorer],
        evaluation_name=evaluation_name,
        researcher_prompt_ref=researcher_prompt_ref,
    )
    return asyncio.run(evaluation.evaluate(predict))


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


def _safe_name(value: str) -> str:
    import re

    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-").lower()
    return slug or next(tempfile._get_candidate_names())


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

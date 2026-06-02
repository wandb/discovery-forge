"""Weave Evaluation runner for ResearcherAgent discovery precision."""

from __future__ import annotations

import asyncio
import json
import re
import tempfile
from pathlib import Path
from typing import Any

import weave
import yaml
from agents import Runner

from autoresearch_researcher.agents.researcher import build_researcher_agent
from autoresearch_researcher.tools.prompts import load_prompt_ref_content
from autoresearch_researcher.tools.search import DEFAULT_SEARCH_BACKEND, RecencyWindow, SearchBackend


DISCOVERY_DATASET_NAME = "researcher_discovery_precision_dataset"
VERDICT_DATASET_NAME = "researcher_verdict_dataset"


class DiscoveryQualityEvaluation(weave.Evaluation):
    """Named Weave Evaluation object for discovery quality runs."""

    researcher_prompt_ref: str | None = None


def load_jsonl_rows(dataset_path: Path) -> list[dict[str, Any]]:
    """Load an eval dataset from local JSONL."""
    return [
        json.loads(line)
        for line in dataset_path.read_text().splitlines()
        if line.strip()
    ]


def load_eval_dataset(
    *,
    dataset_path: Path | None = None,
    dataset_ref: str | None = None,
) -> Any:
    """Load local rows or a versioned Weave Dataset object."""
    if (dataset_path is None) == (dataset_ref is None):
        raise ValueError("Provide exactly one of dataset_path or dataset_ref")
    if dataset_path is not None:
        return load_jsonl_rows(dataset_path)
    return weave.ref(str(dataset_ref)).get()


def dataset_rows(dataset: Any) -> list[dict[str, Any]]:
    if isinstance(dataset, list):
        return [dict(row) for row in dataset]
    return [dict(row) for row in dataset.rows]


def publish_eval_dataset(dataset_path: Path, *, name: str) -> dict[str, Any]:
    """Publish a local JSONL eval dataset as a versioned Weave Dataset."""
    rows = load_jsonl_rows(dataset_path)
    dataset = weave.Dataset(name=name, rows=rows)
    ref = weave.publish(dataset)
    return {
        "name": name,
        "row_count": len(rows),
        "ref": _ref_uri(ref),
    }


def make_discovery_eval_predict_fn(
    *,
    output_dir: Path,
    search_backend: SearchBackend = DEFAULT_SEARCH_BACKEND,
    max_turns: int = 40,
    researcher_prompt_ref: str | None = None,
):
    """Create a prediction op that runs one discovery attempt for one dataset row."""
    instructions_override = (
        load_prompt_ref_content(researcher_prompt_ref)
        if researcher_prompt_ref is not None
        else None
    )

    @weave.op(name="researcher_discovery_eval_predict")
    async def predict(
        id: str,
        search_brief: str,
        recency: RecencyWindow | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        row_dir = output_dir / _safe_name(id)
        row_dir.mkdir(parents=True, exist_ok=True)
        prompt = _render_discovery_prompt(search_brief=search_brief, recency=recency)
        agent = build_researcher_agent(
            output_dir=row_dir,
            search_backend=search_backend,
            recency=recency,
            instructions_override=instructions_override,
        )
        result = await Runner.run(agent, input=prompt, max_turns=max_turns)
        return {
            "row_id": id,
            "search_brief": search_brief,
            **_read_discovery_output(row_dir),
            "researcher_prompt_ref": researcher_prompt_ref,
            "final_output": str(getattr(result, "final_output", "")),
        }

    return predict


class DiscoveryQualityJudge(weave.Scorer):
    """LLM-as-judge scorer for accepted discovery findings."""

    model_id: str = "gpt-5.4-mini"

    @weave.op()
    def score(self, output: dict[str, Any]) -> dict[str, Any]:
        if output.get("scope_status") != "accepted":
            return {
                "scope_status": output.get("scope_status") or "unknown",
                "not_accepted_reason": output.get("verdict_reason") or "No accepted finding to score.",
                "failure_modes": [],
            }

        prompt = _judge_prompt(output)
        from openai import OpenAI

        response = OpenAI().responses.create(
            model=self.model_id,
            input=prompt,
        )
        text = getattr(response, "output_text", "") or "{}"
        parsed = _parse_judge_json(text)
        rating = str(parsed.get("rating") or "neutral").lower()
        if rating not in {"good", "neutral", "bad"}:
            rating = "neutral"
        failure_modes = parsed.get("failure_modes")
        if not isinstance(failure_modes, list):
            failure_modes = []
        quality_score = {"good": 1.0, "neutral": 0.5, "bad": 0.0}[rating]
        return {
            "rating": rating,
            "quality_score": quality_score,
            "bad_accept": rating == "bad",
            "reason": str(parsed.get("reason") or ""),
            "failure_modes": [str(item) for item in failure_modes],
        }


def _parse_judge_json(text: str) -> dict[str, Any]:
    """Parse strict JSON from the judge, tolerating occasional fenced output."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if match is None:
            return {
                "rating": "neutral",
                "reason": text,
                "failure_modes": ["invalid_judge_json"],
            }
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {
                "rating": "neutral",
                "reason": text,
                "failure_modes": ["invalid_judge_json"],
            }
    return parsed if isinstance(parsed, dict) else {
        "rating": "neutral",
        "reason": text,
        "failure_modes": ["invalid_judge_json"],
    }


def aggregate_discovery_metrics(judgments: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate judge outputs into a small set of discovery quality metrics."""
    judged_findings = [row for row in judgments if _has_quality_score(row)]
    judged_count = len(judged_findings)
    quality_scores = [_quality_score(row) for row in judged_findings]
    bad_accept_count = sum(
        1
        for row in judged_findings
        if row.get("bad_accept") is True or row.get("rating") == "bad"
    )
    rejected_count = sum(1 for row in judgments if row.get("scope_status") == "rejected")
    no_new_count = sum(1 for row in judgments if row.get("scope_status") == "no_new")
    denominator = judged_count or 1
    return {
        "judged_count": judged_count,
        "quality_score_mean": sum(quality_scores) / denominator if judged_count else None,
        "bad_accept_count": bad_accept_count,
        "bad_accept_rate": bad_accept_count / denominator if judged_count else None,
        "rejected_count": rejected_count,
        "no_new_count": no_new_count,
    }


def _has_quality_score(row: dict[str, Any]) -> bool:
    return isinstance(row.get("quality_score"), int | float) or str(row.get("rating") or "").lower() in {
        "good",
        "neutral",
        "bad",
    }


def _quality_score(row: dict[str, Any]) -> float:
    score = row.get("quality_score")
    if isinstance(score, int | float):
        return float(score)
    return {"good": 1.0, "neutral": 0.5, "bad": 0.0}.get(str(row.get("rating") or "").lower(), 0.5)


def run_discovery_evaluation(
    *,
    dataset_path: Path | None = None,
    dataset_ref: str | None = None,
    output_dir: Path,
    search_backend: SearchBackend = DEFAULT_SEARCH_BACKEND,
    evaluation_name: str = "Discovery Quality Eval",
    limit: int | None = None,
    judge_model: str = "gpt-5.4-mini",
    researcher_prompt_ref: str | None = None,
) -> Any:
    """Run the ResearcherAgent discovery quality evaluation in Weave."""
    dataset = load_eval_dataset(dataset_path=dataset_path, dataset_ref=dataset_ref)
    rows = dataset_rows(dataset)
    if limit is not None:
        rows = rows[:limit]
    output_dir.mkdir(parents=True, exist_ok=True)
    predict = make_discovery_eval_predict_fn(
        output_dir=output_dir,
        search_backend=search_backend,
        researcher_prompt_ref=researcher_prompt_ref,
    )
    evaluation = DiscoveryQualityEvaluation(
        dataset=rows,
        scorers=[DiscoveryQualityJudge(model_id=judge_model)],
        evaluation_name=evaluation_name,
        researcher_prompt_ref=researcher_prompt_ref,
    )
    return asyncio.run(evaluation.evaluate(predict))


def _render_discovery_prompt(*, search_brief: str, recency: str | None) -> str:
    recency_hint = f"\nRecency: prefer sources from the last {recency}." if recency else ""
    return (
        "Run one offline discovery evaluation attempt.\n\n"
        f"Search brief: {search_brief}"
        f"{recency_hint}\n\n"
        "Find one candidate that best satisfies the brief. "
        "If it is useful, call save_source_tool and save_tool_profile_tool. "
        "If it is clearly unsuitable, call save_rejected_profile_tool. "
        "If no useful candidate is found, call report_no_new_tool."
    )


def _read_discovery_output(output_dir: Path) -> dict[str, Any]:
    rejected = _read_latest_jsonl(output_dir / "_rejected_profiles.jsonl")
    if rejected is not None:
        return {
            "scope_status": "rejected",
            "verdict_reason": rejected.get("verdict_reason"),
            "profile": None,
        }
    no_new = _read_latest_jsonl(output_dir / "_no_new_tool.jsonl")
    if no_new is not None:
        return {
            "scope_status": "no_new",
            "verdict_reason": no_new.get("verdict_reason") or no_new.get("reason"),
            "profile": None,
        }
    tools_dir = output_dir / "tools"
    profiles = sorted(tools_dir.glob("*.md")) if tools_dir.exists() else []
    if profiles:
        profile = _read_profile_frontmatter(profiles[-1])
        return {
            "scope_status": "accepted",
            "verdict_reason": None,
            "profile": profile,
        }
    return {
        "scope_status": "unknown",
        "verdict_reason": "Researcher did not save, reject, or report no-new.",
        "profile": None,
    }


def _read_latest_jsonl(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return rows[-1] if rows else None


def _read_profile_frontmatter(path: Path) -> dict[str, Any]:
    content = path.read_text()
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    data = yaml.safe_load(parts[1]) or {}
    return data if isinstance(data, dict) else {}


def _safe_name(value: str) -> str:
    import re

    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-").lower()
    return slug or next(tempfile._get_candidate_names())


def _ref_uri(ref: Any) -> str | None:
    uri = getattr(ref, "uri", None)
    if callable(uri):
        return uri()
    if isinstance(uri, str):
        return uri
    if ref is not None:
        return str(ref)
    return None


def _judge_prompt(output: dict[str, Any]) -> str:
    profile = output.get("profile") if isinstance(output.get("profile"), dict) else {}
    return (
        "You are judging a ResearcherAgent discovery result.\n"
        "Rate whether this accepted finding should count as a high-quality discovery.\n\n"
        "Good: standalone system with visible action -> evaluation -> feedback/memory -> improvement loop, supported by primary-source evidence.\n"
        "Neutral: plausible but evidence is weak, metadata is incomplete, or it is a borderline framework/component that may still be useful.\n"
        "Bad: curated list, topic page, cookbook/example, generic framework, memory-only infrastructure, testing-only tool, or no visible improvement loop.\n\n"
        "Do not reward popularity alone. Judge whether this should enter the feed as an accepted discovery.\n"
        "Return only strict JSON with keys: rating, reason, failure_modes.\n\n"
        f"Search brief: {output.get('search_brief')}\n"
        f"Profile JSON: {json.dumps(profile, ensure_ascii=False, default=str)}"
    )

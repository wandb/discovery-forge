"""Tests for Profiler Weave Evaluation helpers."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch


def test_scope_decision_scorer_matches_expected():
    from autoresearch_researcher.tools.evaluation import scope_decision_scorer

    score = scope_decision_scorer({"scope_status": "accepted"}, "accepted")

    assert score["passed"] is True
    assert score["observed"] == "accepted"


def test_scope_decision_scorer_reports_mismatch():
    from autoresearch_researcher.tools.evaluation import scope_decision_scorer

    score = scope_decision_scorer(
        {"scope_status": "accepted", "rejection_reason": None},
        "rejected",
    )

    assert score["passed"] is False
    assert score["expected"] == "rejected"
    assert score["observed"] == "accepted"


def test_profile_quality_scorer_scores_rejection_reason():
    from autoresearch_researcher.tools.evaluation import profile_quality_scorer

    score = profile_quality_scorer(
        {
            "scope_status": "rejected",
            "rejection_reason": "Rejected as out of scope: this is a curated resource list, not a tool.",
        },
        "rejected",
        "out_of_scope",
    )

    assert score["passed"] is True
    assert score["category_match"] is True


def test_profile_quality_scorer_scores_accepted_profile_completeness():
    from autoresearch_researcher.tools.evaluation import profile_quality_scorer

    score = profile_quality_scorer(
        {
            "scope_status": "accepted",
            "profile": {
                "license": "Apache-2.0",
                "domains": ["ml"],
                "autonomy_level": "Scientist",
                "autonomy_rationale": "Runs experiment loops.",
                "interface": "CLI",
                "resource_requirements": "GPU",
                "key_limitations": ["Requires compute."],
                "github_url": "https://github.com/example/tool",
                "paper_url": None,
                "project_url": None,
                "source_ids": [0],
            },
        },
        "accepted",
    )

    assert score["passed"] is True
    assert score["missing_fields"] == []


def test_profile_quality_scorer_allows_unknown_advisory_fields():
    from autoresearch_researcher.tools.evaluation import profile_quality_scorer

    score = profile_quality_scorer(
        {
            "scope_status": "accepted",
            "profile": {
                "license": "unknown",
                "domains": ["ml"],
                "autonomy_level": "Scientist",
                "autonomy_rationale": "Runs experiment loops.",
                "interface": "CLI",
                "resource_requirements": "unknown",
                "key_limitations": ["Requires compute."],
                "github_url": "https://github.com/example/tool",
                "paper_url": None,
                "project_url": None,
                "source_ids": [0],
            },
        },
        "accepted",
    )

    assert score["passed"] is True
    assert score["missing_fields"] == []
    assert score["unknown_advisory_fields"] == ["license", "resource_requirements"]


def test_profile_quality_scorer_still_requires_core_profile_fields():
    from autoresearch_researcher.tools.evaluation import profile_quality_scorer

    score = profile_quality_scorer(
        {
            "scope_status": "accepted",
            "profile": {
                "license": "Apache-2.0",
                "domains": ["ml"],
                "autonomy_level": "Scientist",
                "autonomy_rationale": "Runs experiment loops.",
                "interface": "CLI",
                "resource_requirements": "GPU",
                "key_limitations": ["unknown"],
                "github_url": "https://github.com/example/tool",
                "source_ids": [0],
            },
        },
        "accepted",
    )

    assert score["passed"] is False
    assert score["missing_fields"] == ["key_limitations"]


def test_read_profiler_output_prefers_rejected_profile(tmp_path):
    from autoresearch_researcher.tools.evaluation import _read_profiler_output

    rejected = {
        "slug": "tool-a",
        "name": "Tool A",
        "rejection_reason": "Rejected as out of scope.",
    }
    (tmp_path / "_rejected_profiles.jsonl").write_text(json.dumps(rejected) + "\n")

    output = _read_profiler_output(tmp_path)

    assert output["scope_status"] == "rejected"
    assert output["rejection_reason"] == "Rejected as out of scope."


def test_profiler_eval_predict_fn_returns_saved_profile(tmp_path):
    from autoresearch_researcher.tools.evaluation import make_profiler_eval_predict_fn

    async def fake_run(agent, input, max_turns):
        tools_dir = tmp_path / "tool-a" / "tools"
        tools_dir.mkdir(parents=True)
        (tools_dir / "tool-a.md").write_text(
            "---\n"
            "license: Apache-2.0\n"
            "domains: [ml]\n"
            "autonomy_level: Scientist\n"
            "autonomy_rationale: Runs experiments.\n"
            "interface: CLI\n"
            "resource_requirements: GPU\n"
            "key_limitations: [Requires compute]\n"
            "github_url: https://github.com/example/tool-a\n"
            "paper_url: null\n"
            "project_url: null\n"
            "source_ids: [0]\n"
            "---\n"
        )
        return type("Result", (), {"final_output": "done"})()

    predict = make_profiler_eval_predict_fn(output_dir=tmp_path)
    with patch("autoresearch_researcher.tools.evaluation.Runner.run", new=AsyncMock(side_effect=fake_run)):
        import asyncio

        output = asyncio.run(
            predict(
                input_tool_name="Tool A",
                input_candidate_url="https://github.com/example/tool-a",
                input_candidate_description="Runs experiments.",
            )
        )

    assert output["scope_status"] == "accepted"
    assert output["profile"]["license"] == "Apache-2.0"


def test_run_profiler_evaluation_uses_local_rows_without_publishing_dataset(tmp_path):
    from autoresearch_researcher.tools import evaluation as evaluation_module

    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        json.dumps({
            "input_tool_name": "Tool A",
            "input_candidate_url": "https://example.com/tool-a",
            "input_candidate_description": "Runs experiments.",
            "expected_scope_status": "accepted",
            "expected_issue_category": None,
        }) + "\n"
    )
    captured = {}

    class FakeEvaluation:
        def __init__(self, *, dataset, scorers, evaluation_name):
            captured["dataset"] = dataset
            captured["scorers"] = scorers
            captured["evaluation_name"] = evaluation_name

        async def evaluate(self, model):
            captured["model"] = model
            return {"ok": True}

    with patch.object(evaluation_module.weave, "Dataset") as dataset_cls, \
        patch.object(evaluation_module.weave, "Evaluation", FakeEvaluation):
        result = evaluation_module.run_profiler_evaluation(
            dataset_path=dataset_path,
            output_dir=tmp_path / "out",
        )

    dataset_cls.assert_not_called()
    assert result == {"ok": True}
    assert isinstance(captured["dataset"], list)
    assert captured["dataset"][0]["input_tool_name"] == "Tool A"
    assert callable(captured["model"])


def test_run_profiler_evaluation_reuses_dataset_ref_object(tmp_path):
    from autoresearch_researcher.tools import evaluation as evaluation_module

    fake_dataset = type("FakeDataset", (), {"rows": [{"input_tool_name": "Tool A"}]})()
    captured = {}

    class FakeRef:
        def get(self):
            return fake_dataset

    class FakeEvaluation:
        def __init__(self, *, dataset, scorers, evaluation_name):
            captured["dataset"] = dataset

        async def evaluate(self, model):
            return {"ok": True}

    with patch.object(evaluation_module.weave, "ref", return_value=FakeRef()) as ref, \
        patch.object(evaluation_module.weave, "Dataset") as dataset_cls, \
        patch.object(evaluation_module.weave, "Evaluation", FakeEvaluation):
        result = evaluation_module.run_profiler_evaluation(
            dataset_ref="weave:///entity/project/object/profiler-eval-dataset:v1",
            output_dir=tmp_path / "out",
        )

    assert result == {"ok": True}
    ref.assert_called_once_with("weave:///entity/project/object/profiler-eval-dataset:v1")
    dataset_cls.assert_not_called()
    assert captured["dataset"] is fake_dataset

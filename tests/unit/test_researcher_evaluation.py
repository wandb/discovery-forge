"""Tests for ResearcherAgent Weave Evaluation helpers."""

import json
from unittest.mock import AsyncMock, patch


def test_verdict_quality_scorer_matches_expected():
    from discovery_forge.evaluation.verdict import verdict_quality_scorer

    score = verdict_quality_scorer({"scope_status": "accepted"}, "accepted")

    assert score["is_correct"] is True
    assert score["observed"] == "accepted"


def test_verdict_quality_scorer_reports_mismatch():
    from discovery_forge.evaluation.verdict import verdict_quality_scorer

    score = verdict_quality_scorer(
        {"scope_status": "accepted", "verdict_reason": None},
        "rejected",
    )

    assert score["is_correct"] is False
    assert score["expected"] == "rejected"
    assert score["observed"] == "accepted"


def test_profile_quality_scorer_scores_verdict_reason():
    from discovery_forge.evaluation.verdict import profile_quality_scorer

    score = profile_quality_scorer(
        {
            "scope_status": "rejected",
            "verdict_reason": "Rejected as out of scope: this is a curated resource list, not a tool.",
        },
        "rejected",
        "out_of_scope",
    )

    assert score["passed"] is True
    assert score["category_match"] is True


def test_profile_quality_scorer_scores_accepted_profile_completeness():
    from discovery_forge.evaluation.verdict import profile_quality_scorer

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
    from discovery_forge.evaluation.verdict import profile_quality_scorer

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
    from discovery_forge.evaluation.verdict import profile_quality_scorer

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


def test_researcher_eval_predict_fn_returns_saved_profile(tmp_path):
    from discovery_forge.evaluation.verdict import make_researcher_eval_predict_fn
    from discovery_forge.schemas.tool_profile import ToolProfile

    captured = {}

    def fake_build_researcher_agent(**kwargs):
        captured.update(kwargs)
        return object()

    async def fake_run(agent, input, max_turns):
        captured["save_tool_profile_callback"](
            ToolProfile(
                slug="tool-a",
                name="Tool A",
                license="Apache-2.0",
                domains=["ml"],
                autonomy_level="Scientist",
                autonomy_rationale="Runs experiments.",
                interface="CLI",
                resource_requirements="GPU",
                last_commit=None,
                stars=None,
                open_issues=None,
                pricing_note="unknown",
                key_limitations=["Requires compute"],
                github_url="https://github.com/example/tool-a",
                paper_url=None,
                project_url=None,
                source_ids=[0],
            )
        )
        return type("Result", (), {"final_output": "done"})()

    predict = make_researcher_eval_predict_fn(output_dir=tmp_path)
    with patch("discovery_forge.evaluation.verdict.build_researcher_agent", side_effect=fake_build_researcher_agent), \
        patch("discovery_forge.evaluation.verdict.Runner.run", new=AsyncMock(side_effect=fake_run)):
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


def test_researcher_eval_predict_fn_ignores_stale_row_output(tmp_path):
    from discovery_forge.evaluation.verdict import make_researcher_eval_predict_fn
    from discovery_forge.schemas.tool_profile import ToolProfile

    stale_dir = tmp_path / "tool-a"
    stale_dir.mkdir()
    (stale_dir / "_rejected_profiles.jsonl").write_text(
        json.dumps({"verdict_reason": "Stale rejection."}) + "\n"
    )
    captured = {}

    def fake_build_researcher_agent(**kwargs):
        captured.update(kwargs)
        return object()

    async def fake_run(agent, input, max_turns):
        captured["save_tool_profile_callback"](
            ToolProfile(
                slug="tool-a",
                name="Tool A",
                license="Apache-2.0",
                domains=["ml"],
                autonomy_level="Scientist",
                autonomy_rationale="Runs experiments.",
                interface="CLI",
                resource_requirements="GPU",
                last_commit=None,
                stars=None,
                open_issues=None,
                pricing_note="unknown",
                key_limitations=["Requires compute"],
                github_url="https://github.com/example/tool-a",
                paper_url=None,
                project_url=None,
                source_ids=[0],
            )
        )
        return type("Result", (), {"final_output": "done"})()

    predict = make_researcher_eval_predict_fn(output_dir=tmp_path)
    with patch("discovery_forge.evaluation.verdict.build_researcher_agent", side_effect=fake_build_researcher_agent), \
        patch("discovery_forge.evaluation.verdict.Runner.run", new=AsyncMock(side_effect=fake_run)):
        import asyncio

        output = asyncio.run(
            predict(
                input_tool_name="Tool A",
                input_candidate_url="https://github.com/example/tool-a",
                input_candidate_description="Runs experiments.",
            )
        )

    assert (stale_dir / "_rejected_profiles.jsonl").exists()
    assert output["scope_status"] == "accepted"


def test_researcher_eval_predict_fn_returns_rejected_profile(tmp_path):
    from discovery_forge.evaluation.verdict import make_researcher_eval_predict_fn
    from discovery_forge.schemas.tool_profile import RejectedProfile

    captured = {}

    def fake_build_researcher_agent(**kwargs):
        captured.update(kwargs)
        return object()

    async def fake_run(agent, input, max_turns):
        captured["save_rejected_profile_callback"](
            RejectedProfile(
                slug="tool-a",
                name="Tool A",
                verdict_reason="Rejected as out of scope.",
                github_url="https://github.com/example/tool-a",
            )
        )
        return type("Result", (), {"final_output": "rejected"})()

    predict = make_researcher_eval_predict_fn(output_dir=tmp_path)
    with patch("discovery_forge.evaluation.verdict.build_researcher_agent", side_effect=fake_build_researcher_agent), \
        patch("discovery_forge.evaluation.verdict.Runner.run", new=AsyncMock(side_effect=fake_run)):
        import asyncio

        output = asyncio.run(
            predict(
                input_tool_name="Tool A",
                input_candidate_url="https://github.com/example/tool-a",
                input_candidate_description="Generic framework.",
            )
        )

    assert output["scope_status"] == "rejected"
    assert output["verdict_reason"] == "Rejected as out of scope."


def test_run_researcher_evaluation_uses_local_rows_without_publishing_dataset(tmp_path):
    from discovery_forge.evaluation import verdict as evaluation_module

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
        def __init__(self, *, dataset, scorers, evaluation_name, researcher_prompt_ref=None):
            captured["dataset"] = dataset
            captured["scorers"] = scorers
            captured["evaluation_name"] = evaluation_name
            captured["researcher_prompt_ref"] = researcher_prompt_ref

        async def evaluate(self, model):
            captured["model"] = model
            return {"ok": True}

    with patch.object(evaluation_module.weave, "Dataset") as dataset_cls, \
        patch.object(evaluation_module, "load_prompt_ref_content", return_value="Prompt v1") as load_prompt, \
        patch.object(evaluation_module, "VerdictQualityEvaluation", FakeEvaluation):
        result = evaluation_module.run_researcher_evaluation(
            dataset_path=dataset_path,
            output_dir=tmp_path / "out",
            researcher_prompt_ref="weave:///prompt:v1",
        )

    dataset_cls.assert_not_called()
    load_prompt.assert_called_once_with("weave:///prompt:v1")
    assert result == {"ok": True}
    assert isinstance(captured["dataset"], list)
    assert captured["dataset"][0]["input_tool_name"] == "Tool A"
    assert [scorer.__name__ for scorer in captured["scorers"]] == ["verdict_quality_scorer"]
    assert captured["evaluation_name"] == "Verdict Quality Eval"
    assert captured["researcher_prompt_ref"] == "weave:///prompt:v1"
    assert callable(captured["model"])


def test_run_researcher_evaluation_reuses_dataset_ref_object(tmp_path):
    from discovery_forge.evaluation import verdict as evaluation_module

    fake_dataset = type("FakeDataset", (), {"rows": [{"input_tool_name": "Tool A"}]})()
    captured = {}

    class FakeRef:
        def get(self):
            return fake_dataset

    class FakeEvaluation:
        def __init__(self, *, dataset, scorers, evaluation_name, researcher_prompt_ref=None):
            captured["dataset"] = dataset
            captured["researcher_prompt_ref"] = researcher_prompt_ref

        async def evaluate(self, model):
            return {"ok": True}

    with patch.object(evaluation_module.weave, "ref", return_value=FakeRef()) as ref, \
        patch.object(evaluation_module.weave, "Dataset") as dataset_cls, \
        patch.object(evaluation_module, "VerdictQualityEvaluation", FakeEvaluation):
        result = evaluation_module.run_researcher_evaluation(
            dataset_ref="weave:///entity/project/object/researcher-eval-dataset:v1",
            output_dir=tmp_path / "out",
        )

    assert result == {"ok": True}
    ref.assert_called_once_with("weave:///entity/project/object/researcher-eval-dataset:v1")
    dataset_cls.assert_not_called()
    # The versioned Dataset object is passed straight through (no limit), so the
    # Evaluation stays linked to the published dataset instead of creating an
    # anonymous `Dataset` object.
    assert captured["dataset"] is fake_dataset


def test_run_researcher_evaluation_ref_with_limit_uses_rows(tmp_path):
    from discovery_forge.evaluation import verdict as evaluation_module

    fake_dataset = type(
        "FakeDataset",
        (),
        {"rows": [{"input_tool_name": "Tool A"}, {"input_tool_name": "Tool B"}]},
    )()
    captured = {}

    class FakeRef:
        def get(self):
            return fake_dataset

    class FakeEvaluation:
        def __init__(self, *, dataset, scorers, evaluation_name, researcher_prompt_ref=None):
            captured["dataset"] = dataset

        async def evaluate(self, model):
            return {"ok": True}

    with patch.object(evaluation_module.weave, "ref", return_value=FakeRef()), \
        patch.object(evaluation_module.weave, "Dataset") as dataset_cls, \
        patch.object(evaluation_module, "VerdictQualityEvaluation", FakeEvaluation):
        result = evaluation_module.run_researcher_evaluation(
            dataset_ref="weave:///entity/project/object/researcher-eval-dataset:v1",
            output_dir=tmp_path / "out",
            limit=1,
        )

    assert result == {"ok": True}
    dataset_cls.assert_not_called()
    # With a limit, rows are sliced into a list (the version link is not needed
    # for a truncated debug run).
    assert captured["dataset"] == [{"input_tool_name": "Tool A"}]

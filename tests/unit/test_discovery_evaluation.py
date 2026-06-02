import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from autoresearch_researcher.cli import app


runner = CliRunner()


def test_load_jsonl_rows_reads_discovery_dataset(tmp_path):
    from autoresearch_researcher.tools.discovery_evaluation import load_jsonl_rows

    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        json.dumps({"id": "row-1", "search_brief": "Find one tool."}) + "\n"
    )

    rows = load_jsonl_rows(dataset_path)

    assert rows == [{"id": "row-1", "search_brief": "Find one tool."}]


def test_publish_eval_dataset_uses_weave_dataset(tmp_path):
    from autoresearch_researcher.tools import discovery_evaluation as module

    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        json.dumps({"id": "row-1", "search_brief": "Find one tool."}) + "\n"
    )
    captured = {}

    class FakeDataset:
        def __init__(self, *, name, rows):
            captured["name"] = name
            captured["rows"] = rows

    class FakeRef:
        def uri(self):
            return "weave:///entity/project/object/researcher_discovery_precision_dataset:v1"

    with patch.object(module.weave, "Dataset", FakeDataset), \
        patch.object(module.weave, "publish", return_value=FakeRef()) as publish:
        result = module.publish_eval_dataset(
            dataset_path,
            name="researcher_discovery_precision_dataset",
        )

    publish.assert_called_once()
    assert captured["name"] == "researcher_discovery_precision_dataset"
    assert captured["rows"] == [{"id": "row-1", "search_brief": "Find one tool."}]
    assert result["row_count"] == 1
    assert result["ref"].endswith("researcher_discovery_precision_dataset:v1")


def test_make_discovery_eval_predict_fn_reads_saved_profile(tmp_path):
    from autoresearch_researcher.tools.discovery_evaluation import make_discovery_eval_predict_fn

    async def fake_run(agent, input, max_turns):
        row_dir = tmp_path / "row-1" / "tools"
        row_dir.mkdir(parents=True)
        (row_dir / "tool-a.md").write_text(
            "---\n"
            "slug: tool-a\n"
            "name: Tool A\n"
            "domains: [ml]\n"
            "autonomy_level: Scientist\n"
            "autonomy_rationale: Runs eval loops.\n"
            "interface: CLI\n"
            "key_limitations: [Needs compute]\n"
            "github_url: https://github.com/example/tool-a\n"
            "source_ids: [0]\n"
            "---\n"
        )
        return type("Result", (), {"final_output": "done"})()

    predict = make_discovery_eval_predict_fn(output_dir=tmp_path)
    with patch(
        "autoresearch_researcher.tools.discovery_evaluation.Runner.run",
        new=AsyncMock(side_effect=fake_run),
    ):
        output = asyncio.run(
            predict(id="row-1", search_brief="Find one autonomous tool.")
        )

    assert output["scope_status"] == "accepted"
    assert output["row_id"] == "row-1"
    assert output["profile"]["slug"] == "tool-a"


def test_aggregate_discovery_metrics_computes_quality_rates():
    from autoresearch_researcher.tools.discovery_evaluation import aggregate_discovery_metrics

    metrics = aggregate_discovery_metrics([
        {"rating": "good", "quality_score": 1.0},
        {"rating": "neutral", "quality_score": 0.5},
        {"rating": "bad", "quality_score": 0.0, "bad_accept": True},
        {"scope_status": "rejected"},
        {"scope_status": "no_new"},
    ])

    assert metrics["judged_count"] == 3
    assert metrics["quality_score_mean"] == 0.5
    assert metrics["bad_accept_count"] == 1
    assert metrics["bad_accept_rate"] == 1 / 3
    assert metrics["rejected_count"] == 1
    assert metrics["no_new_count"] == 1


def test_discovery_quality_judge_exposes_minimal_quality_metrics():
    from autoresearch_researcher.tools.discovery_evaluation import DiscoveryQualityJudge

    class FakeResponses:
        def create(self, *, model, input):
            return type(
                "Response",
                (),
                {
                    "output_text": json.dumps({
                        "rating": "bad",
                        "reason": "Accepted item is a curated list.",
                        "failure_modes": ["curated_list"],
                    })
                },
            )()

    class FakeOpenAI:
        def __init__(self):
            self.responses = FakeResponses()

    output = {
        "scope_status": "accepted",
        "search_brief": "Find one self-improving agent.",
        "profile": {"name": "Awesome Agents", "domains": ["agents"]},
    }
    with patch("openai.OpenAI", FakeOpenAI):
        score = DiscoveryQualityJudge(model_id="gpt-test").score(output)

    assert score["rating"] == "bad"
    assert score["quality_score"] == 0.0
    assert score["bad_accept"] is True


def test_discovery_quality_judge_skips_non_accepted_outputs():
    from autoresearch_researcher.tools.discovery_evaluation import DiscoveryQualityJudge

    score = DiscoveryQualityJudge(model_id="gpt-test").score({
        "scope_status": "rejected",
        "verdict_reason": "Curated list, not a runnable system.",
    })

    assert score == {
        "scope_status": "rejected",
        "not_accepted_reason": "Curated list, not a runnable system.",
        "failure_modes": [],
    }


def test_run_discovery_evaluation_reuses_dataset_ref(tmp_path):
    from autoresearch_researcher.tools import discovery_evaluation as module

    fake_dataset = type("FakeDataset", (), {"rows": [{"id": "row-1", "search_brief": "Find one tool."}]})()
    captured = {}

    class FakeRef:
        def get(self):
            return fake_dataset

    class FakeEvaluation:
        def __init__(self, *, dataset, scorers, evaluation_name, researcher_prompt_ref=None):
            captured["dataset"] = dataset
            captured["scorers"] = scorers
            captured["evaluation_name"] = evaluation_name
            captured["researcher_prompt_ref"] = researcher_prompt_ref

        async def evaluate(self, model):
            captured["model"] = model
            return {"ok": True}

    with patch.object(module.weave, "ref", return_value=FakeRef()) as ref, \
        patch.object(module, "load_prompt_ref_content", return_value="Prompt v1") as load_prompt, \
        patch.object(module, "DiscoveryQualityEvaluation", FakeEvaluation):
        result = module.run_discovery_evaluation(
            dataset_ref="weave:///entity/project/object/researcher_discovery_precision_dataset:v1",
            output_dir=tmp_path / "out",
            judge_model="gpt-test",
            researcher_prompt_ref="weave:///prompt:v1",
        )

    assert result == {"ok": True}
    ref.assert_called_once()
    load_prompt.assert_called_once_with("weave:///prompt:v1")
    assert captured["dataset"] == [{"id": "row-1", "search_brief": "Find one tool."}]
    assert captured["evaluation_name"] == "Discovery Quality Eval"
    assert captured["researcher_prompt_ref"] == "weave:///prompt:v1"
    assert callable(captured["model"])


def test_eval_publish_dataset_cli_wires_arguments(tmp_path):
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(json.dumps({"id": "row-1"}) + "\n")

    with patch("autoresearch_researcher.orchestrator.init_observability"), \
        patch(
            "autoresearch_researcher.tools.discovery_evaluation.publish_eval_dataset",
            return_value={"name": "test_dataset", "row_count": 1, "ref": "weave:///dataset:v1"},
        ) as publish:
        result = runner.invoke(app, [
            "eval",
            "publish-dataset",
            "--dataset",
            str(dataset_path),
            "--name",
            "test_dataset",
        ])

    assert result.exit_code == 0, result.output
    publish.assert_called_once_with(dataset_path, name="test_dataset")
    assert "weave:///dataset:v1" in result.output


def test_eval_run_discovery_cli_wires_arguments(tmp_path):
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(json.dumps({"id": "row-1", "search_brief": "Find one tool."}) + "\n")

    with patch("autoresearch_researcher.orchestrator.init_observability"), \
        patch(
            "autoresearch_researcher.tools.discovery_evaluation.run_discovery_evaluation",
            return_value={"ok": True},
        ) as run_eval:
        result = runner.invoke(app, [
            "eval",
            "run-discovery",
            "--dataset",
            str(dataset_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--limit",
            "1",
            "--judge-model",
            "gpt-test",
        ])

    assert result.exit_code == 0, result.output
    run_eval.assert_called_once_with(
        dataset_path=dataset_path,
        dataset_ref=None,
        output_dir=tmp_path / "out",
        search_backend="serper",
        limit=1,
        judge_model="gpt-test",
        researcher_prompt_ref=None,
    )

import json
from unittest.mock import patch


def test_get_eval_dataset_ref_reads_yaml_config(tmp_path):
    from discovery_forge.evaluation.datasets import get_eval_dataset_ref

    config_path = tmp_path / "evaluation_config.yaml"
    config_path.write_text(
        "\n".join([
            "datasets:",
            "  verdict_quality:",
            "    name: verdict_quality_dataset",
            "    ref: weave:///entity/project/object/verdict_quality_dataset:v1",
            "",
        ])
    )

    ref = get_eval_dataset_ref("verdict_quality", config_path=config_path)

    assert ref == "weave:///entity/project/object/verdict_quality_dataset:v1"


def test_get_eval_dataset_ref_requires_configured_dataset(tmp_path):
    from discovery_forge.evaluation.datasets import get_eval_dataset_ref

    config_path = tmp_path / "evaluation_config.yaml"
    config_path.write_text("datasets: {}\n")

    try:
        get_eval_dataset_ref("missing_dataset", config_path=config_path)
    except KeyError as exc:
        assert "missing_dataset" in str(exc)
    else:
        raise AssertionError("Expected missing dataset key to raise KeyError")


def test_load_jsonl_rows_reads_eval_dataset(tmp_path):
    from discovery_forge.evaluation.datasets import load_jsonl_rows

    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        json.dumps({"id": "row-1", "input_tool_name": "Tool A"}) + "\n"
    )

    rows = load_jsonl_rows(dataset_path)

    assert rows == [{"id": "row-1", "input_tool_name": "Tool A"}]


def test_publish_eval_dataset_uses_weave_dataset(tmp_path):
    from discovery_forge.evaluation import datasets as module

    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        json.dumps({"id": "row-1", "input_tool_name": "Tool A"}) + "\n"
    )
    captured = {}

    class FakeDataset:
        def __init__(self, *, name, rows):
            captured["name"] = name
            captured["rows"] = rows

    class FakeRef:
        def uri(self):
            return "weave:///entity/project/object/verdict_quality_dataset:v1"

    with patch.object(module.weave, "Dataset", FakeDataset), \
        patch.object(module.weave, "publish", return_value=FakeRef()) as publish:
        result = module.publish_eval_dataset(
            dataset_path,
            name="verdict_quality_dataset",
        )

    publish.assert_called_once()
    assert captured["name"] == "verdict_quality_dataset"
    assert captured["rows"] == [{"id": "row-1", "input_tool_name": "Tool A"}]
    assert result["row_count"] == 1
    assert result["ref"].endswith("verdict_quality_dataset:v1")


def test_evaluate_entrypoint_runs_verdict_ref(tmp_path, monkeypatch):
    import evaluate

    monkeypatch.setattr("sys.argv", [
        "evaluate.py",
        "--verdict-dataset-ref",
        "weave:///verdict:v1",
        "--output-dir",
        str(tmp_path / "eval_runs"),
        "--limit",
        "1",
    ])
    with patch.object(evaluate, "init_observability"), \
        patch.object(evaluate, "run_researcher_evaluation", return_value={"verdict": True}) as verdict_eval:
        evaluate.main()

    verdict_eval.assert_called_once_with(
        dataset_ref="weave:///verdict:v1",
        output_dir=tmp_path / "eval_runs" / "verdict",
        search_backend="serper",
        limit=1,
        researcher_prompt_ref=None,
    )


def test_evaluate_entrypoint_resolves_configured_dataset_key(tmp_path, monkeypatch):
    import evaluate

    monkeypatch.setattr("sys.argv", [
        "evaluate.py",
        "--verdict-dataset-key",
        "verdict_quality",
        "--output-dir",
        str(tmp_path / "eval_runs"),
    ])
    with patch.object(evaluate, "init_observability"), \
        patch.object(evaluate, "get_eval_dataset_ref", return_value="weave:///verdict:v2") as get_ref, \
        patch.object(evaluate, "run_researcher_evaluation", return_value={"verdict": True}) as verdict_eval:
        evaluate.main()

    get_ref.assert_called_once_with("verdict_quality")
    verdict_eval.assert_called_once_with(
        dataset_ref="weave:///verdict:v2",
        output_dir=tmp_path / "eval_runs" / "verdict",
        search_backend="serper",
        limit=None,
        researcher_prompt_ref=None,
    )

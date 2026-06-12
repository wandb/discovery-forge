import json
from pathlib import Path
from unittest.mock import patch


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

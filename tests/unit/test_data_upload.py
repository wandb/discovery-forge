import json
from pathlib import Path
from unittest.mock import patch


def test_data_upload_uses_dataset_key_name(tmp_path, monkeypatch, capsys):
    from discovery_forge.evaluation import data_upload

    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(json.dumps({"id": "row-1"}) + "\n")
    monkeypatch.setattr("sys.argv", [
        "data_upload.py",
        str(dataset_path),
        "--dataset-key",
        "verdict_quality",
    ])

    with patch.object(data_upload, "load_dotenv") as load_dotenv, \
        patch.object(data_upload, "weave_project_path", return_value="entity/project") as project_path, \
        patch.object(data_upload.weave, "init") as weave_init, \
        patch.object(data_upload, "get_eval_dataset_name", return_value="verdict_quality_dataset") as get_name, \
        patch.object(
            data_upload,
            "publish_eval_dataset",
            return_value={
                "name": "verdict_quality_dataset",
                "row_count": 1,
                "ref": "weave:///entity/project/object/verdict_quality_dataset:v1",
            },
        ) as publish:
        result = data_upload.main()

    load_dotenv.assert_called_once()
    project_path.assert_called_once()
    weave_init.assert_called_once_with("entity/project")
    get_name.assert_called_once_with("verdict_quality", config_path=Path(data_upload.DATASET_CONFIG_PATH))
    publish.assert_called_once_with(dataset_path, name="verdict_quality_dataset")
    assert result["ref"].endswith("verdict_quality_dataset:v1")
    printed = json.loads(capsys.readouterr().out)
    assert printed["row_count"] == 1


def test_data_upload_name_override_skips_config_lookup(tmp_path, monkeypatch):
    from discovery_forge.evaluation import data_upload

    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(json.dumps({"id": "row-1"}) + "\n")
    monkeypatch.setattr("sys.argv", [
        "data_upload.py",
        str(dataset_path),
        "--name",
        "custom_dataset",
    ])

    with patch.object(data_upload, "weave_project_path", return_value="entity/project"), \
        patch.object(data_upload.weave, "init"), \
        patch.object(data_upload, "get_eval_dataset_name") as get_name, \
        patch.object(
            data_upload,
            "publish_eval_dataset",
            return_value={
                "name": "custom_dataset",
                "row_count": 1,
                "ref": "weave:///entity/project/object/custom_dataset:v1",
            },
        ) as publish:
        result = data_upload.main()

    get_name.assert_not_called()
    publish.assert_called_once_with(dataset_path, name="custom_dataset")
    assert result["name"] == "custom_dataset"

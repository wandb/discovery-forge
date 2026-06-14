"""Evaluation config, dataset load, and publish helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
import weave


EVALUATION_CONFIG_PATH = Path(__file__).with_name("evaluation_config.yaml")
DATASET_CONFIG_PATH = EVALUATION_CONFIG_PATH
VERDICT_DATASET_KEY = "verdict_quality"


def load_dataset_config(config_path: Path = DATASET_CONFIG_PATH) -> dict[str, Any]:
    """Load evaluation config, including pinned dataset refs, from YAML."""
    config = yaml.safe_load(config_path.read_text())
    if not isinstance(config, dict):
        raise ValueError(f"Dataset config must be a mapping: {config_path}")
    datasets = config.get("datasets")
    if not isinstance(datasets, dict):
        raise ValueError(f"Dataset config must define a datasets mapping: {config_path}")
    return config


def get_eval_dataset_config(
    key: str = VERDICT_DATASET_KEY,
    *,
    config_path: Path = DATASET_CONFIG_PATH,
) -> dict[str, str]:
    """Return one configured evaluation dataset entry."""
    datasets = load_dataset_config(config_path)["datasets"]
    try:
        dataset_config = datasets[key]
    except KeyError as exc:
        raise KeyError(f"Unknown evaluation dataset key: {key}") from exc
    if not isinstance(dataset_config, dict):
        raise ValueError(f"Dataset config for {key!r} must be a mapping")

    name = dataset_config.get("name")
    ref = dataset_config.get("ref")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Dataset config for {key!r} must include a non-empty name")
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError(f"Dataset config for {key!r} must include a non-empty ref")
    return {"name": name, "ref": ref}


def get_eval_dataset_ref(
    key: str = VERDICT_DATASET_KEY,
    *,
    config_path: Path = DATASET_CONFIG_PATH,
) -> str:
    """Return the configured published Weave Dataset ref for an evaluation dataset."""
    return get_eval_dataset_config(key, config_path=config_path)["ref"]


def get_eval_dataset_name(
    key: str = VERDICT_DATASET_KEY,
    *,
    config_path: Path = DATASET_CONFIG_PATH,
) -> str:
    """Return the configured Weave Dataset object name."""
    return get_eval_dataset_config(key, config_path=config_path)["name"]


VERDICT_DATASET_NAME = get_eval_dataset_name()
VERDICT_DATASET_REF = get_eval_dataset_ref()


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


def _ref_uri(ref: Any) -> str | None:
    uri = getattr(ref, "uri", None)
    if callable(uri):
        return uri()
    if isinstance(uri, str):
        return uri
    if ref is not None:
        return str(ref)
    return None

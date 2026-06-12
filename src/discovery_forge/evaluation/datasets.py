"""Eval dataset load/publish helpers and dataset name constants."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import weave


VERDICT_DATASET_NAME = "verdict_quality_dataset"

# Published Weave Dataset refs (pinned versions). Offline evaluation loads these
# by ref so each Weave Evaluation stays linked to the versioned Dataset object.
# Update the digests here when a new dataset version is published.
VERDICT_DATASET_REF = (
    "weave:///wandb-smle/discovery-forge/object/"
    "verdict_quality_dataset:acx7n19ZeYniGNb1XNn4C8O61BcOEp4sdR7qlK7JmS8"
)


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

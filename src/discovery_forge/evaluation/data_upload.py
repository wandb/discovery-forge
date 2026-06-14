"""Publish a local evaluation JSONL dataset to Weave."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv
import weave

from discovery_forge.evaluation.datasets import (
    DATASET_CONFIG_PATH,
    VERDICT_DATASET_KEY,
    get_eval_dataset_name,
    publish_eval_dataset,
)
from discovery_forge.observability import weave_project_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dataset_path",
        type=Path,
        help="Local JSONL dataset path to publish.",
    )
    parser.add_argument(
        "--dataset-key",
        default=VERDICT_DATASET_KEY,
        help="Dataset key whose configured name should be used when --name is omitted.",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Weave Dataset object name. Overrides --dataset-key when provided.",
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=DATASET_CONFIG_PATH,
        help="Evaluation config YAML used to resolve --dataset-key.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> dict[str, object]:
    load_dotenv()
    args = parse_args(argv)
    weave.init(weave_project_path())
    dataset_name = args.name or get_eval_dataset_name(
        args.dataset_key,
        config_path=Path(args.config_path),
    )
    result = publish_eval_dataset(args.dataset_path, name=dataset_name)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


if __name__ == "__main__":
    main()

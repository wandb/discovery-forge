"""US2: hands-on Python entrypoint tests."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from discovery_forge.research_run import ResearchRunConfig, run_research


ROOT = Path(__file__).parent.parent.parent


def test_run_research_creates_daily_dir(tmp_path):
    with patch("discovery_forge.observability.init_observability"), \
        patch("discovery_forge.orchestrator.run_briefing", new_callable=AsyncMock):
        day_dir = run_research(ResearchRunConfig(day="2026-05-28", output_dir=tmp_path))

    assert day_dir == tmp_path / "2026-05-28"
    assert day_dir.exists()


def test_run_research_creates_metadata_json(tmp_path):
    with patch("discovery_forge.observability.init_observability"), \
        patch("discovery_forge.orchestrator.run_briefing", new_callable=AsyncMock):
        run_research(ResearchRunConfig(day="2026-05-28", output_dir=tmp_path))

    metadata_path = tmp_path / "2026-05-28" / "run_metadata.json"
    data = json.loads(metadata_path.read_text())
    assert data["day"] == "2026-05-28"
    assert "started_at" in data
    assert "finished_at" in data
    assert "elapsed_seconds" in data


def test_run_research_aborts_if_dir_exists_without_rerun(tmp_path):
    (tmp_path / "2026-05-28").mkdir()

    with pytest.raises(FileExistsError):
        run_research(ResearchRunConfig(day="2026-05-28", output_dir=tmp_path))


def test_run_research_rerun_backs_up_existing_dir(tmp_path):
    with patch("discovery_forge.observability.init_observability"), \
        patch("discovery_forge.orchestrator.run_briefing", new_callable=AsyncMock):
        day_dir = tmp_path / "2026-05-28"
        day_dir.mkdir()
        (day_dir / "manifest.json").write_text("{}")

        run_research(ResearchRunConfig(day="2026-05-28", output_dir=tmp_path, rerun=True))

    backups = [path for path in tmp_path.iterdir() if "backup" in path.name]
    assert len(backups) == 1
    metadata = json.loads((day_dir / "run_metadata.json").read_text())
    assert metadata["previous_manifest_path"] == str(backups[0] / "manifest.json")


def test_run_research_passes_runtime_options(tmp_path):
    with patch("discovery_forge.observability.init_observability"), \
        patch("discovery_forge.orchestrator.run_briefing", new_callable=AsyncMock) as mock_run:
        run_research(
            ResearchRunConfig(
                day="2026-05-28",
                output_dir=tmp_path,
                max_tools=5,
                max_cost_usd=10.0,
                dry_run=True,
                search_backend="perplexity",
                recency="week",
            )
        )

    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["output_dir"] == tmp_path / "2026-05-28"
    assert call_kwargs["max_tools"] == 5
    assert call_kwargs["max_cost_usd"] == 10.0
    assert call_kwargs["dry_run"] is True
    assert call_kwargs["search_backend"] == "perplexity"
    assert call_kwargs["recency"] == "week"


def test_run_research_skips_weave_init_for_dry_run(tmp_path):
    with patch("discovery_forge.observability.init_observability") as init_obs, \
        patch("discovery_forge.orchestrator.run_briefing", new_callable=AsyncMock):
        run_research(ResearchRunConfig(day="2026-05-28", output_dir=tmp_path, dry_run=True))

    init_obs.assert_not_called()


def test_root_main_py_defaults_to_serper_search_backend(monkeypatch):
    module = _load_root_script("main.py", "handson_main_script")
    monkeypatch.setattr(
        "sys.argv",
        ["main.py", "--day", "2026-05-28", "--dry-run"],
    )

    args = module.parse_args()

    assert args.search_backend == "serper"
    assert args.since == "month"
    assert args.max_tools == 10


def test_root_main_py_defaults_day_to_today(monkeypatch):
    module = _load_root_script("main.py", "handson_main_script_default_day")

    class FixedDate:
        @staticmethod
        def today():
            return FixedDate()

        def isoformat(self):
            return "2026-06-07"

    monkeypatch.setattr(module, "date", FixedDate)
    monkeypatch.setattr("sys.argv", ["main.py", "--dry-run"])

    args = module.parse_args()

    assert args.day == "2026-06-07"


def _load_root_script(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

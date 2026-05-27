"""US2: CLI entrypoint tests."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner
from unittest.mock import patch, AsyncMock

from autoresearch_researcher.cli import app

runner = CliRunner()


def test_run_creates_daily_dir(tmp_path):
    with patch("autoresearch_researcher.cli.run_briefing", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = None
        result = runner.invoke(app, ["run", "--day", "2026-05-28", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "2026-05-28").exists()


def test_run_creates_metadata_json(tmp_path):
    with patch("autoresearch_researcher.cli.run_briefing", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = None
        runner.invoke(app, ["run", "--day", "2026-05-28", "--output-dir", str(tmp_path)])
        metadata_path = tmp_path / "2026-05-28" / "run_metadata.json"
        assert metadata_path.exists()
        data = json.loads(metadata_path.read_text())
        assert "started_at" in data
        assert "day" in data
        assert data["day"] == "2026-05-28"


def test_run_metadata_records_completion(tmp_path):
    with patch("autoresearch_researcher.cli.run_briefing", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = None
        runner.invoke(app, ["run", "--day", "2026-05-28", "--output-dir", str(tmp_path)])
        metadata_path = tmp_path / "2026-05-28" / "run_metadata.json"
        data = json.loads(metadata_path.read_text())
        assert "finished_at" in data
        assert "elapsed_seconds" in data


def test_run_aborts_if_dir_exists_without_rerun(tmp_path):
    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    result = runner.invoke(app, ["run", "--day", "2026-05-28", "--output-dir", str(tmp_path)])
    assert result.exit_code != 0 or "already exists" in result.output or "abort" in result.output.lower()


def test_run_rerun_flag_allows_existing_dir(tmp_path):
    with patch("autoresearch_researcher.cli.run_briefing", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = None
        day_dir = tmp_path / "2026-05-28"
        day_dir.mkdir()
        result = runner.invoke(app, ["run", "--day", "2026-05-28", "--output-dir", str(tmp_path), "--rerun"])
        assert result.exit_code == 0, result.output


def test_run_passes_max_tools_and_cost(tmp_path):
    with patch("autoresearch_researcher.cli.run_briefing", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = None
        runner.invoke(app, [
            "run", "--day", "2026-05-28",
            "--max-tools", "5",
            "--max-cost-usd", "10.0",
            "--output-dir", str(tmp_path),
        ])
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["max_tools"] == 5
        assert call_kwargs["max_cost_usd"] == 10.0


def test_run_passes_search_backend(tmp_path):
    with patch("autoresearch_researcher.cli.run_briefing", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = None
        runner.invoke(app, [
            "run", "--day", "2026-05-28",
            "--search-backend", "perplexity",
            "--output-dir", str(tmp_path),
        ])
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["search_backend"] == "perplexity"


def test_run_metadata_records_default_search_backend(tmp_path):
    with patch("autoresearch_researcher.cli.run_briefing", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = None
        runner.invoke(app, ["run", "--day", "2026-05-28", "--output-dir", str(tmp_path)])
        metadata_path = tmp_path / "2026-05-28" / "run_metadata.json"
        data = json.loads(metadata_path.read_text())
        assert data["search_backend"] == "serpapi"


def test_run_dry_run_flag(tmp_path):
    with patch("autoresearch_researcher.cli.run_briefing", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = None
        runner.invoke(app, [
            "run", "--day", "2026-05-28",
            "--dry-run",
            "--output-dir", str(tmp_path),
        ])
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["dry_run"] is True


def test_diff_subcommand_exists():
    result = runner.invoke(app, ["diff", "--help"])
    assert result.exit_code == 0
    assert "day" in result.output.lower()


def test_feedback_ingest_subcommand_exists():
    result = runner.invoke(app, ["feedback", "ingest", "--help"])
    assert result.exit_code == 0
    assert "day" in result.output.lower()

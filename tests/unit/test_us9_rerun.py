"""US9: Re-run safety and resume-from-candidates tests."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from autoresearch_researcher.cli import app

runner = CliRunner()


# ── --rerun flag backs up existing folder ─────────────────────────────────────

def test_rerun_backs_up_existing_folder(tmp_path):
    """--rerun must rename the existing day folder to a backup before starting fresh."""
    from autoresearch_researcher.orchestrator import backup_run_dir

    week_dir = tmp_path / "2026-05-28"
    week_dir.mkdir()
    (week_dir / "draft.md").write_text("existing draft")
    (week_dir / "run_metadata.json").write_text('{"day": "2026-05-28"}')

    backup_path = backup_run_dir(week_dir)

    assert not week_dir.exists() or backup_path != week_dir
    assert backup_path.exists()
    assert (backup_path / "draft.md").read_text() == "existing draft"


def test_rerun_backup_naming_is_sequential(tmp_path):
    """Multiple reruns produce sequentially numbered backups."""
    from autoresearch_researcher.orchestrator import backup_run_dir

    week_dir = tmp_path / "2026-05-28"

    for i in range(3):
        week_dir.mkdir(exist_ok=True)
        (week_dir / "run.txt").write_text(f"run {i}")
        backup = backup_run_dir(week_dir)
        assert backup.name.startswith("2026-05-28_backup")
        assert backup.exists()


def test_rerun_cli_creates_backup_and_restarts(tmp_path):
    with patch("autoresearch_researcher.cli.run_briefing", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = None

        # First run
        week_dir = tmp_path / "2026-05-28"
        week_dir.mkdir()
        (week_dir / "draft.md").write_text("old draft")

        result = runner.invoke(app, [
            "run", "--day", "2026-05-28",
            "--output-dir", str(tmp_path),
            "--rerun",
        ])

        assert result.exit_code == 0, result.output
        # A backup folder must exist
        backups = [d for d in tmp_path.iterdir() if "backup" in d.name]
        assert len(backups) >= 1


# ── resume from _candidates.jsonl ─────────────────────────────────────────────

def test_resume_skips_discovery_when_candidates_exist(tmp_path):
    """If _candidates.jsonl already exists, orchestrator skips Discovery stage."""
    from autoresearch_researcher.orchestrator import should_skip_discovery

    candidates_file = tmp_path / "_candidates.jsonl"
    candidates_file.write_text(
        '{"name": "Tool A", "url": "https://a.com", "description": "desc", "category": "ml"}\n'
    )

    assert should_skip_discovery(tmp_path) is True


def test_resume_runs_discovery_when_no_candidates(tmp_path):
    from autoresearch_researcher.orchestrator import should_skip_discovery

    # No candidates file
    assert should_skip_discovery(tmp_path) is False


def test_resume_runs_discovery_when_candidates_empty(tmp_path):
    from autoresearch_researcher.orchestrator import should_skip_discovery

    candidates_file = tmp_path / "_candidates.jsonl"
    candidates_file.write_text("")  # empty file

    assert should_skip_discovery(tmp_path) is False


def test_resume_detects_partial_profiling(tmp_path):
    """Resume should profile only un-profiled candidates."""
    from autoresearch_researcher.orchestrator import get_unprofiled_candidates
    from autoresearch_researcher.schemas.candidate import Candidate

    candidates_file = tmp_path / "_candidates.jsonl"
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()

    # 3 candidates
    for name, slug in [("Tool A", "tool-a"), ("Tool B", "tool-b"), ("Tool C", "tool-c")]:
        with candidates_file.open("a") as f:
            f.write(json.dumps({"name": name, "url": f"https://{slug}.com",
                                "description": "desc", "category": "ml"}) + "\n")

    # Only tool-a has been profiled
    (tools_dir / "tool-a.md").write_text("---\nslug: tool-a\n---\n# Tool A\n")

    unprofiled = get_unprofiled_candidates(tmp_path)
    names = [c.name for c in unprofiled]
    assert "Tool A" not in names
    assert "Tool B" in names
    assert "Tool C" in names


def test_resume_all_profiled_returns_empty(tmp_path):
    from autoresearch_researcher.orchestrator import get_unprofiled_candidates

    candidates_file = tmp_path / "_candidates.jsonl"
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()

    for name, slug in [("Tool A", "tool-a"), ("Tool B", "tool-b")]:
        with candidates_file.open("a") as f:
            f.write(json.dumps({"name": name, "url": f"https://{slug}.com",
                                "description": "desc", "category": "ml"}) + "\n")
        (tools_dir / f"{slug}.md").write_text(f"---\nslug: {slug}\n---\n")

    unprofiled = get_unprofiled_candidates(tmp_path)
    assert unprofiled == []


# ── slug derivation ───────────────────────────────────────────────────────────

def test_name_to_slug_basic():
    from autoresearch_researcher.orchestrator import name_to_slug
    assert name_to_slug("Tool Alpha") == "tool-alpha"


def test_name_to_slug_special_chars():
    from autoresearch_researcher.orchestrator import name_to_slug
    assert name_to_slug("My-Tool v2.0!") == "my-tool-v2-0"


def test_name_to_slug_no_leading_trailing_dash():
    from autoresearch_researcher.orchestrator import name_to_slug
    slug = name_to_slug("  Fancy Tool  ")
    assert not slug.startswith("-")
    assert not slug.endswith("-")

"""US9: Re-run safety (folder backup) and slug derivation tests."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from autoresearch_researcher.cli import app

runner = CliRunner()


# ── --rerun flag backs up existing folder ─────────────────────────────────────

def test_rerun_backs_up_existing_folder(tmp_path):
    """--rerun must rename the existing day folder to a backup before starting fresh."""
    from autoresearch_researcher.orchestrator import backup_run_dir

    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    (day_dir / "manifest.json").write_text("{}")
    (day_dir / "run_metadata.json").write_text('{"day": "2026-05-28"}')

    backup_path = backup_run_dir(day_dir)

    assert not day_dir.exists() or backup_path != day_dir
    assert backup_path.exists()
    assert (backup_path / "manifest.json").read_text() == "{}"


def test_rerun_backup_naming_is_sequential(tmp_path):
    """Multiple reruns produce sequentially numbered backups."""
    from autoresearch_researcher.orchestrator import backup_run_dir

    day_dir = tmp_path / "2026-05-28"

    for i in range(3):
        day_dir.mkdir(exist_ok=True)
        (day_dir / "run.txt").write_text(f"run {i}")
        backup = backup_run_dir(day_dir)
        assert backup.name.startswith("2026-05-28_backup")
        assert backup.exists()


def test_rerun_cli_creates_backup_and_restarts(tmp_path):
    with patch("autoresearch_researcher.cli.run_briefing", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = None

        day_dir = tmp_path / "2026-05-28"
        day_dir.mkdir()
        (day_dir / "manifest.json").write_text("{}")

        result = runner.invoke(app, [
            "run", "--day", "2026-05-28",
            "--output-dir", str(tmp_path),
            "--rerun",
        ])

        assert result.exit_code == 0, result.output
        backups = [d for d in tmp_path.iterdir() if "backup" in d.name]
        assert len(backups) >= 1


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

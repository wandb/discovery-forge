"""US8: Diff infrastructure and feedback template tests."""

from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent


# ── classify_diff_line ─────────────────────────────────────────────────────────

def test_classify_new_tool_section_is_add():
    from autoresearch_researcher.tools.diff import classify_diff_line
    assert classify_diff_line("+ ## NewTool") == "ADD"


def test_classify_removed_tool_section_is_remove():
    from autoresearch_researcher.tools.diff import classify_diff_line
    assert classify_diff_line("- ## OldTool") == "REMOVE"


def test_classify_factual_correction_is_fix():
    from autoresearch_researcher.tools.diff import classify_diff_line
    # A changed numeric value in a table row → FIX
    assert classify_diff_line("- | 500 stars |") == "FIX"
    assert classify_diff_line("+ | 1200 stars |") == "FIX"


def test_classify_reword_change():
    from autoresearch_researcher.tools.diff import classify_diff_line
    assert classify_diff_line("+ A better description of the tool.") == "REWORD"


def test_classify_balance_change():
    from autoresearch_researcher.tools.diff import classify_diff_line
    assert classify_diff_line("+ **Known limitation**: This tool has a significant weakness.") == "BALANCE"


def test_classify_context_line_is_none():
    from autoresearch_researcher.tools.diff import classify_diff_line
    assert classify_diff_line("  Unchanged context line.") is None


# ── generate_diff ─────────────────────────────────────────────────────────────

def test_generate_diff_detects_additions(tmp_path):
    from autoresearch_researcher.tools.diff import generate_diff

    draft = "# Title\n\nLine A.\nLine B.\n"
    final = "# Title\n\nLine A.\nLine B.\n\n## New Tool\nNew content.\n"

    result = generate_diff(draft, final)
    assert "ADD" in result or "+" in result
    assert "New Tool" in result


def test_generate_diff_detects_removals(tmp_path):
    from autoresearch_researcher.tools.diff import generate_diff

    draft = "# Title\n\n## Tool A\nSome content.\n\n## Tool B\nOther content.\n"
    final = "# Title\n\n## Tool A\nSome content.\n"

    result = generate_diff(draft, final)
    assert "Tool B" in result or "REMOVE" in result or "-" in result


def test_generate_diff_identical_files_produces_no_changes(tmp_path):
    from autoresearch_researcher.tools.diff import generate_diff

    content = "# Title\n\nNo changes here.\n"
    result = generate_diff(content, content)
    assert "no changes" in result.lower() or len(result.strip()) == 0 or "identical" in result.lower()


def test_generate_diff_returns_string():
    from autoresearch_researcher.tools.diff import generate_diff
    result = generate_diff("a\nb\n", "a\nc\n")
    assert isinstance(result, str)


# ── feedback template generation ─────────────────────────────────────────────

def test_generate_feedback_template_contains_week():
    from autoresearch_researcher.tools.diff import generate_feedback_template
    result = generate_feedback_template(week="2026-W19")
    assert "2026-W19" in result


def test_generate_feedback_template_has_all_sections():
    from autoresearch_researcher.tools.diff import generate_feedback_template
    result = generate_feedback_template(week="2026-W19")
    for section in ["ADD", "FIX", "REMOVE", "REWORD", "BALANCE"]:
        assert section in result
    assert "DiscoveryAgent" in result
    assert "ProfilerAgent" in result
    assert "WriterAgent" in result


def test_generate_feedback_template_has_score_fields():
    from autoresearch_researcher.tools.diff import generate_feedback_template
    result = generate_feedback_template(week="2026-W19")
    assert "Accuracy" in result
    assert "Completeness" in result


# ── CLI diff command integration ──────────────────────────────────────────────

def test_diff_cli_creates_diff_md(tmp_path):
    from typer.testing import CliRunner
    from autoresearch_researcher.cli import app

    week_dir = tmp_path / "2026-W19"
    week_dir.mkdir()
    (week_dir / "draft.md").write_text("# Draft\n\nOriginal content.\n")
    (week_dir / "final.md").write_text("# Final\n\nEdited content.\n\n## New Section\nAdded.\n")

    runner = CliRunner()
    result = runner.invoke(app, ["diff", "--week", "2026-W19", "--output-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert (week_dir / "diff.md").exists()


def test_diff_cli_creates_feedback_template(tmp_path):
    from typer.testing import CliRunner
    from autoresearch_researcher.cli import app

    week_dir = tmp_path / "2026-W19"
    week_dir.mkdir()
    (week_dir / "draft.md").write_text("# Draft\nContent.\n")
    (week_dir / "final.md").write_text("# Final\nChanged.\n")

    runner = CliRunner()
    runner.invoke(app, ["diff", "--week", "2026-W19", "--output-dir", str(tmp_path)])

    assert (week_dir / "feedback.md").exists()
    feedback = (week_dir / "feedback.md").read_text()
    assert "2026-W19" in feedback


def test_diff_cli_aborts_if_no_draft(tmp_path):
    from typer.testing import CliRunner
    from autoresearch_researcher.cli import app

    week_dir = tmp_path / "2026-W19"
    week_dir.mkdir()
    # No draft.md created

    runner = CliRunner()
    result = runner.invoke(app, ["diff", "--week", "2026-W19", "--output-dir", str(tmp_path)])
    assert result.exit_code != 0 or "not found" in result.output.lower()


def test_diff_cli_aborts_if_no_final(tmp_path):
    from typer.testing import CliRunner
    from autoresearch_researcher.cli import app

    week_dir = tmp_path / "2026-W19"
    week_dir.mkdir()
    (week_dir / "draft.md").write_text("# Draft\n")
    # No final.md

    runner = CliRunner()
    result = runner.invoke(app, ["diff", "--week", "2026-W19", "--output-dir", str(tmp_path)])
    assert result.exit_code != 0 or "not found" in result.output.lower()

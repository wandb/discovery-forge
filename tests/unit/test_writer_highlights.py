"""Tests for WriterAgent's weekly highlights generation."""

import json
from pathlib import Path

import pytest


def test_generate_highlights_with_new_tools(tmp_path):
    from autoresearch_researcher.agents.writer import generate_highlights

    week_dir = tmp_path / "2026-W20"
    week_dir.mkdir()
    (week_dir / "_new_candidates.jsonl").write_text(
        json.dumps({"slug": "new-tool-1", "name": "New Tool 1", "stars": 100}) + "\n" +
        json.dumps({"slug": "new-tool-2", "name": "New Tool 2", "stars": 50}) + "\n"
    )

    md = generate_highlights(week_dir, week="2026-W20")
    assert "New Tool 1" in md
    assert "New Tool 2" in md
    assert "2026-W20" in md
    assert "new" in md.lower()


def test_generate_highlights_with_updated_tools(tmp_path):
    from autoresearch_researcher.agents.writer import generate_highlights

    week_dir = tmp_path / "2026-W20"
    week_dir.mkdir()
    (week_dir / "_updated_tools.jsonl").write_text(
        json.dumps({"slug": "tool-x", "name": "Tool X", "stars": 5000}) + "\n"
    )

    md = generate_highlights(week_dir, week="2026-W20")
    assert "Tool X" in md
    assert "updated" in md.lower() or "Updated" in md


def test_generate_highlights_no_changes_uses_baseline_message(tmp_path):
    from autoresearch_researcher.agents.writer import generate_highlights

    week_dir = tmp_path / "2026-W20"
    week_dir.mkdir()
    # No _new_candidates.jsonl, no _updated_tools.jsonl

    md = generate_highlights(week_dir, week="2026-W20")
    assert any(kw in md.lower() for kw in ["no major updates", "first issue", "no new"])


def test_generate_highlights_returns_markdown_string(tmp_path):
    from autoresearch_researcher.agents.writer import generate_highlights

    week_dir = tmp_path / "2026-W20"
    week_dir.mkdir()
    md = generate_highlights(week_dir, week="2026-W20")
    assert isinstance(md, str)
    assert len(md) > 0


def test_generate_highlights_includes_both_new_and_updated(tmp_path):
    from autoresearch_researcher.agents.writer import generate_highlights

    week_dir = tmp_path / "2026-W20"
    week_dir.mkdir()
    (week_dir / "_new_candidates.jsonl").write_text(
        json.dumps({"slug": "new-1", "name": "Newcomer", "stars": 50}) + "\n"
    )
    (week_dir / "_updated_tools.jsonl").write_text(
        json.dumps({"slug": "old-1", "name": "Veteran", "stars": 9000}) + "\n"
    )

    md = generate_highlights(week_dir, week="2026-W20")
    assert "Newcomer" in md
    assert "Veteran" in md

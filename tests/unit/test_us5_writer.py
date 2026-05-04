"""US5: WriterAgent tests."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent.parent

# ── fixture helpers ───────────────────────────────────────────────────────────

def make_tool_profile_md(slug: str, name: str, domains: list[str], autonomy: str) -> str:
    """Create a minimal tool profile .md for test fixtures."""
    import yaml
    front = {
        "slug": slug,
        "name": name,
        "license": "MIT",
        "domains": domains,
        "autonomy_level": autonomy,
        "autonomy_rationale": "Test rationale",
        "interface": "CLI",
        "resource_requirements": "Single GPU",
        "last_commit": "2025-01-01",
        "stars": 500,
        "open_issues": 10,
        "pricing_note": "Free",
        "github_url": f"https://github.com/example/{slug}",
        "paper_url": None,
        "project_url": None,
        "source_ids": [1],
    }
    return "---\n" + yaml.dump(front, allow_unicode=True) + "---\n\n# " + name + "\n\nTest body.\n"


def write_fixture_profiles(tools_dir: Path, count: int = 3) -> list[str]:
    tools_dir.mkdir(parents=True, exist_ok=True)
    slugs = []
    for i in range(count):
        slug = f"test-tool-{i}"
        md = make_tool_profile_md(slug, f"Test Tool {i}", ["ml"], "Scientist")
        (tools_dir / f"{slug}.md").write_text(md)
        slugs.append(slug)
    return slugs


# ── tests ─────────────────────────────────────────────────────────────────────

def test_writer_instructions_exists():
    instr = ROOT / "src" / "autoresearch_researcher" / "instructions" / "writer.md"
    assert instr.exists()


def test_writer_instructions_no_hardcoded_tool_names():
    instr = ROOT / "src" / "autoresearch_researcher" / "instructions" / "writer.md"
    content = instr.read_text().lower()
    forbidden = ["ai scientist", "agent laboratory", "gpt-researcher", "perplexity"]
    for name in forbidden:
        assert name not in content, f"Hardcoded tool name in writer instructions: '{name}'"


def test_writer_instructions_forbids_marketing_language():
    instr = ROOT / "src" / "autoresearch_researcher" / "instructions" / "writer.md"
    content = instr.read_text().lower()
    assert any(kw in content for kw in ["marketing", "objective", "neutral", "informational"])


def test_load_tool_profiles_from_dir(tmp_path):
    from autoresearch_researcher.agents.writer import load_tool_profiles_from_dir
    tools_dir = tmp_path / "tools"
    write_fixture_profiles(tools_dir, 3)

    profiles = load_tool_profiles_from_dir(tools_dir)
    assert len(profiles) == 3
    slugs = {p["slug"] for p in profiles}
    assert slugs == {"test-tool-0", "test-tool-1", "test-tool-2"}


def test_load_tool_profiles_skips_candidates_file(tmp_path):
    from autoresearch_researcher.agents.writer import load_tool_profiles_from_dir
    tools_dir = tmp_path / "tools"
    write_fixture_profiles(tools_dir, 2)
    (tools_dir / "_candidates.jsonl").write_text('{"name": "x"}\n')

    profiles = load_tool_profiles_from_dir(tools_dir)
    assert len(profiles) == 2


def test_generate_comparison_table_has_required_columns(tmp_path):
    from autoresearch_researcher.agents.writer import generate_comparison_table
    tools_dir = tmp_path / "tools"
    write_fixture_profiles(tools_dir, 2)
    profiles = [
        {
            "slug": "tool-a",
            "name": "Tool A",
            "license": "MIT",
            "domains": ["ml"],
            "autonomy_level": "Scientist",
            "interface": "CLI",
            "resource_requirements": "Single GPU",
            "last_commit": "2025-01-01",
            "stars": 200,
            "pricing_note": "Free",
            "key_limitations": ["Needs GPU"],
        },
        {
            "slug": "tool-b",
            "name": "Tool B",
            "license": "Apache 2.0",
            "domains": ["chemistry"],
            "autonomy_level": "Analyst",
            "interface": "Python lib",
            "resource_requirements": "Lab equipment",
            "last_commit": None,
            "stars": None,
            "pricing_note": "unknown",
            "key_limitations": [],
        },
    ]
    table = generate_comparison_table(profiles)
    assert "| " in table  # markdown table
    for col in ["Tool", "License", "Domain", "Autonomy", "Interface", "Resource", "Stars", "Price"]:
        assert col.lower() in table.lower(), f"Missing column: {col}"
    # unknown must appear for missing data
    assert "unknown" in table.lower()


def test_generate_comparison_table_unknown_for_none_values(tmp_path):
    from autoresearch_researcher.agents.writer import generate_comparison_table
    profiles = [
        {
            "slug": "tool-x",
            "name": "Tool X",
            "license": "unknown",
            "domains": ["ml"],
            "autonomy_level": "Tool",
            "interface": "unknown",
            "resource_requirements": "unknown",
            "last_commit": None,
            "stars": None,
            "pricing_note": "unknown",
            "key_limitations": [],
        }
    ]
    table = generate_comparison_table(profiles)
    assert "unknown" in table.lower()


def test_build_writer_agent_returns_agent():
    from autoresearch_researcher.agents.writer import build_writer_agent
    agent = build_writer_agent(output_dir=Path("/tmp"), week="2026-W99")
    assert agent is not None
    assert agent.name == "WriterAgent"


def test_writer_agent_no_hardcoded_tool_names():
    from autoresearch_researcher.agents.writer import build_writer_agent
    agent = build_writer_agent(output_dir=Path("/tmp"), week="2026-W99")
    instructions_lower = agent.instructions.lower()
    forbidden = ["ai scientist", "agent laboratory", "gpt-researcher", "perplexity"]
    for name in forbidden:
        assert name not in instructions_lower


def test_save_draft_tool_writes_file(tmp_path):
    from autoresearch_researcher.tools.persistence import save_draft
    content = "# Draft\n\nTest content.\n"
    save_draft(content, tmp_path)
    assert (tmp_path / "draft.md").exists()
    assert (tmp_path / "draft.md").read_text() == content


def test_save_comparison_table_writes_file(tmp_path):
    from autoresearch_researcher.tools.persistence import save_comparison_table
    content = "| Tool | License |\n|------|---------|"
    save_comparison_table(content, tmp_path)
    assert (tmp_path / "comparison_table.md").exists()

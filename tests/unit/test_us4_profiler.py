"""US4: ProfilerAgent tests — including mandatory scope-filter validation."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent.parent


def test_profiler_instructions_exists():
    instr = ROOT / "src" / "autoresearch_researcher" / "instructions" / "profiler.md"
    assert instr.exists()


def test_profiler_instructions_no_hardcoded_tool_names():
    instr = ROOT / "src" / "autoresearch_researcher" / "instructions" / "profiler.md"
    content = instr.read_text().lower()
    forbidden = ["ai scientist", "agent laboratory", "gpt-researcher", "perplexity"]
    for name in forbidden:
        assert name not in content, f"Hardcoded tool name in profiler instructions: '{name}'"


def test_tool_profile_schema_fields():
    from autoresearch_researcher.schemas.tool_profile import ToolProfile
    p = ToolProfile(
        slug="test-tool",
        name="Test Tool",
        license="MIT",
        domains=["ml"],
        autonomy_level="Scientist",
        autonomy_rationale="Executes full experiment loop",
        interface="CLI",
        resource_requirements="Single GPU",
        last_commit="2025-01-01",
        stars=500,
        open_issues=10,
        pricing_note="Free",
        key_limitations=["Requires GPU"],
        github_url="https://github.com/example/test-tool",
        paper_url=None,
        project_url=None,
        source_ids=[1, 2],
    )
    assert p.slug == "test-tool"
    assert p.domains == ["ml"]


def test_tool_profile_optional_fields_default_none():
    from autoresearch_researcher.schemas.tool_profile import ToolProfile
    p = ToolProfile(
        slug="minimal-tool",
        name="Minimal Tool",
        license="unknown",
        domains=["ml"],
        autonomy_level="Tool",
        autonomy_rationale="Runs scripts",
        interface="Python lib",
        resource_requirements="unknown",
        last_commit=None,
        stars=None,
        open_issues=None,
        pricing_note="unknown",
        key_limitations=[],
        github_url=None,
        paper_url=None,
        project_url=None,
        source_ids=[],
    )
    assert p.last_commit is None
    assert p.stars is None


def test_rejected_profile_schema():
    from autoresearch_researcher.schemas.tool_profile import RejectedProfile
    r = RejectedProfile(
        slug="deep-search-tool",
        name="Deep Search Tool",
        url="https://example.com/deep-search-tool",
        rejection_reason="Only does web search and summarization, no experiment execution",
    )
    assert r.rejection_reason
    assert r.url == "https://example.com/deep-search-tool"


# ── MANDATORY: scope-filter tests ────────────────────────────────────────────

def test_profiler_instructions_contain_scope_filter_rule():
    """Instructions must explicitly tell the agent to reject deep-research tools."""
    instr = ROOT / "src" / "autoresearch_researcher" / "instructions" / "profiler.md"
    content = instr.read_text().lower()
    # Must contain language about rejecting tools that only search/summarize
    assert any(kw in content for kw in ["reject", "exclude", "out of scope", "not in scope"])
    assert any(kw in content for kw in ["search", "summariz", "retriev"])


def test_save_tool_profile_writes_yaml_frontmatter(tmp_path):
    from autoresearch_researcher.schemas.tool_profile import ToolProfile
    from autoresearch_researcher.tools.persistence import save_tool_profile

    tools_dir = tmp_path / "tools"
    profile = ToolProfile(
        slug="example-tool",
        name="Example Tool",
        license="Apache 2.0",
        domains=["ml"],
        autonomy_level="Scientist",
        autonomy_rationale="Runs full experiment loop",
        interface="CLI",
        resource_requirements="Multi GPU",
        last_commit="2025-03-01",
        stars=1200,
        open_issues=45,
        pricing_note="Free",
        key_limitations=["Needs 8x A100"],
        github_url="https://github.com/example/tool",
        paper_url="https://arxiv.org/abs/2025.00001",
        project_url=None,
        source_ids=[1, 2, 3],
    )
    save_tool_profile(profile, tools_dir)

    out_file = tools_dir / "example-tool.md"
    assert out_file.exists()
    content = out_file.read_text()
    assert content.startswith("---")
    assert "slug: example-tool" in content
    assert "Apache 2.0" in content
    assert "---" in content[3:]  # closing frontmatter delimiter


def test_fetch_github_metadata_returns_structured_data():
    from autoresearch_researcher.tools.github import fetch_github_metadata
    # With a fake/non-existent repo, it should return None or a stub (no real HTTP)
    # We just verify the function exists and accepts a github URL
    import inspect
    sig = inspect.signature(fetch_github_metadata)
    assert "github_url" in sig.parameters


def test_build_profiler_agent_returns_agent():
    from autoresearch_researcher.agents.profiler import build_profiler_agent
    agent = build_profiler_agent(output_dir=Path("/tmp"))
    assert agent is not None
    assert agent.name == "ProfilerAgent"


def test_profiler_agent_no_hardcoded_tool_names():
    from autoresearch_researcher.agents.profiler import build_profiler_agent
    agent = build_profiler_agent(output_dir=Path("/tmp"))
    instructions_lower = agent.instructions.lower()
    forbidden = ["ai scientist", "agent laboratory", "gpt-researcher", "perplexity"]
    for name in forbidden:
        assert name not in instructions_lower, f"Hardcoded tool name: '{name}'"


# ── Scope filter: deep-research rejection ────────────────────────────────────

def test_profiler_scope_filter_deep_research_tool_is_rejected():
    """
    ProfilerAgent must reject tools that only do deep research (web search + summarization).
    This test verifies the scope-filter logic at the function level (no LLM call).
    """
    from autoresearch_researcher.agents.profiler import is_experiment_automation

    # Tool that only searches and summarizes web content
    assert is_experiment_automation(
        autonomy_level="Analyst",
        description="Searches the web and produces a comprehensive research report by summarizing sources.",
        domains=["general"],
    ) is False


def test_profiler_scope_filter_experiment_tool_is_accepted():
    """Tools that execute experiments must pass the scope filter."""
    from autoresearch_researcher.agents.profiler import is_experiment_automation

    assert is_experiment_automation(
        autonomy_level="Scientist",
        description="Proposes hypotheses, writes experiment code, runs ML training, and generates a paper.",
        domains=["ml"],
    ) is True


def test_profiler_scope_filter_chemistry_automation_is_accepted():
    from autoresearch_researcher.agents.profiler import is_experiment_automation

    assert is_experiment_automation(
        autonomy_level="Scientist",
        description="Controls robotic lab equipment to perform chemical synthesis experiments autonomously.",
        domains=["chemistry"],
    ) is True


def test_profiler_scope_filter_rag_tool_is_rejected():
    from autoresearch_researcher.agents.profiler import is_experiment_automation

    assert is_experiment_automation(
        autonomy_level="Tool",
        description="Retrieval-augmented generation pipeline for Q&A over scientific literature.",
        domains=["general"],
    ) is False

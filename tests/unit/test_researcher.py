"""ResearcherAgent: the single discover+profile agent and its scope filter."""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
INSTR = ROOT / "src" / "discovery_forge" / "instructions" / "researcher.md"


# ── instructions ──────────────────────────────────────────────────────────────

def test_researcher_instructions_exists():
    assert INSTR.exists(), "instructions/researcher.md must exist"


def test_researcher_instructions_no_hardcoded_tool_names():
    content = INSTR.read_text().lower()
    forbidden = ["ai scientist", "agent laboratory", "gpt-researcher", "perplexity"]
    for name in forbidden:
        assert name not in content, f"Hardcoded tool name in researcher instructions: '{name}'"


def test_researcher_instructions_contain_scope_filter_rule():
    content = INSTR.read_text().lower()
    assert any(kw in content for kw in ["reject", "exclude", "out of scope", "not in scope"])
    assert any(kw in content for kw in ["search", "summariz", "retriev"])


def test_researcher_instructions_do_not_hardcode_search_years():
    content = INSTR.read_text()
    assert "2024" not in content
    assert "2025" not in content
    assert "2026" not in content


def test_load_instructions_returns_string():
    from discovery_forge.agents.researcher import load_instructions
    text = load_instructions("researcher")
    assert isinstance(text, str)
    assert len(text) > 50


# ── agent construction ─────────────────────────────────────────────────────────

def test_build_researcher_agent_returns_agent():
    from discovery_forge.agents.researcher import build_researcher_agent
    agent = build_researcher_agent(output_dir=Path("/tmp"))
    assert agent is not None
    assert agent.name == "ResearcherAgent"


def test_researcher_agent_has_expected_tools():
    from discovery_forge.agents.researcher import build_researcher_agent
    agent = build_researcher_agent(output_dir=Path("/tmp"))
    tool_names = {t.name for t in agent.tools}
    for expected in {
        "search_web",
        "is_known_tool",
        "fetch_github_metadata_tool",
        "save_tool_profile_tool",
        "save_rejected_profile_tool",
        "report_no_new_tool",
    }:
        assert expected in tool_names, f"Missing tool: {expected}"


def test_serper_backend_uses_function_search_tool():
    from agents import WebSearchTool
    from discovery_forge.agents.researcher import build_researcher_agent

    agent = build_researcher_agent(output_dir=Path("/tmp"), search_backend="serper")
    assert not any(isinstance(t, WebSearchTool) for t in agent.tools)
    assert "search_web" in {getattr(t, "name", None) for t in agent.tools}


def test_build_researcher_agent_accepts_recency():
    from discovery_forge.agents.researcher import build_researcher_agent

    agent = build_researcher_agent(output_dir=Path("/tmp"), search_backend="serper", recency="month")
    assert agent is not None
    assert "search_web" in {getattr(t, "name", None) for t in agent.tools}


def test_openai_backend_uses_hosted_web_search_tool():
    from agents import WebSearchTool
    from discovery_forge.agents.researcher import build_researcher_agent

    agent = build_researcher_agent(output_dir=Path("/tmp"), search_backend="openai")
    assert any(isinstance(t, WebSearchTool) for t in agent.tools)
    # The custom function tool is replaced by the hosted tool for this backend.
    assert "search_web" not in {getattr(t, "name", None) for t in agent.tools}


def test_researcher_agent_no_hardcoded_tool_names():
    from discovery_forge.agents.researcher import build_researcher_agent
    agent = build_researcher_agent(output_dir=Path("/tmp"))
    instructions_lower = agent.instructions.lower()
    forbidden = ["ai scientist", "agent laboratory", "gpt-researcher", "perplexity"]
    for name in forbidden:
        assert name not in instructions_lower, f"Hardcoded tool name: '{name}'"


def test_researcher_agent_accepts_registry_param(tmp_path):
    from discovery_forge.agents.researcher import build_researcher_agent
    from discovery_forge.tools.registry import ToolRegistry

    registry = ToolRegistry.load(tmp_path / "_registry")
    agent = build_researcher_agent(output_dir=tmp_path, registry=registry, day="2026-05-28")
    assert agent is not None
    assert "is_known_tool" in {t.name for t in agent.tools}


# ── scope filter (no LLM call) ──────────────────────────────────────────────────

def test_scope_filter_deep_research_tool_is_rejected():
    from discovery_forge.agents.researcher import is_experiment_automation
    assert is_experiment_automation(
        autonomy_level="Analyst",
        description="Searches the web and produces a comprehensive research report by summarizing sources.",
        domains=["general"],
    ) is False


def test_scope_filter_experiment_tool_is_accepted():
    from discovery_forge.agents.researcher import is_experiment_automation
    assert is_experiment_automation(
        autonomy_level="Scientist",
        description="Proposes hypotheses, writes experiment code, runs ML training, and generates a paper.",
        domains=["ml"],
    ) is True


def test_scope_filter_chemistry_automation_is_accepted():
    from discovery_forge.agents.researcher import is_experiment_automation
    assert is_experiment_automation(
        autonomy_level="Scientist",
        description="Controls robotic lab equipment to perform chemical synthesis experiments autonomously.",
        domains=["chemistry"],
    ) is True


def test_scope_filter_rag_tool_is_rejected():
    from discovery_forge.agents.researcher import is_experiment_automation
    assert is_experiment_automation(
        autonomy_level="Tool",
        description="Retrieval-augmented generation pipeline for Q&A over scientific literature.",
        domains=["general"],
    ) is False


# ── schemas + persistence ───────────────────────────────────────────────────────

def test_tool_profile_schema_fields():
    from discovery_forge.schemas.tool_profile import ToolProfile
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
        page_title="example/test-tool",
        page_description="Source-provided repo description.",
        page_image_url="https://example.com/og.png",
        page_published_at="2024-12-31T00:00:00Z",
        source_updated_at="2025-01-02T00:00:00Z",
        github_url="https://github.com/example/test-tool",
        paper_url=None,
        project_url=None,
        source_ids=[1, 2],
    )
    assert p.slug == "test-tool"
    assert p.domains == ["ml"]
    assert p.page_published_at == "2024-12-31T00:00:00Z"


def test_rejected_profile_schema():
    from discovery_forge.schemas.tool_profile import RejectedProfile
    r = RejectedProfile(
        slug="deep-search-tool",
        name="Deep Search Tool",
        url="https://example.com/deep-search-tool",
        verdict_reason="Only does web search and summarization, no experiment execution",
    )
    assert r.verdict_reason
    assert r.url == "https://example.com/deep-search-tool"


def test_save_tool_profile_writes_yaml_frontmatter(tmp_path):
    from discovery_forge.schemas.tool_profile import ToolProfile
    from discovery_forge.tools.persistence import save_tool_profile

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
        page_title="example/tool",
        page_description="GitHub repository description.",
        page_image_url=None,
        page_published_at="2025-01-15T00:00:00Z",
        source_updated_at="2025-03-01T00:00:00Z",
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
    assert "page_title: example/tool" in content
    assert "page_published_at: '2025-01-15T00:00:00Z'" in content


def test_fetch_github_metadata_signature():
    from discovery_forge.tools.github import fetch_github_metadata
    import inspect
    sig = inspect.signature(fetch_github_metadata)
    assert "github_url" in sig.parameters


def test_fetch_github_metadata_includes_source_page_fields():
    from unittest.mock import MagicMock, patch

    from discovery_forge.tools.github import fetch_github_metadata

    repo_response = MagicMock()
    repo_response.json.return_value = {
        "name": "tool-a",
        "full_name": "example/tool-a",
        "description": "Source-provided repo description.",
        "created_at": "2025-01-15T00:00:00Z",
        "pushed_at": "2025-03-02T00:00:00Z",
        "stargazers_count": 123,
        "open_issues_count": 4,
        "license": {"spdx_id": "MIT"},
        "default_branch": "main",
        "open_graph_image_url": "https://example.com/og.png",
    }
    repo_response.raise_for_status = MagicMock()

    commit_response = MagicMock()
    commit_response.status_code = 200
    commit_response.json.return_value = {
        "commit": {"committer": {"date": "2025-03-01T00:00:00Z"}}
    }

    with patch("discovery_forge.tools.github.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_client.get.side_effect = [repo_response, commit_response]

        metadata = fetch_github_metadata("https://github.com/example/tool-a")

    assert metadata == {
        "stars": 123,
        "open_issues": 4,
        "last_commit": "2025-03-01T00:00:00Z",
        "license": "MIT",
        "page_title": "tool-a",
        "page_description": "Source-provided repo description.",
        "page_image_url": "https://example.com/og.png",
        "page_published_at": "2025-01-15T00:00:00Z",
        "source_updated_at": "2025-03-01T00:00:00Z",
    }


# ── profile loading helper ──────────────────────────────────────────────────────

def _write_profile(tools_dir: Path, slug: str) -> None:
    import yaml
    front = {
        "slug": slug,
        "name": slug.replace("-", " ").title(),
        "license": "MIT",
        "domains": ["ml"],
        "autonomy_level": "Scientist",
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
    tools_dir.mkdir(parents=True, exist_ok=True)
    (tools_dir / f"{slug}.md").write_text(
        "---\n" + yaml.dump(front, allow_unicode=True) + "---\n\n# Body\n"
    )


def test_load_tool_profiles_from_dir(tmp_path):
    from discovery_forge.tools.profiles import load_tool_profiles_from_dir
    tools_dir = tmp_path / "tools"
    for i in range(3):
        _write_profile(tools_dir, f"test-tool-{i}")

    profiles = load_tool_profiles_from_dir(tools_dir)
    assert {p["slug"] for p in profiles} == {"test-tool-0", "test-tool-1", "test-tool-2"}


def test_load_tool_profiles_skips_underscore_files(tmp_path):
    from discovery_forge.tools.profiles import load_tool_profiles_from_dir
    tools_dir = tmp_path / "tools"
    _write_profile(tools_dir, "test-tool-0")
    (tools_dir / "_candidates.jsonl").write_text('{"name": "x"}\n')

    profiles = load_tool_profiles_from_dir(tools_dir)
    assert len(profiles) == 1

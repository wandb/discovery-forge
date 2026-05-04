"""US3: DiscoveryAgent tests."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent.parent


def test_discovery_instructions_file_exists():
    instr = ROOT / "src" / "autoresearch_researcher" / "instructions" / "discovery.md"
    assert instr.exists(), "instructions/discovery.md must exist"


def test_discovery_instructions_has_no_hardcoded_tool_names():
    """Instructions must NOT contain specific tool names as seeds."""
    instr = ROOT / "src" / "autoresearch_researcher" / "instructions" / "discovery.md"
    content = instr.read_text().lower()
    # These are example tool names from the PRD that must NOT be hardcoded
    forbidden = ["ai scientist", "agent laboratory", "gpt-researcher", "perplexity", "openai deep research"]
    for name in forbidden:
        assert name not in content, f"Hardcoded tool name found in instructions: '{name}'"


def test_load_instructions_returns_string():
    from autoresearch_researcher.agents.discovery import load_instructions
    text = load_instructions("discovery")
    assert isinstance(text, str)
    assert len(text) > 50


def test_candidate_schema_fields():
    from autoresearch_researcher.schemas.candidate import Candidate
    c = Candidate(
        name="TestTool",
        url="https://example.com",
        description="A test tool",
        category="ml-experiment-automation",
    )
    assert c.name == "TestTool"
    assert c.url == "https://example.com"
    assert c.category == "ml-experiment-automation"


def test_rejected_candidate_has_reason():
    from autoresearch_researcher.schemas.candidate import RejectedCandidate
    r = RejectedCandidate(
        name="SomeDeepResearchTool",
        url="https://example.com",
        description="Web search and summarize",
        category="deep-research",
        rejection_reason="Only does web search and summarization, no experiment execution",
    )
    assert r.rejection_reason
    assert r.name == "SomeDeepResearchTool"


def test_save_candidate_tool_writes_jsonl(tmp_path):
    from autoresearch_researcher.tools.persistence import save_candidate
    from autoresearch_researcher.schemas.candidate import Candidate

    output_file = tmp_path / "_candidates.jsonl"
    c = Candidate(name="ToolX", url="https://x.com", description="Runs experiments", category="ml")
    save_candidate(c, output_file)

    assert output_file.exists()
    lines = output_file.read_text().strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["name"] == "ToolX"


def test_save_candidate_appends(tmp_path):
    from autoresearch_researcher.tools.persistence import save_candidate
    from autoresearch_researcher.schemas.candidate import Candidate

    output_file = tmp_path / "_candidates.jsonl"
    for i in range(3):
        c = Candidate(name=f"Tool{i}", url=f"https://x{i}.com", description="desc", category="ml")
        save_candidate(c, output_file)

    lines = output_file.read_text().strip().splitlines()
    assert len(lines) == 3


def test_build_discovery_agent_returns_agent():
    from autoresearch_researcher.agents.discovery import build_discovery_agent
    agent = build_discovery_agent(output_dir=Path("/tmp"))
    assert agent is not None
    assert agent.name == "DiscoveryAgent"


def test_discovery_agent_has_no_hardcoded_tool_names():
    """Agent instructions must NOT contain specific tool name seeds."""
    from autoresearch_researcher.agents.discovery import build_discovery_agent
    agent = build_discovery_agent(output_dir=Path("/tmp"))
    instructions_lower = agent.instructions.lower()
    forbidden = ["ai scientist", "agent laboratory", "gpt-researcher", "perplexity"]
    for name in forbidden:
        assert name not in instructions_lower, f"Hardcoded tool name in agent instructions: '{name}'"

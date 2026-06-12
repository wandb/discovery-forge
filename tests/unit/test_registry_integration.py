"""Integration of the global registry with the single ResearcherAgent."""



def test_researcher_agent_accepts_registry_param(tmp_path):
    from discovery_forge.agents.researcher import build_researcher_agent
    from discovery_forge.tools.registry import ToolRegistry

    registry = ToolRegistry.load(tmp_path / "_registry")
    agent = build_researcher_agent(output_dir=tmp_path, registry=registry, day="2026-05-19")
    assert agent is not None
    assert agent.name == "ResearcherAgent"


def test_researcher_agent_has_is_known_tool(tmp_path):
    from discovery_forge.agents.researcher import build_researcher_agent
    from discovery_forge.tools.registry import ToolRegistry

    registry = ToolRegistry.load(tmp_path / "_registry")
    agent = build_researcher_agent(output_dir=tmp_path, registry=registry, day="2026-05-19")
    tool_names = [t.name for t in agent.tools]
    assert "is_known_tool" in tool_names


def test_researcher_agent_works_without_registry(tmp_path):
    """Backwards compatibility: registry param is optional."""
    from discovery_forge.agents.researcher import build_researcher_agent

    agent = build_researcher_agent(output_dir=tmp_path)
    assert agent is not None


def test_registry_starts_empty(tmp_path):
    from discovery_forge.tools.registry import ToolRegistry

    registry = ToolRegistry.load(tmp_path / "_registry")
    assert len(registry.get_all_entries()) == 0

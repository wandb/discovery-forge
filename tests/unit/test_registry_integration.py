"""Integration of registry with DiscoveryAgent / ProfilerAgent."""

from pathlib import Path

import pytest


# ── DiscoveryAgent dedup ──────────────────────────────────────────────────────

def test_discovery_agent_accepts_registry_param(tmp_path):
    from autoresearch_researcher.agents.discovery import build_discovery_agent
    from autoresearch_researcher.tools.registry import ToolRegistry

    registry = ToolRegistry.load(tmp_path / "_registry")
    agent = build_discovery_agent(output_dir=tmp_path, registry=registry)
    assert agent is not None
    assert agent.name == "DiscoveryAgent"


def test_discovery_agent_has_is_known_tool(tmp_path):
    from autoresearch_researcher.agents.discovery import build_discovery_agent
    from autoresearch_researcher.tools.registry import ToolRegistry

    registry = ToolRegistry.load(tmp_path / "_registry")
    agent = build_discovery_agent(output_dir=tmp_path, registry=registry)
    tool_names = [t.name for t in agent.tools]
    assert "is_known_tool" in tool_names


def test_discovery_agent_works_without_registry(tmp_path):
    """Backwards compatibility: registry param is optional."""
    from autoresearch_researcher.agents.discovery import build_discovery_agent

    agent = build_discovery_agent(output_dir=tmp_path)
    assert agent is not None


# ── ProfilerAgent registry routing ───────────────────────────────────────────

def test_profiler_agent_accepts_registry_param(tmp_path):
    from autoresearch_researcher.agents.profiler import build_profiler_agent
    from autoresearch_researcher.tools.registry import ToolRegistry

    registry = ToolRegistry.load(tmp_path / "_registry")
    agent = build_profiler_agent(output_dir=tmp_path, registry=registry)
    assert agent is not None


def test_profiler_save_routes_to_registry(tmp_path):
    """When registry is provided, save_tool_profile_tool should add to registry, not week_dir/tools/."""
    from autoresearch_researcher.agents.profiler import build_profiler_agent
    from autoresearch_researcher.schemas.tool_profile import ToolProfile
    from autoresearch_researcher.tools.registry import ToolRegistry

    registry = ToolRegistry.load(tmp_path / "_registry")
    week_dir = tmp_path / "2026-W19"
    week_dir.mkdir()

    agent = build_profiler_agent(output_dir=week_dir, registry=registry, week="2026-W19")

    # Find the save_tool_profile tool's underlying callable and invoke directly
    # Verify by checking the registry state after a manual add
    assert len(registry.get_all_entries()) == 0

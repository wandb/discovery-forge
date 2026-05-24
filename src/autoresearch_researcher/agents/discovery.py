"""DiscoveryAgent: finds experiment-automation tool candidates via Perplexity search."""

import json
import os
from pathlib import Path

from agents import Agent, function_tool

from autoresearch_researcher.schemas.candidate import Candidate, RejectedCandidate
from autoresearch_researcher.tools.persistence import save_candidate, save_rejected_candidate
from autoresearch_researcher.tools.search import DEFAULT_SEARCH_BACKEND, SearchBackend, search_web_query

INSTRUCTIONS_DIR = Path(__file__).parent.parent / "instructions"


def load_instructions(agent_name: str) -> str:
    """Load agent instructions from instructions/{agent_name}.md."""
    path = INSTRUCTIONS_DIR / f"{agent_name}.md"
    return path.read_text()


def build_discovery_agent(
    output_dir: Path,
    max_tools: int = 12,
    registry=None,
    search_backend: SearchBackend = DEFAULT_SEARCH_BACKEND,
    instructions_override: str | None = None,
) -> Agent:
    """Build and return the DiscoveryAgent.

    If `registry` is provided, the agent gets an `is_known_tool` tool that
    returns whether a URL is already in the global registry, so it can skip
    re-discovery and save Perplexity calls.
    """
    candidates_file = output_dir / "_candidates.jsonl"
    rejected_file = output_dir / "_rejected.jsonl"

    @function_tool
    def save_candidate_tool(
        name: str,
        url: str,
        description: str,
        category: str,
    ) -> str:
        """Save a discovered tool candidate that is IN scope."""
        candidate = Candidate(name=name, url=url, description=description, category=category)
        save_candidate(candidate, candidates_file)
        return f"Saved candidate: {name}"

    @function_tool
    def save_rejected_candidate_tool(
        name: str,
        url: str,
        description: str,
        category: str,
        rejection_reason: str,
    ) -> str:
        """Save a tool candidate that is OUT of scope, with rejection reason."""
        rejected = RejectedCandidate(
            name=name,
            url=url,
            description=description,
            category=category,
            rejection_reason=rejection_reason,
        )
        save_rejected_candidate(rejected, rejected_file)
        return f"Rejected: {name} — {rejection_reason}"

    @function_tool
    def search_web(query: str) -> str:
        """Search the web using the configured backend. Returns source URLs/snippets."""
        return search_web_query(query, backend=search_backend)

    @function_tool
    def is_known_tool(url: str) -> str:
        """Check if a tool URL is already in the global registry. Returns 'known' or 'new'."""
        if registry is not None and registry.contains(url):
            return f"known: {url} is already in the global registry — skip it."
        return f"new: {url} is not in the registry yet — proceed to save_candidate."

    instructions = instructions_override or load_instructions("discovery").replace("{max_tools}", str(max_tools))

    tools = [search_web, save_candidate_tool, save_rejected_candidate_tool]
    if registry is not None:
        tools.insert(1, is_known_tool)
    else:
        # Always expose the tool name (returns "new" stub) so callers can rely on it.
        tools.insert(1, is_known_tool)

    return Agent(
        name="DiscoveryAgent",
        instructions=instructions,
        tools=tools,
        model="gpt-5.4-mini",
    )

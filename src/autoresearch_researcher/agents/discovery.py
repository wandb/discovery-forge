"""DiscoveryAgent: finds experiment-automation tool candidates via web search."""

import json
from pathlib import Path

from agents import Agent, WebSearchTool, function_tool

from autoresearch_researcher.schemas.candidate import Candidate, RejectedCandidate
from autoresearch_researcher.tools.persistence import save_candidate, save_rejected_candidate

INSTRUCTIONS_DIR = Path(__file__).parent.parent / "instructions"


def load_instructions(agent_name: str) -> str:
    """Load agent instructions from instructions/{agent_name}.md."""
    path = INSTRUCTIONS_DIR / f"{agent_name}.md"
    return path.read_text()


def build_discovery_agent(output_dir: Path, max_tools: int = 12) -> Agent:
    """Build and return the DiscoveryAgent."""
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

    instructions = load_instructions("discovery").replace("{max_tools}", str(max_tools))

    return Agent(
        name="DiscoveryAgent",
        instructions=instructions,
        tools=[
            WebSearchTool(),
            save_candidate_tool,
            save_rejected_candidate_tool,
        ],
        model="gpt-4o",
    )

"""ResearcherAgent: the single agent that discovers AND profiles one tool per run.

Each invocation is asked to find ONE candidate that is not yet covered (an
exclusion list is passed at runtime), verify it, and either save a canonical
profile, reject it, or report that no new finding was found for this attempt.
"""

from pathlib import Path
from typing import Any

from agents import Agent

from discovery_forge.agents.researcher_tools import ResearcherToolContext, build_researcher_tools
from discovery_forge.tools.search import (
    DEFAULT_SEARCH_BACKEND,
    RecencyWindow,
    SearchBackend,
)

INSTRUCTIONS_DIR = Path(__file__).parent

# Keywords that indicate a tool only searches/summarizes (not experiment automation)
_DEEP_RESEARCH_KEYWORDS = [
    "search and summariz",
    "web search",
    "summariz",
    "retriev",
    "retrieval-augmented",
    "rag",
    "literature review",
    "web document",
    "search the web",
    "synthesize sources",
    "web sources",
]

_EXPERIMENT_KEYWORDS = [
    "experiment",
    "execut",
    "run",
    "train",
    "simulation",
    "lab",
    "robotic",
    "hypothesis",
    "synthesis",
    "automat",
    "code and run",
    "runs code",
]


def load_instructions(agent_name: str) -> str:
    """Load agent instructions from agents/{agent_name}.md."""
    path = INSTRUCTIONS_DIR / f"{agent_name}.md"
    return path.read_text()


def is_experiment_automation(
    autonomy_level: str,
    description: str,
    domains: list[str],
) -> bool:
    """
    Heuristic scope filter: returns True if tool appears to be experiment automation.
    Used for unit-testable pre-flight check before LLM profiling.
    """
    desc_lower = description.lower()

    deep_count = sum(1 for kw in _DEEP_RESEARCH_KEYWORDS if kw in desc_lower)
    exp_count = sum(1 for kw in _EXPERIMENT_KEYWORDS if kw in desc_lower)

    # A tool dominated by retrieval/summarization keywords with no experiment keywords is OUT
    if deep_count > 0 and exp_count == 0:
        return False

    if autonomy_level.lower() in ("scientist", "analyst") and exp_count > 0:
        return True

    if autonomy_level.lower() == "tool" and deep_count > exp_count:
        return False

    return exp_count > 0


def build_researcher_agent(
    output_dir: Path,
    registry=None,
    day: str | None = None,
    search_backend: SearchBackend = DEFAULT_SEARCH_BACKEND,
    recency: RecencyWindow | None = None,
    instructions_override: str | None = None,
    save_tool_profile_callback: Any = None,
    save_rejected_profile_callback: Any = None,
    report_no_new_tool_callback: Any = None,
    search_query_observer: Any = None,
    save_tool_profile_observer: Any = None,
    save_rejected_profile_observer: Any = None,
    report_no_new_tool_observer: Any = None,
) -> Agent:
    """Build and return the single ResearcherAgent.

    With a registry, ``save_tool_profile_tool`` routes the canonical profile into
    the global registry (and records new/updated status for ``day``); ``is_known_tool``
    reports whether a URL is already known so the agent can skip re-profiling it.
    """
    instructions = instructions_override or load_instructions("researcher")
    tools = build_researcher_tools(
        ResearcherToolContext(
            output_dir=output_dir,
            registry=registry,
            day=day,
            search_backend=search_backend,
            recency=recency,
            save_tool_profile_callback=save_tool_profile_callback,
            save_rejected_profile_callback=save_rejected_profile_callback,
            report_no_new_tool_callback=report_no_new_tool_callback,
            search_query_observer=search_query_observer,
            save_tool_profile_observer=save_tool_profile_observer,
            save_rejected_profile_observer=save_rejected_profile_observer,
            report_no_new_tool_observer=report_no_new_tool_observer,
        )
    )

    return Agent(
        name="ResearcherAgent",
        instructions=instructions,
        tools=tools,
        model="gpt-5.4-mini",
    )

"""ResearcherAgent: the single agent that discovers AND profiles one tool per run.

Each invocation is asked to find ONE candidate that is not yet covered (an
exclusion list is passed at runtime), verify it, and either save a canonical
profile, reject it, or report that no new finding was found for this attempt.
"""

import json
from pathlib import Path

from agents import Agent, WebSearchTool, function_tool

from autoresearch_researcher.schemas.tool_profile import RejectedProfile, ToolProfile
from autoresearch_researcher.tools.github import fetch_github_metadata
from autoresearch_researcher.tools.persistence import save_tool_profile
from autoresearch_researcher.tools.search import (
    DEFAULT_SEARCH_BACKEND,
    RecencyWindow,
    SearchBackend,
    search_web_query,
)

INSTRUCTIONS_DIR = Path(__file__).parent.parent / "instructions"

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
    """Load agent instructions from instructions/{agent_name}.md."""
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
) -> Agent:
    """Build and return the single ResearcherAgent.

    With a registry, ``save_tool_profile_tool`` routes the canonical profile into
    the global registry (and records new/updated status for ``day``); ``is_known_tool``
    reports whether a URL is already known so the agent can skip re-profiling it.
    """
    tools_dir = output_dir / "tools"
    rejected_file = output_dir / "_rejected_profiles.jsonl"
    no_new_file = output_dir / "_no_new_tool.jsonl"

    if search_backend == "openai":
        # Hosted web search runs server-side; needs only OPENAI_API_KEY.
        search_tool = WebSearchTool()
    else:
        @function_tool
        def search_web(query: str) -> str:
            """Search the web using the configured backend. Returns source URLs/snippets."""
            return search_web_query(query, backend=search_backend, recency=recency)

        search_tool = search_web

    @function_tool
    def is_known_tool(url: str) -> str:
        """Check if a tool URL is already in the global registry. Returns 'known' or 'new'."""
        if registry is not None and registry.contains(url):
            return f"known: {url} is already in the global registry — pick a different tool."
        return f"new: {url} is not in the registry yet — proceed to profile it."

    @function_tool
    def fetch_github_metadata_tool(github_url: str) -> str:
        """Fetch GitHub repository metadata (stars, last commit, open issues, license)."""
        result = fetch_github_metadata(github_url)
        if result is None:
            return "Could not fetch GitHub metadata"
        return str(result)

    @function_tool
    def save_source_tool(url: str, title: str) -> str:
        """Register a source URL and return a placeholder source ID."""
        return "0"

    @function_tool
    def save_tool_profile_tool(
        slug: str,
        name: str,
        license: str,
        domains: list[str],
        autonomy_level: str,
        autonomy_rationale: str,
        interface: str,
        resource_requirements: str,
        last_commit: str | None,
        stars: int | None,
        open_issues: int | None,
        pricing_note: str,
        key_limitations: list[str],
        github_url: str | None,
        paper_url: str | None,
        project_url: str | None,
        source_ids: list[int],
        page_title: str | None = None,
        page_description: str | None = None,
        page_image_url: str | None = None,
        page_published_at: str | None = None,
        source_updated_at: str | None = None,
    ) -> str:
        """Save a profiled, in-scope tool. With registry: routes to
        _registry/profiles/{slug}.md; without registry: tools/{slug}.md."""
        profile = ToolProfile(
            slug=slug,
            name=name,
            license=license,
            domains=domains,
            autonomy_level=autonomy_level,
            autonomy_rationale=autonomy_rationale,
            interface=interface,
            resource_requirements=resource_requirements,
            last_commit=last_commit,
            stars=stars,
            open_issues=open_issues,
            pricing_note=pricing_note,
            key_limitations=key_limitations,
            page_title=page_title,
            page_description=page_description,
            page_image_url=page_image_url,
            page_published_at=page_published_at,
            source_updated_at=source_updated_at,
            github_url=github_url,
            paper_url=paper_url,
            project_url=project_url,
            source_ids=source_ids,
        )

        if registry is not None and day is not None:
            is_new = registry.add(profile, day=day)
            log_file = output_dir / ("_new_candidates.jsonl" if is_new else "_updated_tools.jsonl")
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a") as f:
                f.write(json.dumps({"slug": slug, "name": name, "stars": stars}) + "\n")
            return f"Saved profile to registry: {slug} ({'new' if is_new else 'updated'})"

        save_tool_profile(profile, tools_dir)
        return f"Saved profile: {slug}"

    @function_tool
    def save_rejected_profile_tool(
        slug: str,
        name: str,
        verdict_reason: str,
        url: str | None = None,
        github_url: str | None = None,
        paper_url: str | None = None,
        project_url: str | None = None,
    ) -> str:
        """Reject a tool that does not meet scope, preserving reviewer-visible URLs."""
        rejected = RejectedProfile(
            slug=slug,
            name=name,
            url=url,
            github_url=github_url,
            paper_url=paper_url,
            project_url=project_url,
            verdict_reason=verdict_reason,
        )
        rejected_file.parent.mkdir(parents=True, exist_ok=True)
        with rejected_file.open("a") as f:
            f.write(json.dumps(rejected.model_dump()) + "\n")
        primary_url = github_url or project_url or paper_url or url or "unknown"
        return f"Rejected: {name} ({primary_url}) — {verdict_reason}"

    @function_tool
    def report_no_new_tool(reason: str) -> str:
        """Signal that no new useful finding was found for this attempt."""
        no_new_file.parent.mkdir(parents=True, exist_ok=True)
        with no_new_file.open("a") as f:
            f.write(json.dumps({"verdict_reason": reason}) + "\n")
        return f"No new tool found: {reason}"

    instructions = instructions_override or load_instructions("researcher")

    return Agent(
        name="ResearcherAgent",
        instructions=instructions,
        tools=[
            search_tool,
            is_known_tool,
            fetch_github_metadata_tool,
            save_source_tool,
            save_tool_profile_tool,
            save_rejected_profile_tool,
            report_no_new_tool,
        ],
        model="gpt-5.4-mini",
    )

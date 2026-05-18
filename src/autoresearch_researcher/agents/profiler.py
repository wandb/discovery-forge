"""ProfilerAgent: collects detailed metadata for a single tool candidate."""

from pathlib import Path

from agents import Agent, function_tool

from autoresearch_researcher.agents.discovery import load_instructions
from autoresearch_researcher.schemas.tool_profile import RejectedProfile, ToolProfile
from autoresearch_researcher.tools.github import fetch_github_metadata
from autoresearch_researcher.tools.persistence import save_tool_profile
from autoresearch_researcher.tools.search import DEFAULT_SEARCH_BACKEND, SearchBackend, search_web_query

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

    # Reject if description is dominated by deep-research/search keywords
    deep_count = sum(1 for kw in _DEEP_RESEARCH_KEYWORDS if kw in desc_lower)
    exp_count = sum(1 for kw in _EXPERIMENT_KEYWORDS if kw in desc_lower)

    # A tool dominated by retrieval/summarization keywords with no experiment keywords is OUT
    if deep_count > 0 and exp_count == 0:
        return False

    # Analyst/Scientist level with experiment keywords → IN
    if autonomy_level.lower() in ("scientist", "analyst") and exp_count > 0:
        return True

    # Tool-level that only retrieves → OUT
    if autonomy_level.lower() == "tool" and deep_count > exp_count:
        return False

    # Default: if description mentions experiment execution, accept
    return exp_count > 0


def build_profiler_agent(
    output_dir: Path,
    registry=None,
    week: str | None = None,
    search_backend: SearchBackend = DEFAULT_SEARCH_BACKEND,
    instructions_override: str | None = None,
) -> Agent:
    """Build and return the ProfilerAgent.

    If `registry` is provided, save_tool_profile routes the canonical profile
    into the global registry (and records new/updated status for the given week).
    """
    tools_dir = output_dir / "tools"

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
    ) -> str:
        """Save a profiled tool. With registry: routes to _registry/profiles/{slug}.md;
        without registry: tools/{slug}.md."""
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
            github_url=github_url,
            paper_url=paper_url,
            project_url=project_url,
            source_ids=source_ids,
        )

        if registry is not None and week is not None:
            is_new = registry.add(profile, week=week)
            # Also log to the week dir which tools became new vs. updated
            log_file = output_dir / ("_new_candidates.jsonl" if is_new else "_updated_tools.jsonl")
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a") as f:
                import json
                f.write(json.dumps({"slug": slug, "name": name, "stars": stars}) + "\n")
            return f"Saved profile to registry: {slug} ({'new' if is_new else 'updated'})"

        save_tool_profile(profile, tools_dir)
        return f"Saved profile: {slug}"

    rejected_file = output_dir / "_rejected_profiles.jsonl"

    @function_tool
    def save_rejected_profile_tool(slug: str, name: str, rejection_reason: str) -> str:
        """Reject a tool that does not meet the experiment-automation scope."""
        import json
        rejected_file.parent.mkdir(parents=True, exist_ok=True)
        with rejected_file.open("a") as f:
            f.write(json.dumps({"slug": slug, "name": name, "rejection_reason": rejection_reason}) + "\n")
        return f"Rejected: {name} — {rejection_reason}"

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
        # Full source tracking implemented in US6; return stub ID for now
        return "0"

    @function_tool
    def search_web(query: str) -> str:
        """Search the web using the configured backend. Returns source URLs/snippets."""
        return search_web_query(query, backend=search_backend)

    instructions = instructions_override or load_instructions("profiler")

    return Agent(
        name="ProfilerAgent",
        instructions=instructions,
        tools=[
            search_web,
            save_tool_profile_tool,
            save_rejected_profile_tool,
            fetch_github_metadata_tool,
            save_source_tool,
        ],
        model="gpt-5.4-mini",
    )

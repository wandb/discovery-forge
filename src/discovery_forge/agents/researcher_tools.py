"""Tool factory for the ResearcherAgent.

The tools are kept together here because they define the observable contract of
one research run: search, check registry, fetch metadata, then save/reject/report
the result through day-scoped output files.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents import WebSearchTool, function_tool

from discovery_forge.schemas.tool_profile import RejectedProfile, ToolProfile
from discovery_forge.tools.github import fetch_github_metadata
from discovery_forge.tools.persistence import save_tool_profile
from discovery_forge.tools.search import (
    DEFAULT_SEARCH_BACKEND,
    RecencyWindow,
    SearchBackend,
    search_web_query,
)


@dataclass(frozen=True)
class ResearcherToolContext:
    """Runtime context captured by the ResearcherAgent's function tools."""

    output_dir: Path
    registry: Any = None
    day: str | None = None
    search_backend: SearchBackend = DEFAULT_SEARCH_BACKEND
    recency: RecencyWindow | None = None
    save_tool_profile_callback: Callable[[ToolProfile], str] | None = None
    save_rejected_profile_callback: Callable[[RejectedProfile], str] | None = None
    report_no_new_tool_callback: Callable[[str], str] | None = None


def build_researcher_tools(context: ResearcherToolContext) -> list[Any]:
    """Return the tool list used by ResearcherAgent, in the order shown to learners."""
    tools_dir = context.output_dir / "tools"
    rejected_file = context.output_dir / "_rejected_profiles.jsonl"
    no_new_file = context.output_dir / "_no_new_tool.jsonl"

    if context.search_backend == "openai":
        # Hosted web search runs server-side; needs only OPENAI_API_KEY.
        search_tool = WebSearchTool()
    else:

        @function_tool
        def search_web(query: str) -> str:
            """Search the web using the configured backend. Returns source URLs/snippets."""
            return search_web_query(
                query,
                backend=context.search_backend,
                recency=context.recency,
            )

        search_tool = search_web

    @function_tool
    def is_known_tool(url: str) -> str:
        """Check if a tool URL is already in the global registry. Returns 'known' or 'new'."""
        if context.registry is not None and context.registry.contains(url):
            return f"known: {url} is already in the global registry - pick a different tool."
        return f"new: {url} is not in the registry yet - proceed to profile it."

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
        """Save an in-scope tool profile to the registry or the local tools directory."""
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

        if context.save_tool_profile_callback is not None:
            return context.save_tool_profile_callback(profile)

        if context.registry is not None and context.day is not None:
            is_new = context.registry.add(profile, day=context.day)
            log_file = context.output_dir / ("_new_candidates.jsonl" if is_new else "_updated_tools.jsonl")
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
        """Reject an out-of-scope candidate while preserving reviewer-visible URLs."""
        rejected = RejectedProfile(
            slug=slug,
            name=name,
            url=url,
            github_url=github_url,
            paper_url=paper_url,
            project_url=project_url,
            verdict_reason=verdict_reason,
        )
        if context.save_rejected_profile_callback is not None:
            return context.save_rejected_profile_callback(rejected)

        rejected_file.parent.mkdir(parents=True, exist_ok=True)
        with rejected_file.open("a") as f:
            f.write(json.dumps(rejected.model_dump()) + "\n")
        primary_url = github_url or project_url or paper_url or url or "unknown"
        return f"Rejected: {name} ({primary_url}) - {verdict_reason}"

    @function_tool
    def report_no_new_tool(reason: str) -> str:
        """Signal that no new useful finding was found for this attempt."""
        if context.report_no_new_tool_callback is not None:
            return context.report_no_new_tool_callback(reason)

        no_new_file.parent.mkdir(parents=True, exist_ok=True)
        with no_new_file.open("a") as f:
            f.write(json.dumps({"verdict_reason": reason}) + "\n")
        return f"No new tool found: {reason}"

    return [
        search_tool,
        is_known_tool,
        fetch_github_metadata_tool,
        save_source_tool,
        save_tool_profile_tool,
        save_rejected_profile_tool,
        report_no_new_tool,
    ]

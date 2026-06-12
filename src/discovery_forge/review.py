"""Reviewer-friendly output rendering for ResearcherAgent traces."""

from __future__ import annotations

import re
from typing import Any


def profile_review_output(
    profile: dict[str, Any],
    *,
    status: str,
    search_queries: list[str] | None = None,
    search_backend: str | None = None,
    search_recency: str | None = None,
    workflow_name: str | None = None,
    researcher_prompt_ref: str | None = None,
    researcher_prompt_hash: str | None = None,
) -> dict[str, Any]:
    """Return Annotation Queue-friendly research output fields."""
    primary_url = (
        profile.get("github_url")
        or profile.get("project_url")
        or profile.get("paper_url")
        or profile.get("url")
        or "unknown"
    )
    return {
        "profile_review_markdown": render_profile_review_markdown(profile, status=status),
        "verdict": status,
        "tool_name": profile.get("name") or "unknown",
        "primary_url": primary_url,
        "urls": {
            "github": profile.get("github_url"),
            "paper": profile.get("paper_url"),
            "project": profile.get("project_url"),
        },
        "summary": {
            "autonomy_level": profile.get("autonomy_level"),
            "page_description": profile.get("page_description"),
            "page_published_at": profile.get("page_published_at"),
            "source_updated_at": profile.get("source_updated_at") or profile.get("last_commit"),
            "key_limitations": profile.get("key_limitations"),
        },
        "search_queries": search_queries or [],
        "search": {
            "backend": search_backend,
            "recency": search_recency,
        },
        "run": {
            "workflow_name": workflow_name,
            "researcher_prompt_ref": researcher_prompt_ref,
            "researcher_prompt_hash": researcher_prompt_hash,
        },
    }


def render_profile_review_markdown(profile: dict[str, Any], *, status: str) -> str:
    """Render ResearcherAgent output as a reviewer-friendly Markdown block."""
    name = profile.get("name") or "unknown"
    slug = profile.get("slug") or name_to_slug(name)
    primary_url = (
        profile.get("github_url")
        or profile.get("project_url")
        or profile.get("paper_url")
        or profile.get("url")
        or "unknown"
    )
    limitations = profile.get("key_limitations") or []
    if isinstance(limitations, str):
        limitations = [limitations]

    lines = [
        f"# Tool Profile Review: {name}",
        "",
        f"Verdict: {status}",
        f"Slug: {slug}",
        f"Primary URL: {primary_url}",
        "",
    ]

    if status in {"rejected", "no_new"}:
        lines.extend([
            "## Scope Decision",
            profile.get("verdict_reason") or "No verdict reason captured.",
            "",
        ])
    elif status == "accepted":
        lines.extend([
            "## Scope Decision",
            profile.get("autonomy_rationale") or "No autonomy rationale captured.",
            "",
            "## Key Metadata",
            f"- Autonomy: {_md_cell(profile.get('autonomy_level'))}",
            f"- Domains: {_md_cell(profile.get('domains'))}",
            f"- License: {_md_cell(profile.get('license'))}",
            f"- GitHub: {_md_cell(profile.get('github_url'))}",
            f"- Paper: {_md_cell(profile.get('paper_url'))}",
            f"- Project: {_md_cell(profile.get('project_url'))}",
            f"- Page title: {_md_cell(profile.get('page_title'))}",
            f"- Page published: {_md_cell(profile.get('page_published_at'))}",
            f"- Source updated: {_md_cell(profile.get('source_updated_at') or profile.get('last_commit'))}",
            f"- Resource requirements: {_md_cell(profile.get('resource_requirements'))}",
            "",
            "## Known Limitations",
        ])
        if limitations:
            lines.extend(f"- {limitation}" for limitation in limitations)
        else:
            lines.append("- unknown")
        lines.append("")
    else:
        lines.extend([
            "## Scope Decision",
            "The agent did not call save_tool_profile or save_rejected_profile, so the result is unresolved.",
            "",
        ])

    lines.extend([
        "## Reviewer Checklist",
        "- Is the scope verdict correct?",
        "- Are sources primary and sufficient?",
        "- Is any metadata wrong or unverified?",
        "- Should this feedback become a prompt improvement?",
        "",
    ])
    return "\n".join(lines)


def name_to_slug(name: str) -> str:
    """Convert a tool name to a filesystem-safe slug."""
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _md_cell(value: Any) -> str:
    text = "unknown" if value is None or value == "" else str(value)
    return text.replace("\n", "<br>").replace("|", "\\|")

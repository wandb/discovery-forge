"""Persistence tools: save tool profiles and sources."""

import json
from pathlib import Path

import yaml

from autoresearch_researcher.schemas.sources import Source
from autoresearch_researcher.schemas.tool_profile import ToolProfile


def save_tool_profile(profile: ToolProfile, tools_dir: Path) -> None:
    """Save a ToolProfile as tools/{slug}.md with YAML front-matter."""
    tools_dir.mkdir(parents=True, exist_ok=True)
    out_file = tools_dir / f"{profile.slug}.md"

    front = {
        "slug": profile.slug,
        "name": profile.name,
        "license": profile.license,
        "domains": profile.domains,
        "autonomy_level": profile.autonomy_level,
        "autonomy_rationale": profile.autonomy_rationale,
        "interface": profile.interface,
        "resource_requirements": profile.resource_requirements,
        "last_commit": profile.last_commit,
        "stars": profile.stars,
        "open_issues": profile.open_issues,
        "pricing_note": profile.pricing_note,
        "page_title": profile.page_title,
        "page_description": profile.page_description,
        "page_image_url": profile.page_image_url,
        "page_published_at": profile.page_published_at,
        "source_updated_at": profile.source_updated_at,
        "github_url": profile.github_url,
        "paper_url": profile.paper_url,
        "project_url": profile.project_url,
        "source_ids": profile.source_ids,
        "key_limitations": profile.key_limitations,
    }
    body_lines = [
        f"# {profile.name}",
        "",
        f"**Autonomy level**: {profile.autonomy_level} — {profile.autonomy_rationale}",
        "",
        "## Known Limitations",
    ]
    for lim in profile.key_limitations:
        body_lines.append(f"- {lim}")

    content = "---\n" + yaml.dump(front, allow_unicode=True, sort_keys=False) + "---\n\n"
    content += "\n".join(body_lines) + "\n"
    out_file.write_text(content)


def save_source(source: Source, sources_file: Path) -> None:
    """Append a source entry to sources.jsonl."""
    sources_file.parent.mkdir(parents=True, exist_ok=True)
    with sources_file.open("a") as f:
        f.write(source.model_dump_json() + "\n")


def load_sources(sources_file: Path) -> list[Source]:
    """Load all sources from sources.jsonl."""
    if not sources_file.exists():
        return []
    sources = []
    for line in sources_file.read_text().splitlines():
        line = line.strip()
        if line:
            sources.append(Source(**json.loads(line)))
    return sources

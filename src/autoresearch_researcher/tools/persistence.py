"""Persistence tools: save candidates, profiles, drafts."""

import json
from pathlib import Path

import yaml

from autoresearch_researcher.schemas.candidate import Candidate, RejectedCandidate
from autoresearch_researcher.schemas.sources import Source
from autoresearch_researcher.schemas.tool_profile import ToolProfile


def save_candidate(candidate: Candidate, output_file: Path) -> None:
    """Append a candidate to the JSONL file."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("a") as f:
        f.write(json.dumps(candidate.model_dump()) + "\n")


def save_rejected_candidate(candidate: RejectedCandidate, output_file: Path) -> None:
    """Append a rejected candidate (with reason) to a separate JSONL file."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("a") as f:
        f.write(json.dumps(candidate.model_dump()) + "\n")


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


def save_draft(content: str, output_dir: Path) -> None:
    """Save draft.md to the daily output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "draft.md").write_text(content)


def save_comparison_table(content: str, output_dir: Path) -> None:
    """Save comparison_table.md to the daily output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "comparison_table.md").write_text(content)


def load_candidates(candidates_file: Path) -> list[Candidate]:
    """Load all accepted candidates from a JSONL file."""
    if not candidates_file.exists():
        return []
    candidates = []
    for line in candidates_file.read_text().splitlines():
        line = line.strip()
        if line:
            candidates.append(Candidate(**json.loads(line)))
    return candidates


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

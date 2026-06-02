"""Helpers for reading tool profile markdown files with YAML front-matter."""

from __future__ import annotations

from pathlib import Path

import yaml


def load_tool_profiles_from_dir(tools_dir: Path) -> list[dict]:
    """Load all tool profile .md files from tools_dir, parse YAML front-matter."""
    if not tools_dir.exists():
        return []
    profiles = []
    for md_file in sorted(tools_dir.glob("*.md")):
        if md_file.name.startswith("_"):
            continue
        content = md_file.read_text()
        profile = parse_frontmatter(content)
        if profile:
            profiles.append(profile)
    return profiles


def parse_frontmatter(content: str) -> dict | None:
    """Extract YAML front-matter from a --- delimited markdown file."""
    if not content.startswith("---"):
        return None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        data = yaml.safe_load(parts[1])
        data["_body"] = parts[2].strip()
        return data
    except yaml.YAMLError:
        return None


# Backwards-compatible private alias used in a few call sites.
_parse_frontmatter = parse_frontmatter
